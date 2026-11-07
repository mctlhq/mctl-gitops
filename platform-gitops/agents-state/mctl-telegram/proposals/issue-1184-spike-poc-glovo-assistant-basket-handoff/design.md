# Design: issue-1184-spike-poc-glovo-assistant-basket-handoff

## Current state

### mctl-telegram assistant runtime (read in the clone)

- **One assistant per account.** `assistants/hr-recruiter/assistant.yaml` is the only
  embedded definition (`assistants/embed.go`). An install
  (`docs/assistants/spec.md` "Install") is stored on the account's `agent_profiles`
  row through `PUT /api/admin/agent/install`
  (`internal/agentapi/installhandler.go`, `internal/assistantinstall/service.go`:
  `Service.Prepare`, `Service.Commit`, `Service.Apply`). An install is keyed by the
  Telegram user ID (`userID int64`). It is not keyed by tenant or principal, and
  there is no install ID separate from the account.
- **Revision fencing already exists.** `agent_profiles.install_revision` moves on
  every install. Jobs and actions carry the revision, and stale work is refused as
  `install_changed` at propose, at `/mctl approve` and at send
  (`docs/assistants/spec.md` "Install revisions"). The Glovo order snapshot reuses
  this as its install binding.
- **What triggers the assistant today.** Inbound third-party DMs go through
  `internal/agent/listener/listener.go`, then jobs, then the worker. Owner commands
  arrive separately as `/mctl ...` in Saved Messages
  (`internal/agent/control/router.go`, `Router.HandleSavedText`, which handles
  status, approve/reject, takeover and the `work` commands in
  `internal/agent/control/work.go`). The assistant has no owner-initiated task path
  and no timed trigger. `internal/agent/schedule/schedule.go` parses only *working
  hours* (when replies need approval). It is not a job scheduler. A Glovo command
  must therefore enter through the owner channel, never through the listener.
- **Identity and tenant.** `docs/contracts/mctl-api-work-context.md` pins the rule:
  the bot authenticates as `surface:telegram`, relays the user only through
  `X-MCTL-Surface-Actor`, and mctl-api resolves a verified `SurfaceIdentityLink` to
  `github:<login>`. The bot never starts or attaches executions and never names
  `engine`/`engine_ref`/`execution_id`. The client is `internal/workctx`; bindings
  are in `internal/db/work_item_bindings.go`.
- **Managed runtime** (`docs/adr/0008-managed-runtime.md`): a pooled worker with a
  claim-only credential and per-call consent `managed-data-flow/v1`, gated by
  `MANAGED_RUNTIME_ENABLED` (default `false`, `internal/config/config.go:589`).
- **Threat model for runtimes**: `docs/agent-runtime/threat-model.md` (T3 cross-job
  and cross-account access, T10 credential confusion, T12 late or stale writes). The
  Glovo threat model extends these entries rather than starting over.
- **Egress safety**: `internal/netsafe/netsafe.go` (`Client`, `PublicAddr`,
  `ReadLimited`) is the existing SSRF-safe HTTP client. The provider adapter must use
  it.
- **Human input** relay: `internal/humaninput` with
  `docs/contracts/mctl-api-human-input.md`. This is the existing durable approval and
  ask path (mctl-agents#198/#333), reused for basket consent. No new approval engine
  is added.
- No Glovo code, no Temporal SDK (`go.mod` has no `go.temporal.io`), and no
  commerce code exist in this repository. The spike precedent is
  `docs/reports/mcp-apps-spike.md`.

### Deployed state checked

- `$MCTL_GITOPS_ROOT/infra-components/data/temporal/tenant-namespace-job.yaml`:
  PostSync Job using `temporalio/admin-tools:1.31.0`. It registers
  `register_ns kuptsi 7` and `register_ns mctl-agents 30`. Search attributes:
  `kuptsi LeadId Keyword`, and `mctl-agents Service Keyword`, `IssueNumber Int`,
  `AgentVersion Keyword`. **Deployed.** No assistant namespace exists.
- `$MCTL_GITOPS_ROOT/infra-components/data/temporal/networkpolicy.yaml`
  (mctl-gitops#1810, narrowed in #1818): the header states that the frontend "has no
  client authentication" and "the network is the only boundary". Port 7233 is allowed
  from namespace `mctl-api`, from `admins` pods `admins-mctl-agents-worker{,-exec,-implement}`,
  and from `labs` pod `labs-kuptsi-app`. **Deployed.** Any pod allowed by this policy
  can therefore act on *every* Temporal namespace, including `mctl-agents`.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`:
  `TEMPORAL_NAMESPACE: mctl-agents`, `--role control` on queue `mctl-dev-loop`;
  `-exec` serves `mctl-dev-loop-exec`; `-implement` runs `--role implementation`.
  Image `ghcr.io/mctlhq/mctl-agents:1.117.0`.
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml` (around lines
  350-356): `TEMPORAL_ADDRESS temporal-frontend.temporal.svc.cluster.local:7233`,
  `TEMPORAL_NAMESPACE mctl-agents`.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`:
  `AGENT_ENABLED "true"`, `ASSISTANT_REGISTRY_ENABLED "true"`,
  `HUMAN_INPUT_ENABLED "true"`, and `workContext.featureEnabled: true` with
  `tenant: mctl`. Every work item this deployment creates goes to the single
  configured tenant `mctl`. This is the "silently assigned shared `mctl` tenant" risk
  the issue names. `MANAGED_RUNTIME_ENABLED` is not set, so it takes the code default
  `false`. mctl-telegram is not a Temporal client and is not in the NetworkPolicy.
- mctl MCP tools: no live read was made in this run. Live state (whether the cluster
  matches GitOps, actual namespaces in Temporal) is **not observed** and is listed
  under Open questions.

## Proposed solution

The spike produces documents and an inert test harness. No production code path
changes, no flag flips, and nothing in GitOps changes.

### D1. Baseline and duplicate map (`docs/reports/glovo-assistant-spike.md`)

- Builds the inventory table above into the report, marking each entry
  deployed or candidate.
- Duplicate map. Each concern stays with its existing owner:
  - catalog and install: #1002;
  - connector threat model and per-tool approval: #1048;
  - managed worker: #1088;
  - schedules: .github#318;
  - commerce accounting: .github#173;
  - tenant boundary: .github#309;
  - approval and human input: mctl-agents#198/#333;
  - Temporal client auth: mctl-gitops#1810/#1818.

  The spike adds nothing that duplicates them.
- Provider evaluation. Glovo Discover MCP is search-only, with no cart. The
  unofficial `denya/glovo-skill` prepares an authenticated basket over consumer
  HTTP/session APIs and has no checkout. Partner APIs are unknown. Each is recorded
  with auth model, session persistence, permissions and terms status. Montenegro
  coverage, the terms of service and basket continuity are marked `UNVERIFIED`. No
  cookie or token is pasted anywhere.

### D2. Tenant and Temporal topology ADR candidate (`docs/adr/0009-assistant-temporal-tenancy.md`, status: Proposed)

**Recommended target: option B.** This is a shared, per-environment Temporal namespace
`mctl-assistants` (`mctl-assistants-poc` for a disposable non-prod run), common to
every assistant type and every ordinary tenant. Isolation is done in MCTL's control
plane, not by namespace topology:

- **Only mctl-api / the Automation Control Plane is a Temporal client** for start,
  signal, query and list. The surfaces (mctl-telegram, Claude/ChatGPT MCP) call
  mctl-api with an authenticated principal and an opaque `order_id`. mctl-api derives
  the workflow ID server-side as `glovo-order/<tenant_id>/<order_id>` and checks
  `(tenant_id, owner_principal_id)` against its own order index before any Temporal
  call. Listing goes through mctl-api's index, never through Temporal visibility
  queries assembled from client input.
- **Queues.** One shared workflow/control queue `assistants-control`, served by a
  trusted worker. One low-trust provider activity queue `assistants-provider-glovo`,
  served by a provider worker in its own Kubernetes namespace (candidate
  `assistants-provider`). That worker has its own security context, egress allowlist
  for the provider only (through `netsafe` semantics), no Vault token, and no access
  to DevLoop queues or tenant namespaces.

  The provider worker still needs Temporal gRPC to poll, and with no frontend authorizer
  the NetworkPolicy is its only limit. That is why multi-tenant rollout is BLOCKED
  until an authorizer or claim mapper restricts each worker identity to its namespace
  and queue.
- **Fairness.** Per-tenant concurrency and rate limits are enforced in the control
  workflow by an activity-token semaphore keyed by `tenant_id`. A provider-global
  backoff is a per-provider circuit breaker, so one tenant's 429s throttle Glovo for
  everybody but cannot block other providers. The report compares this with
  Temporal's per-tenant task queue recommendation. Per-tenant queues are the
  promotion step when one tenant's backlog measurably delays others; per-personal-user
  queues are never the default.
- **Option C** (namespace per tenant) is the high-assurance fallback, promoted only
  on a compliance requirement, a hard auth or rate-limit boundary, or measured
  noisy-neighbour impact. Its cost is one bootstrap line, retention and search
  attributes per tenant in `tenant-namespace-job.yaml`, plus worker fan-out.
- **Option A** (`mctl-agents`) is rejected. It mixes untrusted provider I/O with the
  DevLoop's privileged queues (`mctl-dev-loop`, `mctl-dev-loop-exec`) and 30-day
  history, and every DevLoop client could touch assistant orders.
- **Retention.** 7 days for `mctl-assistants`. Histories hold only opaque IDs, so
  retention bounds metadata only.
- **Prerequisites before any multi-tenant rollout (BLOCKERS):**
  - Temporal frontend client auth (mTLS or JWT) with an authorizer scoping each
    client to its namespace;
  - narrowed NetworkPolicy entries for the assistant workers;
  - independent tenant-isolation threat-model tests.

  The NetworkPolicy alone is not enough.

### Identity chain (part of D2)

```
telegram_user_id
  -> SurfaceIdentityLink (mctl-api, verified)      -> owner_principal_id (github:<login>)
  -> tenant membership (mctl-api)                  -> tenant_id   | refuse: no_tenant / ambiguous_tenant
  -> assistant install (tenant_id, owner, assistant=glovo)
                                                   -> assistant_install_id + install_revision
  -> glovo_connection (owner-bound secret ref)     -> glovo_connection_id | refuse: no_connection
```

Rules:

- **Explicit tenant.** The tenant comes from an explicit owner choice when the
  principal has more than one tenant. It is never taken from the deployment's
  `workContext.tenant`.
- **Personal scope.** `personal:<principal>` is modelled but refused by default until
  .github#309 defines it.
- **Installs.** Today's `agent_profiles` install is per Telegram account and stays as
  it is. A Glovo install would be a separate install record keyed by
  `(tenant_id, owner_principal_id, assistant)`, so the recruiter install is not
  replaced. That change is a follow-up for #1002, not part of this spike.

### D3. Glovo adapter and checkout-handoff contract (`docs/contracts/glovo-checkout-handoff.md`)

Provider adapter interface. It is provider-neutral, and the Glovo implementation is a
fake in the PoC:

```
SearchStores(ctx, conn, query) / GetMenu(ctx, conn, store)        // read, idempotent
GetPastOrders(ctx, conn, since)                                   // read
QuoteBasket(ctx, conn, BasketDraft) -> Quote{fingerprint, totals}  // read
MutateBasket(ctx, conn, BasketDraft, idemKey) -> BasketRef        // write, authorized only
ReadBasket(ctx, conn, BasketRef) -> Quote                          // verify read-back
HandoffTarget(ctx, conn, BasketRef) -> {kind: app_open|web_url|unverified, ...}
```

There is no `PlaceOrder` and no `Pay`. `conn` is the opaque `glovo_connection_id`;
only the provider worker dereferences it, from encrypted, tenant-owned state (AES-GCM,
as in `internal/crypto`).

`GlovoOrderWorkflow` (one per order) takes an immutable `OrderSnapshot`:

```
{
  order_id, tenant_id, owner_principal_id,
  install_id, install_revision, policy_digest,
  connection_ref,
  request_ref,                          // encrypted intent text
  trigger: {kind: owner|schedule, schedule_id?, occurrence?}
}
```

States:

```
prepared -> quoted -> awaiting_consent(fingerprint, expires_at)
  -> basket_mutated -> verified -> handoff_issued(token_hash, ttl)
  -> handoff_opened -> OUTCOME_UNKNOWN
```

Terminal side states: `stale_install`, `consent_expired`, `basket_changed` (which
re-asks the owner), `provider_unavailable` and `cancelled`.

- **Consent.** Consent goes through the existing human-input request and is bound to
  `(order_id, fingerprint, install_revision)`. A signal with any other value is
  rejected.
- **Revalidation.** Every activity that writes to the provider first runs
  `RevalidateScope` (install active, revision equal, membership, connection live).
  So does every signal handler and every schedule fire.
- **Handoff token.** The token is 256-bit random. Only its hash is stored, it is
  single-use (compare-and-set), and it expires after its TTL. The handoff page or
  button checks owner, order and fingerprint, then redirects to the provider target.
  If continuity is unverified, it shows "Open Glovo and review the basket", not a
  claimed deep link.
- **Outcome.** Without provider-confirmed evidence the outcome is always
  `OUTCOME_UNKNOWN`. A later phase may poll past orders read-only for a matching
  fingerprint to move the order to `observed_placed`, which is still not "paid by
  MCTL".

Schedules. The Automation Control Plane owns the schedule. On each occurrence it
starts `GlovoOrderWorkflow` with ID
`glovo-order/<tenant>/<install>/<schedule_id>/<occurrence_utc>` and
`WorkflowIDReusePolicy=RejectDuplicate`, which gives one run per occurrence, crash
dedupe, and protection against overlapping fires. A scheduled order only *prepares*
and asks; it never mutates the basket without a consent made for that occurrence,
unless the install policy explicitly pre-authorizes the mutation (and never the
payment).

Telegram UI (minimal). The owner gets a message in the bot or Saved Messages with:

- the basket preview (store, items, modifiers, totals, delivery-address label only);
- buttons `Confirm basket`, `Change`, `Cancel` and, after verify, `Open Glovo`.

Button callbacks carry only `order_id` plus a nonce. A second press is a no-op
acknowledgement. Claude and ChatGPT later get the same contract as MCP tools
(`glovo_prepare_order`, `glovo_order_status`, `glovo_confirm_basket`) returning opaque
handles.

### D4. Inert two-tenant PoC (`test/glovo-poc/`, separate Go module)

- A separate `go.mod`, so the server image and `go.mod` at the root gain no
  `go.temporal.io/sdk` dependency. It runs with the SDK `testsuite` and the
  `temporal server start-dev` embedded test server. It runs only locally or in an
  opt-in CI job, never in a deployment.
- Components:
  - `fakeglovo`: an `httptest` server with synthetic stores, menus, past orders,
    fees, availability changes, a timeout injector and per-session carts keyed by a
    fake session.
  - `controlplane`: an in-memory mctl-api stand-in for the identity chain, order
    index, scope checks and handoff tokens, with a mock Automation Control Plane.
  - `workflows`: `GlovoOrderWorkflow` and activities.
  - `leakcheck`: scans exported histories and logs for the fake tokens and addresses
    as canaries.
- Synthetic tenants: `tenant-alpha` (owner Alice), `tenant-beta` (owner Bob) and the
  unauthorized `tenant-gamma` (Carol, no install), following the CLAUDE.md persona
  rule. Numeric IDs are checked with `git grep` before use.

### D5. Risk matrix and decision

- The threat model covers:
  - cross-tenant list, query and signal;
  - prompt or context injection through menu text, which reaches the LLM only as
    sanitized structured fields;
  - direct Temporal ingress;
  - provider credential theft;
  - SSRF through provider URLs (`netsafe`);
  - session theft;
  - a stale install;
  - another user's Glovo cart (session-bound basket ref);
  - one provider degrading others (circuit breaker per provider).
- **Expected decision: `MOCK_ONLY_PENDING_CONNECTOR`.** Three things are still
  missing: Temporal client auth, the #1048 connector threat model, and any sanctioned
  Glovo basket API. The target architecture is recorded as
  `GO_SHARED_AFTER_HARDENING` (option B) once those blockers clear.
- Child issues are listed by owner repo: mctl-api, mctl-gitops, mctl-telegram,
  mctl-agents and .github#318.

## Alternatives

1. **Run assistant orders in the existing `mctl-agents` namespace (option A).**
   Rejected. It puts low-trust provider I/O next to the DevLoop's privileged queues
   and clients, gives every DevLoop client reach into assistant orders, and keeps
   30-day history.
2. **One Temporal namespace per tenant by default (option C).** Rejected as the
   default. It gives no real isolation while the frontend lacks auth, because any
   allowed client still reaches every namespace. It multiplies bootstrap lines,
   search attributes, workers and retention policies. It does not solve the
   personal-Telegram-user case. It is kept as the promotion path for high-assurance
   tenants.
3. **Assistant-local scheduler and direct LLM-held Glovo token (for example running
   `glovo-skill` inside the worker).** Rejected. It creates a second schedule owner
   against .github#318, puts a third-party session token in the model's context
   against #1048, and depends on an unofficial consumer API.
4. **Per-tenant task queues instead of in-workflow fairness.** Evaluated rather than
   dropped. It matches Temporal's published guidance and is kept as the measured
   promotion step. It is not the default, because personal-user queue explosion
   and worker fan-out cost more than a semaphore at PoC scale.

## Platform impact

- **Migrations:** none. No schema, GitOps, flag or catalog change. New files are docs
  (`docs/reports/glovo-assistant-spike.md`, `docs/adr/0009-...` marked Proposed, and
  `docs/contracts/glovo-checkout-handoff.md`) and an isolated test module
  `test/glovo-poc/`.
- **Backward compatibility:** the main module, the server binary and the Docker
  images are unchanged. `go build ./...` at the root does not enter `test/glovo-poc`,
  because it is a separate module.
- **Resources:** local only. An optional CI job (opt-in, `workflow_dispatch`) runs the
  Temporal dev server in-process for about 2-3 minutes.
- **Risks and mitigations:**
  - *Docs read as approval to deploy.* The ADR status is `Proposed`, and the report
    states the BLOCKER and decision value at the top.
  - *A fixture leaks real data.* Only synthetic personas and fake tokens are used,
    and the leak canary test fails if a token appears in history.
  - *A docs test enumerates `docs/adr`* (for example `docs/compatibility_test.go` or
    `docs/managed_runtime_docs_test.go`). Run `go test ./docs/...` and update any
    index (`docs/adr/README.md`).
  - *The unofficial provider is used live by mistake.* The fake adapter has no real
    base URL, and the test module refuses non-loopback addresses.
