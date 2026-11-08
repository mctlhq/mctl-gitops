# Design: issue-948-feat-automation-define-canonical-automat

## Current state

Nothing named "automation" exists in `mctl-api`. Running `grep -rn automation internal` finds only
comments in `internal/auth`. The records this contract has to stand on already exist, though.

### Work-item records

- **`workitem/v1`** (`docs/work-context-contract.md`, `internal/workitems/{store,types}.go`)
  - It defines the `wi_` WorkItem, with `tenant`, `owner_principal`, `visibility`,
    `origin_surface`, `origin_client_id`, `external_key`, `state_version` and `schema_version`.
  - It defines the `we_` WorkItemExecution, with at most one non-terminal execution per item, and
    the `cs_` ContextSnapshot, which is insert-only.
  - Creation is idempotent by `idempotency_key`. An `external_key` matching
    an *open* item replays it, NOT a closed item. The
    `work_item_create_requests` row has `ON DELETE CASCADE` to WorkItem.
    Neither is durable enough to enforce permanent occurrence replay protection
    after WorkItem retention cleanup.
- **ExecutionRequest `xr_`** (`internal/workitems/execution_requests.go`)
  - `CreateExecutionRequest`, `ClaimExecutionRequest` and fulfil use these errors:
    `ErrExecutionRequestOpen` (one open request per item), `ErrIntentUnavailable`, and
    `expected_state_version` CAS.
  - ADR `docs/adr/0001-queue-execution-request-while-active.md` adds queue-while-active behind
    `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE`, plus a fail-closed orphan sweeper
    (`internal/workitems/orphans.go`): "a run it cannot read is never treated as closed".
- **ActionApprovalRequest `aar_`** (`internal/workitems/action_approvals.go`)
  - Each request is single-use and bound to one `execution_id`, `action_kind`, `target` and
    `intent_hash`.
  - Its typed errors include `ErrApprovalSelfDecision`, `ErrApprovalConsumed`,
    `ErrApprovalTargetMismatch`, `ErrApprovalStale` and `ErrApprovalReceiptStale`.
  - Governance revalidation lives in `internal/governance/governance.go`: `Revalidate`,
    `LiveAuthority`, `PolicySet.Admit` and `SpendContextIncompleteError`. An approval is bound to
    one execution, so it structurally cannot be reused for a later occurrence.

### Identity, delegation and scopes

- **SurfaceIdentityLink `sil_`** (`internal/surfaceid/store.go`)
  - A link is created by two-sided possession proof (`CreateChallenge` and `Redeem`, with
    `ChallengeTTL` = 10m).
  - A link has a TTL and is revocable (`Revoke` / `RevokeAs`).
  - `Resolve(surface, externalID)` returns only live links.
  - The only surfaces are `telegram` and `portal` (`IsSurface`).
- **Delegation** (`internal/delegation/delegation.go`)
  - A grant ref (`xr_`, `aar_`, `wi_` or `sil_`) only *selects* a grant already bound to the
    run's execution or work item.
  - "Nothing a caller supplies ... may ever produce a subject."
- **Agent scopes** (`internal/auth/agent_scope.go`, `docs/support-agent-scope.md`)
  - The `support` scope is tenant-bound and read-only (GET routes only).
  - Tokens are minted by a human, with a TTL of 10m by default and 1h at most.
  - The caller is stored as `via_principal_id`.

### Budget, ingress, Temporal and the schema harness

- **Budget observed boundary** (`internal/commerce/budget.go`): its
  payer-account/month and per-request monetary-payment limits and simulated
  payment reservations are NOT per-day, per-owner, per-run inference usage
  budgets. The authoritative metered automation/FinOps budget adapter remains
  `unknown` pending verification. No verified source means deny.
- **Event ingress** (`docs/github-events-producer.md`): HMAC-verified
  `POST /api/v1/webhooks/github`, then an outbox (`internal/events/outbox.go`), then a Valkey
  relay. It is subscribed to `pull_request` and `pull_request_review` only, so `check_run` and
  `workflow_run` have no verified producer.
- **Temporal** (`internal/temporalclient/client.go`): one fixed `TaskQueue = "mctl-dev-loop"`, with
  the namespace taken from `TEMPORAL_NAMESPACE` (`cmd/api/main.go`). Clients never choose either.
  There is no Schedule API usage today.
- **Schema harness precedent** (`internal/deployanalyze/schema.go`): it embeds
  `schema/deploy-intent.schema.json` with `//go:embed`, compiles it once with
  `santhosh-tekuri/jsonschema/v6` (already in `go.mod`), and validates in tests.
- **MCP tool count**: `TestNewMCPServer_ToolCount` (`internal/mcp/server_test.go:59`). This slice
  must leave it unchanged.

### Deployed state checked

- `$MCTL_GITOPS_ROOT` was unset. I read `/workdir/mctl-gitops/platform-gitops/` instead.
  - `services/` has tenants `admins`, `karabu`, `labs` and `namax66`.
  - `services/admins/` has no `mctl-api` directory. mctl-api's deployment is referenced from
    `bootstrap/values.yaml`, where I saw the `usageWriter` and evidence-writer flags. I found no
    automation-related value.
- No mctl MCP read tools were called. This slice changes no deployed configuration, so deployed
  state is informative only.
- I did not observe whether Temporal Schedules are enabled in the deployed Temporal namespace.
  That is recorded as `unknown` (see Open questions in `requirements.md`).
- The spike schemas in mctlhq/.github were not readable from this run, which was offline and
  read-only.

## Proposed solution

The slice adds only documentation, schemas and a pure Go validation and decision package. No
production path imports it yet.

### 1. Normative document: `docs/automation-contract.md`

The document is written in the style of `work-context-contract.md` and has these sections:

1. **Status and claim classes.** Every statement is tagged `proved-source` (a cited file),
   `isolated-model` (proved only by the harness in this package), `assumed` or `unknown`.
2. **Identity, per-fire WorkItem and durable claims.**
   - `au_` + UUID is standing intent only; a run is a derived view of one
     `wi_ → xr_ → we_` chain, never a second execution-state store.
   - The occurrence identity is a domain-separated, length-prefixed hash of
     `(au_id, trigger_kind, canonical_occurrence_identity)`:
     `at`/`schedule` = scheduled UTC instant; `event`/`dependency` =
     authenticated producer identity + event type + stable source event ID,
     **not** a transport attempt/delivery ID;
     `run` = server-bound manual request ID derived from the authenticated
     caller's request idempotency key. **Definition version is excluded.**
     A version/policy snapshot is stored as admitted run provenance.
   - `external_key = automation:<au_>:<occurrence_key>` and
     `WorkItem Create idempotency_key = automation-fire:<occurrence_key>`
     are server-generated; distinct overlapping occurrences get different
     `wi_` and at most one active `we_` per `wi_`.
   - A future **durable occurrence-claim** uniquely bound to
     `(tenant, au_id, occurrence_key)` records `wi_id`, admitted version
     and terminal/tombstone state. Claim retention MUST outlive WorkItem
     terminal transitions/history sweeps and source replay; cleanup cannot
     re-enable an old fire while its `au_` is usable. Atomic claim/WorkItem/
     ExecutionRequest creation or fail-closed reconciliation is mandatory
     for `automation-api-store`; none is implemented in this slice.
   - Expected duplicate delivery returns a replay of the original run
     (`replayed: true`) or a redacted tombstone, never a new effect or
     a routine 409. Conflicting reuse of an occurrence identity returns
     `automation_occurrence_conflict` 409; divergent/corrupt internal state
     may use `automation_occurrence_duplicate` 409.
3. **Operations.** `create`, `get`, `list`, `update`, `pause`,
   `resume`, `delete`, `run`, `list_runs`. Future MCP names are
   `mctl_automation_*` and REST paths
   `/api/v1/automations[/{id}[/runs|:pause|:resume|:run]]`; **nothing
   registered in this slice**.
   - Separate create, definition (response) and patch schemas; future
     routes expose explicit request/response/error contracts.
     Definition creation idempotency is scoped by
     `(tenant, authenticated principal, caller key)`; a different
     principal's same key/body never returns another owner's definition.
   - Opaque cursor pagination `limit` 1..100; filters `state`/`template`;
     soft delete, history and retention are specified, not built.
   - `run` takes a mandatory opaque caller `idempotency_key` scoped
     to principal, tenant and `au_`; the server binds it to an immutable
     manual occurrence ID. Same request = replay; changed request under
     same key = 409; fresh key = deliberate new fire. **Manual run is
     disabled until separately approved.**
   - `at` becomes `completed` after fire. Support definition TTL is at
     most 24h, independent of per-fire run token TTL.
4. **Field ownership.** Caller-writable fields are explicitly separated
   from server-owned/derived `au_`, authenticated actor, version,
   lifecycle, tenant and surface. Neither body nor template may select
   raw Temporal workflow/namespace/task queue/signal.
5. **Template registry versus enablement.**
   - Schema registry names `reminder.v1` (`text` <=2 KiB,
     gated `notify.surface`) and `support.diagnostic-followup.v1`
     (`question_ref`, read-only `support` scope).
   - Enabled-template registry is a **separate server-only decision**:
     initial gate is **`reminder.v1 + at` only**. Support is structurally
     valid, but cannot execute until reviewed owner-consent, fresh
     per-fire support token and delegation checks exist.
   - Runtime mapping `(template_id, version) -> capability, queue,
     workflow, allowed trigger kinds, side effects` is server-owned.
6. **Trigger and policy semantics.**
   - `at` takes an RFC3339 instant or a local time plus IANA zone and
     explicit `dst_gap`/`dst_fold` resolution.
   - `schedule`, `event` and `dependency` are schema-defined, not
     MVP-enabled. Policies overlap/catch-up/fanout/cancellation have
     closed enums and exact compatibility gates.
   - `UNVERIFIED` Temporal behaviors include overlap/catch-up under
     outages, pause/update in-flight races and schedule-ID reuse after
     delete; isolated fake-clock results never imply server proof.
7. **Authorization and budget authority.**
   - OAuth callers (Claude/ChatGPT) are canonical token principals
     tagged with `origin_client_id`; Telegram resolves a verified,
     non-expired `SurfaceIdentityLink` and opaque, live `install_ref`.
   - Authenticate before ID lookup: unlinked/unknown identity gets the
     same 403 for every `au_` ID; after valid authentication, foreign
     tenant/owner, mismatching link and nonexistent specific resource
     all produce the **same 404 response**. `list` excludes unauthorized
     resources without count leakage. Create in an unauthorized tenant
     denies before any foreign resource lookup.
   - Existing possession proof, revocation, principal and delegate
     attribution are reused. No caller-supplied `delegated_actor`.
   - At create/update, at every fire, and immediately before every
     external side effect, use live authorization, install revision,
     policy and budget checks. Unavailable authority fails closed.
     A schedule never grants a standing `aar_`; any action approval
     is bound to one `we_`.
   - A future verified automation usage authority must enforce per-run,
     per-day and per-tenant inference limits with idempotent reservation,
     release and settlement. `internal/commerce/budget.go` does not
     prove these limits. The isolated decision harness accepts verified
     headroom/source availability as input only, not a client assertion.
8. **Support scope and renewal (NOT enabled).**
   - `support.diagnostic-followup.v1` is a template *definition* with
     at most 24h life / three read-only fires; current `support` run
     token is only 10m default / 1h max and minted by a human (direct
     or registered surface relay).
   - Each eventual fire needs a **fresh eligible run token** plus
     independent live tenant-owner consent; no 24h token reuse, no
     agent/service self-mint, no `auth_ref`-by-presence permission.
   - Without independently approved renewal/delegation policy and a
     safe minting path, Support stays disabled with a fail-closed reason.
     mctl-api#901 is separate/unapproved work, not authorization here.
9. **Transport and failure.** The future reconciler distinguishes
   desired/observed schedule state; orphan schedules are not silently
   adopted; retry/backoff and delivery status must be defined. Event
   ingress authenticates a stable producer event ID, tenant-hydrates
   subject and dedupes per `(subscriber au_, source, event ID)`;
   delivery-attempt IDs cannot bypass replay protection.
10. **Versioning.** This covers the error-code evolution rules, the `v0`-to-`v1` note (no
    compatibility), the redaction boundary, and the MVP gate.
11. **Crosswalk.**

    | Record | Owner | mctl-agents | mctl-telegram | mctl-support |
    |---|---|---|---|---|
    | `wi_`, `xr_`, `we_`, `cs_` | mctl-api | consumes | consumes | consumes |
    | `aar_` | mctl-api | consumes | consumes | consumes |
    | `sil_` | mctl-api; created by the surface's redeem | | redeems | |
    | automation usage budget | mctl-api (adapter/source of truth **not yet proven**) | consumes verified budget admission | | |
    | payment budget | mctl-api commerce (payment-only; not general inference spend) | | | |

    The table also lists what each consumer must never write.
12. **Proposed follow-up slices**, for owner review only and not filed:
    - `automation-api-store` (au_ table plus CRUD behind a flag);
    - `automation-temporal-reconciler`;
    - `automation-reminder-delivery` (mctl-telegram);
    - `automation-support-followup` (mctl-support);
    - `automation-event-ingress`.

    Each has a rollout checkpoint.

### 2. Schemas: `internal/automation/contract/schema/v1/`

The schemas are written in JSON Schema draft 2020-12, with `additionalProperties: false`
everywhere:

- `automation-create-request.schema.json`
- `automation-manual-run-request.schema.json` (caller-scoped request `idempotency_key`, client input only, no `occurrence_key`/`wi_`/`we_` fields)
- `automation-patch.schema.json`. This uses `expected_version` with JSON Merge Patch semantics over
  the client-writable fields only.
- `automation-definition.schema.json`
- `trigger.schema.json`, with a `oneOf` over the kinds
- `policies.schema.json`
- `template-reminder.v1.schema.json`
- `template-support-followup.v1.schema.json`
- `automation-run.schema.json`
- `automation-error.schema.json`, with the `code` enum

The `automation-error.v1` code vocabulary is:

| Code | HTTP | Meaning |
|---|---|---|
| `automation_invalid` | 400 | malformed body or schema violation |
| `automation_unknown_field` | 400 | unknown field |
| `automation_server_owned_field` | 400 | client supplied a server-owned field |
| `automation_template_not_allowed` | 400 | template not on the allowlist |
| `automation_trigger_unsupported` | 400 | trigger kind outside the enabled set |
| `automation_time_ambiguous` | 400 | DST gap or fold with policy `reject` |
| `automation_support_constraint` | 400 | Support constraint violated |
| `automation_not_found` | 404 | also covers cross-owner and cross-tenant reads |
| `automation_version_conflict` | 409 | CAS mismatch |
| `automation_idempotency_key_reused` | 409 | same key, different body |
| `automation_occurrence_conflict` | 409 | conflicting canonical intent under a previously claimed occurrence identity, no new fire |
| `automation_occurrence_duplicate` | 409 | divergent/corrupt internal replay state only; ordinary retry returns success `replayed: true` |
| `automation_identity_unlinked` | 403 | |
| `automation_policy_drift` | 409 | |
| `automation_budget_exhausted` | 409 | verified automation usage budget exhausted (not payment authorization) |
| `automation_approval_required` | 409 | |
| `automation_approval_not_reusable` | 409 | |
| `automation_paused` | 409 | |
| `automation_authority_unavailable` | 503 | |

### 3. Harness: `internal/automation/contract` (pure Go, no I/O)

- `schema.go` follows the same pattern as `deployanalyze/schema.go`:
  - it embeds and compiles the schemas once;
  - `ValidateCreate(raw []byte) error`, `ValidatePatch(raw)` and `ValidateDefinition(raw)` return
    `*ContractError{Code}`;
  - a pre-pass reports server-owned keys as `automation_server_owned_field` before the generic
    unknown-field rule.
- `templates.go` separates a closed template **schema registry** from an
  explicit enabled-template set. Initial enablement only `reminder.v1 + at`;
  Support is schema-valid and disabled. Client input selects neither
  queue/workflow nor enabled status.
- `trigger.go` provides `ResolveAt(local, zone, gap, fold) (time.Time, error)` using
  `time.LoadLocation`. Gap and fold are detected by round-trip comparison. The package embeds
  `time/tzdata` so the tests are deterministic.
- `occurrence.go` provides `OccurrenceKey(auID, triggerKind, sourceID)`,
  `ExternalKey(...)`, `FireIdempotencyKey(...)` and a pure manual-request
  binding helper. Use domain-separated canonical length-prefixed hashing,
  with **no definition version in the deduplication key**. The package
  models keys and replay decisions, not the future DB claim/tombstone.
- `authority.go` provides the isolated decision model. It is pure and has no store.
  - The function is `Decide(Checkpoint, Inputs) Decision`.
  - `Inputs` is a struct of already-resolved facts: link state, install state, tenant membership,
    owner match, pinned versus live policy version, budget headroom, approval binding
    `(aar_.execution_id == this we_)`, and source availability.
  - Any source marked unavailable yields `automation_authority_unavailable`.
  - Its doc comment says it models the rules and is not wired to `governance.Revalidate`. Wiring is
    for later slices.
- `support.go` checks definition bounds, separate 1h support token TTL,
  eligible per-fire mint/owner consent and fail-closed unknown authority.
  It does not mint tokens.
- A pure `ManualOccurrence(...)` helper models caller-scoped manual
  request replay/conflict without enabling a production run operation.
- `testdata/valid/*.json`, `testdata/invalid/*.json` and a `manifest.json` map each fixture to its
  expected code.

## Alternatives

1. **Ship the spike `v0` schemas as-is.** Rejected by the issue. The `v0` model asserts owner and
   tenant from the client and has no action-time authority.
2. **Add an `au_` table and CRUD now, behind a flag.** Rejected. That is the next slice
   (`automation-api-store`), and it must not start before this contract is reviewed and accepted.
3. **Contract as prose plus OpenAPI only, with no harness.** Rejected. The acceptance criteria
   require machine-checkable negative tests. OpenAPI (`internal/openapi/openapi.yaml`) is the
   catalogue of served routes, and adding unserved routes there would advertise endpoints that do
   not exist.
4. **A separate scheduler service.** Rejected by the spike decision, because it duplicates tenant
   identity and governance.

## Platform impact

- **Migrations:** none.
- **Runtime:** none. The new package is imported only by its own tests. There is no binary
  behaviour change, the MCP tool count and OpenAPI are unchanged, and there are no Helm or gitops
  edits.
- **Dependencies:** none new. `santhosh-tekuri/jsonschema/v6` is already required, and
  `time/tzdata` is in the standard library.
- **Binary size:** the test-only import adds no size to the production binary. If a later slice
  imports the package, tzdata adds about 450 KB.
- **Backward compatibility:** `v1` is new. The `v0` spike documents get no compatibility promise.
- **Risks and mitigations:**
  - *The contract drifts from the real stores.* Every `proved-source` claim cites a file. Later
    slices must update the doc in the same PR.
  - *The isolated model is mistaken for enforcement.* It is labelled `isolated-model` in both the
    doc and the code. No production caller exists.
  - *Durable occurrence dedupe after close is NOT proved by WorkItem.* The
    successor slice MUST implement uniquely claimed occurrence state, a
    retention-safe tombstone and atomic or fail-closed recovery.
  - *Automation usage budget authority unresolved.* Payment Commerce
    monthly/per-request budgets are not a substitute for verified daily
    inference/LLM caps, reservation and settlement.
  - *Support authorization lifetime mismatch.* A 24h automation can outlive
    the 1h maximum support run token. Keep Support disabled until an
    independently authorized fresh per-fire token/owner-consent path exists.
  - *DST tests depend on host tzdata.* Mitigated by embedding `time/tzdata`.
