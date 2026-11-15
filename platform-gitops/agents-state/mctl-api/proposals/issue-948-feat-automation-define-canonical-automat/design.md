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
  - Creation is idempotent by `idempotency_key`. An `external_key` matching an *open* item replays
    that item.
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

- **Budget** (`internal/commerce/budget.go`): `GetBudget`, reservations, and
  `ErrBudgetExhausted` / `ErrBudgetNotFound`.
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
2. **Identity.**
   - `au_` + UUID is standing intent only.
   - `AutomationRun` is a view, not a table: for each `occurrence_key`, it is the WorkItem with
     `external_key = automation:<au_>:<occ>`, its `xr_` chain and its `we_` executions.
   - The occurrence key is derived as described in `requirements.md`.
   - Overlap produces distinct `wi_` ids. The one-open-`we_` invariant per item is the existing
     index.
   - Replay key: `idempotency_key = "automation-fire:" + occurrence_key`.
3. **Operations.** The operations are `create`, `get`, `list`, `update`, `pause`, `resume`,
   `delete`, `run` and `list_runs`. They have future MCP names `mctl_automation_*` and REST paths
   `/api/v1/automations[/{id}[/runs|:pause|:resume|:run]]`. These are specified, not registered.
   For each operation the document gives the request schema, the response schema and the error
   codes.
   - Pagination uses an opaque cursor and `limit` 1..100.
   - Filters are `state` and `template` only.
   - `delete` is a soft delete with the lifecycle `deleted`. Runs are kept per work-item retention.
     After the retention window, `get` answers `automation_not_found`.
   - Definition TTL: an `at` definition becomes `completed` after its fire. Support definitions
     expire after 24h at most.
4. **Field ownership table.** Each field is marked client-writable, server-owned or derived.
   Server-owned fields are set from `auth.User` and the resolved `SurfaceIdentityLink`, never from
   the body.
5. **Templates.** `templates/v1` is a server-side map from `template_id` to the capability, the
   agent scope, the queue and the workflow, the allowed trigger kinds and the side-effect kinds.
   - `reminder.v1` takes `{text <= 2 KiB}` and has one side effect, `notify.surface`.
   - `support.diagnostic-followup.v1` takes `{question_ref}`, uses the `support` scope and has no
     write side effect.
6. **Trigger and policy semantics.**
   - `at` takes either an `instant` (RFC 3339 with Z or an offset) or `local` (wall time plus an
     IANA `zone`) with `dst_gap` and `dst_fold`.
   - `schedule`, `event` and `dependency` are defined but unsupported in the MVP.
   - Overlap, catch-up, fanout and cancellation semantics are given as stated in
     `requirements.md`.
   - The `UNVERIFIED` Temporal list covers: Schedule overlap-policy mapping, catch-up window
     behaviour after a namespace outage, pause/update atomicity relative to an in-flight action,
     and schedule-ID uniqueness after deletion.
7. **Authority.**
   - Principal resolution covers OAuth subjects (Claude or ChatGPT, using `origin_client_id`) and
     Telegram, which uses `surfaceid.Resolve` plus an opaque `install_ref` whose meaning is
     `unknown`.
   - The document defines possession proof, revocation, principal-versus-tenant scoping, creator
     versus delegate, and audit attribution, using `audit.Entry` and `work_item_events.request_id`.
   - It lists the three checkpoints and their inputs.
   - It states that an `aar_` is per-occurrence only.
   - It states that a schedule is never approval.
8. **Support constraints**, as stated in `requirements.md`.
9. **Transport and failure.** This covers the desired versus observed reconciler and `sync_state`,
   the rule that orphan schedules are deleted and never adopted, dedupe by `occurrence_key`,
   exponential backoff with a cap, Telegram delivery outcomes, and signed producer ingress with a
   replay key per subscriber of `(subscriber au_, producer delivery id)`.
10. **Versioning.** This covers the error-code evolution rules, the `v0`-to-`v1` note (no
    compatibility), the redaction boundary, and the MVP gate.
11. **Crosswalk.**

    | Record | Owner | mctl-agents | mctl-telegram | mctl-support |
    |---|---|---|---|---|
    | `wi_`, `xr_`, `we_`, `cs_` | mctl-api | consumes | consumes | consumes |
    | `aar_` | mctl-api | consumes | consumes | consumes |
    | `sil_` | mctl-api; created by the surface's redeem | | redeems | |
    | budget | mctl-api commerce | | | |

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
| `automation_occurrence_duplicate` | 409 | the `occurrence_key` was already fired, so the delivery is a replay |
| `automation_identity_unlinked` | 403 | |
| `automation_policy_drift` | 409 | |
| `automation_budget_exhausted` | 402/409 | the status code is decided in the doc |
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
- `templates.go` holds the closed allowlist `map[string]Template`. Resolution happens on the
  server and returns the binding. A client never supplies one.
- `trigger.go` provides `ResolveAt(local, zone, gap, fold) (time.Time, error)` using
  `time.LoadLocation`. Gap and fold are detected by round-trip comparison. The package embeds
  `time/tzdata` so the tests are deterministic.
- `occurrence.go` provides `OccurrenceKey(...)`, `ExternalKey(...)` and `FireIdempotencyKey(...)`.
- `authority.go` provides the isolated decision model. It is pure and has no store.
  - The function is `Decide(Checkpoint, Inputs) Decision`.
  - `Inputs` is a struct of already-resolved facts: link state, install state, tenant membership,
    owner match, pinned versus live policy version, budget headroom, approval binding
    `(aar_.execution_id == this we_)`, and source availability.
  - Any source marked unavailable yields `automation_authority_unavailable`.
  - Its doc comment says it models the rules and is not wired to `governance.Revalidate`. Wiring is
    for later slices.
- `support.go` holds the Support constraint checks.
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
  - *Durable occurrence dedupe after close is not proved.* It is flagged `assumed` and is a
    required decision for `automation-api-store`.
  - *DST tests depend on host tzdata.* Mitigated by embedding `time/tzdata`.
