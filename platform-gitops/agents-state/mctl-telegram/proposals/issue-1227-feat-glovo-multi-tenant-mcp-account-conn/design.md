# Design: issue-1227-feat-glovo-multi-tenant-mcp-account-conn

## Current state

### In the clone (`mctlhq/mctl-telegram` at e3ff43c)

- **No Glovo code and no Temporal on `main`.** No file in the clone mentions Glovo.
  `go.mod` has no `go.temporal.io` dependency. The #1184 PoC (`test/glovo-poc/`, its own
  Go module) exists only on PR #1187, which is OPEN and unmerged (`gh pr view 1187`:
  `state OPEN, mergedAt null`). `test/` contains only `load/`.
- **Identity is the Telegram account.** Every account-scoped service takes
  `userID int64`. For example, `internal/assistantinstall/service.go` (`Service.prepare(ctx,
  userID, raw)`) and `internal/assistantinstall/forks.go` (`ownerScope(userID)`) are both
  keyed by the Telegram user, and the existing install lives in `agent_profiles`
  (`internal/db/agent_*.go`). No Go code knows an MCTL `prn_` principal or a tenant id
  per user.
- **The mctl-api relay is deployment-tenant-bound.** `internal/workctx/client.go`
  (`Client{baseURL, token, tenant}`, `NewClient(baseURL, token, tenant, hc)`)
  authenticates as `surface:telegram` and relays the human through
  `X-MCTL-Surface-Actor: <telegram id>`. Its `tenant` comes from the one deployment-wide
  `MCTL_WORK_ITEM_TENANT`. That is exactly the "tenant fallback to the hosting
  workspace" the issue forbids for Glovo end users, so the Glovo path must not reuse
  this tenant field.
- **The tg.mctl.ai OAuth server is Telegram-identity only.** `internal/oauth/scopes.go`
  (`DCRNegotiableScopes`: `telegram:*`, `account:manage`) and ADR
  `docs/adr/0004-own-authorization-server.md` describe an authorization server whose
  subject is a Telegram account. `narrowGrant` shows the least-privilege grant rule the
  Glovo resource must also apply. ADR 0008 notes that `api.mctl.ai/mcp` is a different
  realm.
- **Reusable primitives.**
  - `internal/crypto/aesgcm.go`: AES-256-GCM with HKDF-SHA256 per-user subkeys and
    versioned blobs (`VersionPerUser`, info label `mctl-telegram-session-v2`).
  - `internal/netsafe/netsafe.go`: a public-only HTTP client that pins the resolved IP
    (`Client(Options)`, `PublicAddr`) and reads with a cap (`ReadLimited`).
  - `internal/audit/redact.go`: the slog redaction handler (`sensitiveKeys` includes
    `session`, `session_encrypted`, `consent_token`, `worker_token`).
  - `docs/contracts/mctl-api-human-input.md`: the human-input relay. An answer is never
    an approval, and a failed list means "nothing observed".
  - ADR 0002 (send gate) and `docs/agent-runtime/threat-model.md`: the invariant
    "runtime reasons, MCTL executes" and the pattern of a doc-coverage test
    (`go test ./docs/...` fails when routes drift).
  - `docs/tool-descriptors*.json` with ADR 0007 (tool surface as contract): a precedent
    for a checked-in machine-readable tool surface.
- **Isolated-image precedent.** `Dockerfile.agent-worker` builds a separate image from
  `cmd/agent-worker` in the same repo, published by the same release path.

### Deployed state checked

- `mctl_list_services(team=labs)` (complete, ArgoCD ok, 21 items): `mctl-telegram`
  runs `0.134.0` on `tg.mctl.ai` and `labs-mctl-telegram.mctl.ai`, and
  `mctl-telegram-preview` runs `main-4ccb257` on `tg-preview.mctl.ai`. The managed
  worker previews `agent-worker-preview` and `agent-worker-managed-preview` run
  `main-4ccb257`. **No `glovo` service and no `glovo.mctl.ai` host exist.**
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: image tag `0.134.0`.
  The OAuth implicit-host allowlist includes `claude.ai`, `chatgpt.com` and others.
  There is no Temporal configuration.
- `grep -ri glovo $MCTL_GITOPS_ROOT/services $MCTL_GITOPS_ROOT/tenants`: no matches.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: Temporal workers
  `--role control` on `temporal-frontend.temporal.svc.cluster.local:7233`. This is the
  only Temporal client family observed, apart from mctl-api.
- Tenants present in `$MCTL_GITOPS_ROOT/tenants`: `admins`, `commerce-proof`,
  `erpact`, `karabu`, `labs`, `mctl`, `namax66`.
- `agents-state/mctl-telegram/proposals/issue-1184-...`: `status: implemented`, PR
  #1187. Its design gives the identity chain, the adapter interface (no `PlaceOrder`,
  no `Pay`), the order state machine, and the `mctl-assistants` namespace with the
  `assistants-control` and `assistants-provider-glovo` queues. Verdict:
  `MOCK_ONLY_PENDING_CONNECTOR`.
- `agents-state/mctl-telegram/proposals/issue-1225-...`: `status: proposed`. It
  recommends `REUSE_EXISTING`: the adapter becomes its own module and image in
  mctl-telegram, mctl-api is the only Temporal client, and workflows run in mctl-agents
  under a separate role and namespace. The verdict on .github#324 is **not recorded**.
- `agents-state/mctl-gitops/proposals/issue-2456-...`: names the future identity
  `temporal-provider-<name>`, which has `mctl-assistants-provider-<name>:writer` only.
- `https://github.com/denya/glovo-skill` (fetched 2026-11-07, page summary only, code
  not inspected): MIT, Node.js 18+, a local stdio MCP server, a `glovo_login` tool that
  "may open a dedicated Chrome login window for session bootstrap", and a session in
  `session.json` (mode 0600). It reads order history, stores, menus and location, and
  reads, adds, changes the quantity of and removes basket items after approval. It has
  "no checkout, payment, delivery-slot booking, or order-placement tool". It is
  "Independent project; not affiliated with ... Glovo". The contents of `session.json`
  and the endpoints used were **not observed**.
- **Not observed:** live Temporal namespaces and authorizer state, mctl-api source
  (OAuth issuer, `prn_` format, membership API), Glovo terms of service, any Glovo
  partner programme, Montenegro coverage, mobile basket continuity. See Open questions
  in requirements.md.

## Proposed solution

### AMEND 2026-11-08 — invariants superseding ambiguous initial design

**Approval is NOT `human-input`.** The mctl-telegram pinned `docs/contracts/mctl-api-human-input.md` explicitly says that an answer never grants action approval. Glovo `prepare_order` may show a preview and request a human decision, but the actual provider write must be fenced by mctl-api's canonical **ActionApprovalRequest `aar_` + single-use receipt gate** from `internal/workitems/action_approvals.go` (and governance revalidation), bound to one `we_` and hashed provider effect:
`(tenant, owner principal, order, connection, install ID/revision, basket fingerprint, item/qty/modifier/price intent, provider target)`. A different `we_`, owner, tenant, receipt, changed fingerprint or revoked connection is rejected before I/O. Clarification `hir_`, successful `glovo_prepare_order`, a schedule or the model's answer never substitutes for a human-signed `aar_` decision. Revalidation must happen both at the approved handoff and immediately before **every** provider write, including retries, where read-back prevents duplicates. Use the existing `aar_` semantics rather than inventing a second approval engine.

**G2 is not fulfilled by `mctl-api#948` or merged PR #950.** Those are contract-only. G2 requires a dedicated mctl-api implementation issue/proposal/approved merged PR and live negative integration evidence: principal-tenant-scope selection; per-owner connection registry and encrypted secret references; per-owner order index; authorization checks including revocation; `aar_` creation, decision verification and receipt reservation/consumption at the write boundary. **No fake M1 control-plane wiring or real M2/3 activation claim may treat a planning issue as delivery.**

**No hard crypto-shredding with derivable HKDF keys.** If a master KEK survives and the per-connection key can be rederived from `tenant_id` and `gcn_`, deleting ciphertext cannot prove cryptographic destruction. Use random per-connection DEKs individually wrapped under an independently rotated KEK, deleting all active DEK wrappers and copies on revoke, with tracked cache/backup retention; or explicitly label revocation as deletion/denial, NOT crypto-shredding. Logs/Temporal histories never carry session bytes.

**Trust domain:** `mctl-assistants` and `mctl-assistants-provider-glovo` are independent Temporal namespaces. Stock authorizer has no task-queue RBAC. Control-provider dispatch must use a verified Nexus endpoint or a narrowly authenticated mctl-api bridge (message IDs, tenant-scoped opaque handles, retry/dedupe/cancel, no provider->control signal authority); ordinary Activities do not jump namespaces. G5 includes denial tests for provider->control and provider->DevLoop.

**Provider and M1 presentation:** connection handoff in M1 is for a synthetic provider; no real login. A public-facing facade remains disabled until separate DNS/TLS/OAuth, tenant identity and M3 activation approvals. Provider session bootstrap/refresh must pass G3's sanctioned/legally reviewed access path and independent real-device basket continuity tests, with explicit customer consent. The new MCP resource is NOT the existing Telegram authorization server or a default `labs` user scope.



### Decision and gates

Recorded decision: **`GO_FAKE_MULTITENANT`**. The real path is **`BLOCKED_PROVIDER_ACCESS`**.

| Gate | Meaning | Unblocks | Evidence required |
|---|---|---|---|
| G0 | This M0 proposal merged and independently reviewed | M1 planning | ADR, report, schemas and threat model, plus the doc tests green |
| G1 | Runtime ownership verdict recorded on .github#324 | M1 repo placement | Owner comment on #324 (`REUSE_EXISTING` expected) |
| G2 | Glovo identity and action-approval service implemented in mctl-api (separate issue/PR; #948/#950 are only Automation contract) | M1 control-plane wiring and later release | independently reviewed, merged code + cross-tenant and same-tenant-different-user negative integration tests + `aar_` receipt enforcement |
| G3 | Provider access legally and technically GO | M2 | A sanctioned partner API, or a written legal review of the consumer API and terms, plus an accepted #1048 connector threat model |
| G4 | M1 security GO | M2 | Isolation tests T1-T16 green, plus independent review |
| G5 | Temporal client auth live (#2456) and deploy sequencing (#2457) | M3 deploy | Negative test: the provider identity cannot reach `mctl-agents` |
| G6 | Release approval for `glovo.mctl.ai` | M3 | Kill switch, rollback and monitoring verified on preview |

Transitions: `DEFER` applies if G1 or G2 stalls. `GO_FAKE_MULTITENANT` becomes
`GO_REAL_PILOT` only when G3 and G4 are both recorded. `BLOCKED_PROVIDER_ACCESS` is
final if G3 finds no permissible path. In that case only the fake or a read-only
alternative ships, and no silent bypass is ever built.

### System boundary

```
ChatGPT / Claude / Telegram
  -> glovo.mctl.ai/mcp  [cmd/glovo-mcp facade: token validation, 7 closed tools, no secrets]
       (Telegram reaches the same mctl-api calls through mctl-telegram's existing surface relay)
  -> mctl-api           [principal -> tenant membership -> install/revision -> glovo_connection,
                         order index, consent (human-input), allowlist, sole Temporal client]
  -> Temporal mctl-assistants / assistants-control   [control workflows, trusted worker]
  -> Temporal assistants-provider-glovo              [provider worker, own K8s namespace,
                                                      egress only to the provider, unseals secrets]
  -> Provider adapter: fake (M1) | real (M2, behind G3 and build tag)
```

The facade holds no provider secret, no Temporal credential and no arbitrary-HTTP
capability. It calls mctl-api with the user's own access token, or with a token
exchanged for it. It never calls Temporal.

### Identity chain (frozen)

```
access token (iss = MCTL AS, aud = https://glovo.mctl.ai/mcp, sub = prn_...)
  -> principal_id                     | refuse: not_authorized
  -> tenant membership (mctl-api)     | refuse: no_tenant / ambiguous_tenant / scope_unsupported
  -> pilot allowlist (mctl-api)       | refuse: not_in_pilot
  -> assistant install (tenant, principal, assistant=glovo) -> install_id + install_revision
                                      | refuse: no_install / stale_install
  -> glovo_connection (tenant, principal, provider, provider_account_ref) -> gcn_...
                                      | refuse: no_connection / connection_revoked / connection_expired
  -> secret_ref (sealed, per-connection key, readable only by the provider worker)
```

- Tenant selection: if the principal has more than one tenant, the facade returns
  `ambiguous_tenant` with a list of tenant display names. The user selects through a
  server-issued, token-bound selection (an mctl-api session attribute), never through a
  tool argument.
- `personal:<principal>` is modelled and always refused (`scope_unsupported`) until
  .github#309 settles it.
- Two principals in one tenant get two independent connections. One principal in two
  tenants gets two independent connections. A connection is never shared.
- The Glovo install is a new record keyed by `(tenant_id, principal_id, assistant)`. It
  does not touch `agent_profiles` or the `hr-recruiter` install.

### Connection and secret state machine

```
(none) --connect--> pending_handoff --handoff opened (token CAS)--> pending_provider
pending_provider --provider proof ok--> active
pending_provider --timeout/abort/error--> failed
pending_handoff --TTL (10 min)--> failed
active --provider says expired / refresh fails--> expired --reconnect--> pending_handoff (new gcn_)
active|expired|pending_* --revoke | uninstall | membership removed--> revoked   (terminal)
```

- A reconnect always mints a new `gcn_` and a new secret. A `revoked` connection is never
  reactivated, and a reinstall never revives it. Consents are bound to `connection_id`,
  so old consents die with the connection.
- Revocation is fail-closed session and connection deletion. It may be called crypto-shredding ONLY if an independently random per-connection DEK and all recoverable wrappers/backups are destroyed with evidence; HKDF from surviving master key does not meet this condition. Provider-side session invalidation remains UNVERIFIED. The revocation is recorded in audit with IDs only.
- Secret key: a random per-connection DEK sealed/wrapped by a provider-only Vault KEK (AES-256-GCM with authenticated associated data for tenant/principal/connection). The DEK wrapper and caches must be destroyed or denied on revocation, with bounded backup retention; otherwise treat it as best-effort data deletion, never guaranteed cryptographic erasure. The provider-only KEK is unavailable to the facade or control worker. The facade and the control worker never see it.
- In M1 the fake provider issues synthetic sessions (canary strings), so the leak checks
  have something to search for.

### Authorization checkpoints

`RevalidateScope(tenant, principal, install_id, install_revision, connection_id)` is an
mctl-api call. It runs:

1. at MCP ingress, on every tool call;
2. at workflow start, inside mctl-api before the Temporal call;
3. in the provider worker, before every write activity (`MutateBasket`), as the first
   step of the activity;
4. when the consent or handoff token is used (compare-and-set single-use, then
   revalidate);
5. on every signal and schedule fire.

Every refusal is typed, and none falls back. The workflow ID
`glovo-order/<tenant_id>/<order_id>` is derived by mctl-api with
`RejectDuplicate`. Duplicate tool calls carry an idempotency key, scoped to
`(tenant, principal, tool)`, and return the original result.

### MCP surface (closed, `docs/contracts/glovo-mcp-tools.json`)

| Tool | Input (closed) | Output | Effect |
|---|---|---|---|
| `glovo_auth_status` | `{}` | `{connection_state, connection_id?, provider_account_label?, expires_at?}` | read |
| `glovo_connect_account` | `{idempotency_key}` | `{connection_id, state: pending_handoff, handoff_url, expires_at}` | creates a pending connection only |
| `glovo_get_order_history` | `{limit<=20, cursor?}` | `{orders:[{order_ref, store_name, placed_at, total_label, item_count}], next_cursor?}` | read |
| `glovo_preview_reorder` | `{order_ref}` | `{preview_id, items, unavailable_items, fingerprint, expires_at}` | read |
| `glovo_get_basket` | `{}` | `{store_name?, items, totals_label, fingerprint}` | read |
| `glovo_prepare_order` | `{preview_id, idempotency_key}` | `{order_id, fingerprint, consent_request_id, expires_at}` | prepares and asks for consent; no basket write |
| `glovo_order_status` | `{order_id}` | `{state, outcome: OUTCOME_UNKNOWN \| observed_placed, handoff_url?}` | read |

- No `place_order`, `pay`, `checkout` or `confirm_payment`. The basket write happens only after independent human approval on a canonical `aar_` request, consumed via the single-use receipt gate at provider I/O. The `hir_` clarification path NEVER authorizes a write. No model-callable tool may approve its own request.
- Text from the provider (store names, item names) is returned as bounded, sanitised
  structured fields, never as instruction-bearing free text.
- Protected-resource metadata (`/.well-known/oauth-protected-resource`):
  `resource=https://glovo.mctl.ai/mcp`, `authorization_servers=[<MCTL AS>]`,
  `scopes_supported=["glovo:read","glovo:basket:prepare"]`. `glovo:read` covers the
  read tools. `glovo:basket:prepare` covers `glovo_connect_account` and
  `glovo_prepare_order`. The grant is narrowed to the requested scopes, as
  `narrowGrant` in `internal/oauth/scopes.go` does.

### Provider adapter interface (M1 module)

The interface is the #1184 one, narrowed and given a connection type:

```go
type Adapter interface {
    AuthStatus(ctx, Conn) (Status, error)
    OrderHistory(ctx, Conn, Page) ([]PastOrder, Cursor, error)
    PreviewReorder(ctx, Conn, OrderRef) (Preview, error)
    ReadBasket(ctx, Conn) (Basket, error)
    MutateBasket(ctx, Conn, BasketDraft, IdemKey) (Basket, error) // write, after consent
}
// Conn is resolved by the provider worker from connection_id; it never crosses into
// workflow input or history. Errors map to ErrConnectorUnavailable / ErrExpired.
```

- M1 implementations: `fake` only. It has synthetic stores and carts per fake session,
  fault injection (timeouts, 429s, shape changes), and a canary session string.
- M2 (after G3): `real`, behind a build tag `glovo_real` and an env flag that is off by
  default. It uses `netsafe`-style egress pinned to the provider hosts in an allowlist.
  It is a reimplementation in Go (see Alternatives), not the Node project.

### Code placement (M1, assuming G1 = REUSE_EXISTING)

- A new Go module `providers/glovo/` (its own `go.mod`), so the root module and server
  image never gain Temporal or provider dependencies. It has these packages:
  - `adapter/` (interface, fake);
  - `conn/` (connection state machine, sealed secret store with Postgres and SQLite
    implementations, wrapped random per-connection DEKs and proven revocation semantics);
  - `authz/` (the `ScopeResolver` interface for the mctl-api contract and an in-memory
    implementation for tests);
  - `mcpfacade/` (the seven tools, built with `mark3labs/mcp-go` as in `internal/mcp`);
  - `cmd/glovo-mcp/` (the facade binary);
  - `cmd/glovo-provider-worker/` (the provider worker binary).
- `Dockerfile.glovo-mcp` and `Dockerfile.glovo-provider-worker`. They are not added to
  `release-please.yml` until the deploy gates. The images are built in CI only to check
  that they build.
- Control workflows (`GlovoOrderWorkflow`) live in mctl-agents under the
  `assistants-control` role, per the #1225 map. Until then, M1 tests drive them with the
  Temporal `testsuite` inside the module, using the #1184 PoC shape.

### mctl-api contract (handed to G2 as an issue, not built here)

- `POST /api/v1/assistants/glovo/scope:resolve` takes the access token and returns
  `{principal_id, tenant_id, install_id, install_revision, connection_id?}` or a typed
  refusal.
- `POST /api/v1/assistants/glovo/connections`, `GET .../connections/{gcn}` and
  `DELETE .../connections/{gcn}` (revoke).
- `POST /api/v1/assistants/glovo/orders` (start), `GET .../orders/{order_id}`. Consent
  requires canonical `aar_` ActionApprovalRequest and receipt enforcement; `hir_` may collect clarification only.
- mctl-api is the only Temporal client. The facade calls these routes with the user's
  token, or with a token exchanged for it (RFC 8693).

### Threat model summary (full text in `docs/agent-runtime/glovo-threat-model.md`)

| Threat | Mitigation | Test |
|---|---|---|
| Cross-tenant connection use | Scope from token plus membership, never from args; connection keyed by tenant and principal | T1, T2 |
| Same-tenant other user | Connection owner check at every checkpoint | T3 |
| Confused deputy (facade or worker acts for the wrong principal) | Facade has no secrets; worker revalidates before writes; IDs derived server-side | T6 |
| Revocation while a workflow runs | Checkpoint 3 refuses; crypto-shred | T4 |
| Stale install / reinstall revival | Revision bound into the snapshot and consent; new `gcn_` on reconnect | T5, T8 |
| Handoff / consent replay | 256-bit token, hash stored, CAS single-use, TTL | T7 |
| CSRF on the handoff page | Token-bound, `SameSite=strict`, POST with origin check | T7 |
| SSRF through provider URLs | Egress allowlist plus `netsafe` pinning; no URL inputs in the tool schemas | T10, schema test |
| Remote browser trust | None in M1; any remote browser is a G3 decision with its own review | n/a (gate) |
| Session theft from logs or histories | Opaque IDs only; redact keys; canary leak scan | T9 |
| Prompt injection via menu text | Bounded sanitised fields; no write without human consent | T11 |
| Abuse and cost fan-out | Per-tenant and per-principal rate limits; per-provider circuit breaker; history `limit<=20` | T12 |
| Token expiry | `expired` state; no silent refresh outside the worker | T13 |
| Unsanctioned API access | `BLOCKED_PROVIDER_ACCESS` until G3; real adapter absent from the build | build-tag test |

## Alternatives

- **Run `denya/glovo-skill` as a subprocess or sidecar of the provider worker.**
  Rejected. It is single-user by design (one `session.json` path per process), it
  bootstraps through a local Chrome window, and it would bring a Node runtime and
  unaudited dependencies into the most sensitive workload. Multi-tenancy would mean one
  process per connection, with the session on disk. MIT allows it, but the security
  and terms questions are unchanged.
- **Port `denya/glovo-skill` as a reference reimplementation now.** Deferred to M2,
  behind G3. Reading MIT code as a reference is permitted (keep the copyright notice if
  any code is copied). Building it before the terms are reviewed would amount to
  treating published unofficial endpoints as authorization, which the issue forbids.
- **Personal single-user PoC on `tg.mctl.ai` first.** Rejected by owner decision
  (2026-11-08). It would also inherit `workctx`'s deployment-wide tenant, which is the
  fallback this design forbids.
- **Glovo tools inside the existing `tg.mctl.ai` MCP server.** Rejected. That server's
  subject is a Telegram account (`internal/oauth`), and mixing provider tools into it
  would risk regressions on `tg.mctl.ai` and widen its scope set. A separate resource
  and audience keep the blast radius apart.
- **Temporal namespace per tenant.** Kept as the high-assurance fallback (#1184 option
  C). It is not the default.

## Platform impact

- M0 is documentation, JSON schemas and `docs/` tests only. There are no migrations, the
  root `go.mod` and the images are unchanged, and nothing is deployed.
- M1 (separate approval) adds a separate Go module and two images that are not published
  by release-please. M1 has no root `go.mod` change, no server migration and no change
  to `tg.mctl.ai`. A connection store schema is created only in the module's own
  database or schema (for example `glovo_*` tables). It is never in the Telegram session
  tables.
- Resources: none in M0. For M3 the estimate is two small Deployments (facade and
  provider worker), defined by mctl-gitops later.
- Risks and mitigations:
  - *The proposal is read as permission to call Glovo.* The decision and gates are at the
    top of the ADR, and the real adapter is absent from the build.
  - *The contract drifts from mctl-api's eventual design.* G2 makes mctl-api accept it,
    and the schemas are versioned (`glovo-mcp-tools.json` `$id` with `v1alpha1`).
  - *Unknown provider terms.* `BLOCKED_PROVIDER_ACCESS` is a valid final outcome.
  - *Kill switches.* Facade `GLOVO_MCP_ENABLED=false`. Provider worker
    `replicaCount: 0`. `GLOVO_PROVIDER_REAL=false`. Revoke the provider worker identity
    in Temporal. Remove the pilot allowlist in mctl-api.
