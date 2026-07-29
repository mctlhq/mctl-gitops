# Design: issue-340-implement-communicationapprovalworkflow

## Current state

`mctl-telegram` has a complete, working Communication Agent approval flow
with **no Temporal dependency at all** — confirmed by `grep -ri temporal`
across the repo (zero hits) and `go.mod` (no `go.temporal.io/sdk`). Relevant
existing pieces, all read directly from the clone:

- **Schema** (`internal/db/agent_schema.go`, `migrateAgent`): `agent_profiles`
  (one row per `users.id`, holds `mode`, `autopilot_paused`,
  `listener_enabled`, `sender_allowlist`, encrypted owner profile),
  `agent_actions` (`status` proposed -> pending_approval -> approved ->
  executing -> executed|rejected|expired|denied, `approval_code_hash`/
  `approval_code_encrypted`, `send_random_id`, `send_body_encrypted`),
  `agent_jobs`/`agent_job_attempts` (at-least-once durable queue, `FOR UPDATE
  SKIP LOCKED` claim), `conversations`, `job_leads`, `owner_notifications`.
  Every table is single-tenant-per-`user_id`; there is no `tenant_id` or
  `account_id` column anywhere in the schema.
- **Policy** (`internal/agent/policy/policy.go`): `Evaluate(Input) Result` —
  pure, deterministic, table-driven-tested. `mode==observe` always forces
  `RequireApproval`.
- **Executor** (`internal/agent/executor/executor.go`): the *only* code path
  that actually sends a Telegram reply on the agent's behalf.
  `Approve`/`Reject` handle the two decisions that exist today (no `edit`, no
  `cancel`). Crash safety: `send_random_id` is persisted before the MTProto
  RPC (`Store.BeginExecutingAgentAction` inside
  `Store.ReserveAgentActionSend`), so a restart mid-send retries the exact
  same send and MTProto dedups it server-side (`recoverOne`,
  `RecoverStuck`). Policy, restricted-field, and send-gate checks are all
  re-run immediately before the send RPC (`send`), not only at approval time
  — exactly the "revalidate before execution" and "recheck ownership/
  capability/kill switch" requirements #340 asks for, just implemented as
  hand-rolled DB CAS instead of a workflow engine.
- **Control surface** (`internal/agent/control/command.go`,
  `router.go`): parses `/mctl approve|reject|status|leads|show|continue|
  pause|takeover <arg>` from Saved Messages. `CmdApprove`/`CmdReject` are the
  only decision verbs; there is no `edit` or `cancel` command type today.
- **Background sweeps** wired from `cmd/server/main.go`: periodic goroutines
  call `Executor.RecoverStuck` (stuck-executing recovery) and an approval-TTL
  sweep (`ExpireStaleAgentActions`) — this is the "durable timer" role a
  Temporal workflow timer would take over for the flagged path.
- **Product audit**: `audit_logs` (`internal/db/db.go`, `Store.LogToolCall`,
  `store.go`) is a hash-chained, tamper-evident, independently-queryable
  audit log (`prev_hash`/`entry_hash`, `VerifyAuditChain`) already used for
  every MCP tool call. This is the existing "audit independent of the
  orchestration engine" precedent #340's requirement #7 and the epic's
  non-goal ("not the only audit store") point at.
- **Agent API** (`internal/agentapi`): `aud=agent` JWT surface the worker
  calls (`propose_reply`, `request_owner_approval`, etc.) — this is the
  producer of `require_approval` decisions today; #341 (not this issue) will
  add the equivalent `aud=user`/operator-facing decision surface that
  signals the new workflow.
- **Docs**: `docs/plans/communication-agent.md` is the single canonical plan
  for the whole Communication Agent effort and currently describes only the
  DB/CAS-based design above (status as of 2026-07-27, C1 validation still
  in progress). It has no Temporal section — this proposal is new ground
  relative to that plan, not an extension of an existing Temporal mention.

Confirmed via `gh issue view` that #340 is scoped by its parent epic #339
("[Epic] Add Temporal-backed human approval flow for Communication Agent")
and sibling #341 ("Expose approval decisions through agent API and audit
model", `Depends on: #340`). The epic is explicit: preserve the existing
policy engine and audit log, do not remove the existing queue before the
Temporal path is proven, ship behind a feature flag, enable first only for a
test tenant/account.

## Proposed solution

Add Temporal as a new, additive orchestration layer that a feature-flagged
subset of `require_approval` decisions route through, while the existing
`agent_actions`/`executor` path keeps serving everyone else unchanged during
rollout.

**1. New package `internal/comms` (workflow + activities), new dependency
`go.temporal.io/sdk`.**

```
internal/comms/
  workflow.go       // CommunicationApprovalWorkflow
  signal.go         // DecisionSignal type, validation
  query.go          // StatusQuery handler + response type
  activities.go      // Activity interfaces + implementations
  activities_test.go
  workflow_test.go   // testsuite-based unit + replay tests
  ids.go             // workflow_id / approval_id construction helpers
```

- `CommunicationApprovalWorkflow(ctx workflow.Context, input WorkflowInput) (WorkflowResult, error)`
  is the only workflow function. `WorkflowInput` carries `TenantID`,
  `AccountID`, `AgentProfileID`, `ConversationID`, `OperationID`, the
  proposed action type/payload, a `ProposalHash`, the policy decision/version
  that triggered the workflow, and actor/source metadata — exactly the field
  list the issue specifies. All of this is passed in once at start and never
  re-derived non-deterministically inside the workflow (no `time.Now()`,
  no random IDs generated in workflow code — those come from Activities or
  `workflow.SideEffect`/`workflow.Now` where unavoidable).
- Workflow ID: `communication:{tenant_id}:{account_id}:{operation_id}`,
  constructed once in `ids.go` and reused by both the starter (Agent API /
  executor integration point) and any replay test fixture, so retries and
  duplicate proposals from the same `operation_id` always address the same
  workflow (`WorkflowIDReusePolicy` set to reject-duplicate for the active
  run, matching the "duplicate API requests address the same workflow"
  requirement).
- Approval ID: `{workflow_id}:{approval_revision}`, minted inside the
  workflow when it enters `waiting_approval`; `approval_revision` starts at 1
  and increments on every `edit`.
- State machine implemented as an explicit Go `type approvalState string`
  enum matching the issue's diagram exactly: `proposed`, `waiting_approval`,
  `approved`, `executing`, `completed`, `failed`, `edited`, `validating`,
  `rejected`, `cancelled`, `expired`, `denied`. Transitions are a small
  table-driven function (`nextState(current, event) (next, ok)`) unit-tested
  independently of the workflow, mirroring the existing pure-function style
  of `internal/agent/policy.Evaluate` and `internal/agent/control.ParseCommand`.
- Waiting: `workflow.NewSelector` over (a) a signal channel for
  `DecisionSignal` and (b) a `workflow.NewTimer(ctx, approvalTTL)` — this
  timer, not a goroutine sweep, is what "an approval expiry uses a durable
  Temporal timer" and "waiting consumes no active worker" translate to.
  When the timer fires first, the workflow transitions to `expired` via the
  same `nextState` table and returns (or Continue-As-News once, see below).
- `DecisionSignal` handling: validate `approval_id` matches current, validate
  `expected_revision` matches current `approval_revision`, and check
  `request_id` against an in-workflow bounded set (`map[string]struct{}`,
  capped and pruned the same way the issue's "duplicate/late decisions" tests
  expect) before acting — all three checks happen before any state mutation,
  so a rejected signal is a true no-op. Exactly one valid terminal decision
  is accepted per revision: the selector loop exits the `waiting_approval`
  case as soon as one signal passes validation for that revision; every
  further signal for the same revision fails the `expected_revision` check
  by construction once the revision has moved on.
- `approve`: revalidate via a `RevalidateActivity` (tenant/account ownership,
  capability, peer identity, proposal version, policy version, kill switch —
  the same checklist `executor.send` already re-runs today) before calling
  `ExecuteActionActivity`. Both activities are ordinary Temporal Activities
  with per-activity `RetryPolicy` (not a blanket workflow-level retry, per
  the issue's explicit requirement) — non-retryable application errors (deny,
  stale revision, kill switch on) are returned as
  `temporal.NewNonRetryableApplicationError` so a policy deny does not get
  silently retried into an eventual allow.
- `reject`/`cancel`: transition directly to the terminal state, call
  `AuditActivity` for the transition, return. `cancel` is deliberately
  **not** implemented via Temporal's native workflow-cancellation feature —
  it is a `DecisionSignal.decision=="cancel"` handled inside the same
  selector, because native cancellation cannot express "must not interrupt
  an already-committed external side effect" (the issue's explicit
  concurrency/safety requirement); once `ExecuteActionActivity` has started,
  the workflow is past the point where a `cancel` signal is still consulted
  — the state table has no `executing -> cancelled` edge.
- `edit`: build a new proposal revision from `edited_payload`
  (`approval_revision++`), transition to `edited` then `validating`, call the
  same policy Activity used for the original proposal
  (`PolicyEvaluateActivity`, wrapping `internal/agent/policy.Evaluate` so the
  deterministic policy logic itself is never reimplemented in workflow code —
  Activities are allowed to call it because Activity code is not required to
  be deterministic, and the policy function itself already is pure/
  deterministic so this is a safe, side-effect-free call). Based on the
  result, the workflow either loops back to `waiting_approval` (mint a new
  `approval_id` at the bumped revision) or proceeds to `executing` — never
  assumes edit implies approval, matching the issue's explicit warning.
- Query handler `GetStatus` (registered via `workflow.SetQueryHandler`)
  returns `{state, approval_revision, approval_id, expires_at,
  terminal_result}` without mutating state, satisfying "Workflow exposes a
  Query for current status and proposal revision" / "Query returns state,
  current revision, expiry, and terminal result".
- Continue-As-New: after N `edit` cycles (constant, e.g. 20, configurable)
  or when `workflow.GetInfo(ctx).GetCurrentHistoryLength()` crosses a
  threshold, the workflow calls `workflow.NewContinueAsNewError` carrying
  forward current state/revision — addresses "Continue-As-New is considered
  if workflow history can grow through repeated edits" without over-engineering
  a fixed cadence into v1.

**2. Activities call back into existing packages, they do not duplicate
them.** `ExecuteActionActivity` wraps a narrow interface implemented over
`internal/agent/executor` (or a new minimal `comms.Sender`/`comms.Store`
adapter mirroring `executor.Sender`'s existing narrow-interface pattern) so
the *actual* Telegram send still goes through the one send path the repo
already trusts for `send_random_id` crash-safety — Temporal does not get its
own second implementation of "how to send a Telegram message safely."
`PolicyEvaluateActivity` wraps `internal/agent/policy.Evaluate` directly (it
takes no I/O, so wrapping it in an Activity is solely so workflow code never
calls it inline — keeps the workflow itself trivially deterministic and
free of any accidental non-determinism if the policy package ever gains
I/O). `AuditActivity` wraps `Store.LogToolCall` (or a small dedicated
`Store.LogCommsWorkflowEvent` following the identical hash-chain pattern) so
every workflow transition lands in the existing tamper-evident audit log —
satisfying "Persist product audit events independently from Temporal
history" and the epic's "not the only audit store" non-goal by construction
(the audit row exists whether or not Temporal history is ever read again).

**3. New schema, additive only.** A new migration file
`internal/db/comms_schema.go` (following the exact `migrateAgent`/
`addColumnIfMissing` idempotent pattern in `agent_schema.go`) adds:
- `comms_approval_workflows` — one row per workflow (`workflow_id` PK,
  `tenant_id`/`account_id`/`agent_profile_id`/`conversation_id`/
  `operation_id`, `state`, `approval_revision`, `approval_id`,
  `proposal_hash`, `policy_version`, `expires_at`, `terminal_result`,
  timestamps) — a read-side projection kept in sync by `AuditActivity`,
  *not* the workflow's source of truth (Temporal itself is), so operators
  and #341's future API can query current state without calling Temporal
  directly for simple listing.
- `comms_approval_decisions` — append-only, one row per accepted
  `request_id` (`workflow_id`, `approval_id`, `expected_revision`,
  `request_id` UNIQUE per workflow, `decision`, `actor`, `decided_at`) —
  gives an idempotency backstop even though the workflow's own in-memory
  `request_id` set is the primary dedup mechanism (Temporal workflow state
  is durable across restarts by design, but this table also makes dedup
  state auditable/queryable outside Temporal, and doubles as the audit
  record for #340's own "Product audit events are emitted for every
  transition" acceptance criterion).
No existing table (`agent_actions`, `agent_jobs`, etc.) is altered. This
keeps the new path reconcilable against, and rollback-safe from, the
existing one.

**4. New worker entrypoint `cmd/comms-worker`**, modeled directly on
`cmd/agent-worker`'s structure (own `main.go`, own `Dockerfile.comms-worker`,
own `-ldflags "-X main.version=..."` convention) rather than folding a
long-running Temporal worker into `cmd/server`'s HTTP process — this matches
the repo's existing precedent of a dedicated binary/image per distinct
runtime concern (`cmd/agent-worker` needs the `claude` CLI the server image
deliberately excludes; `cmd/comms-worker` needs the Temporal SDK's
long-lived gRPC connection and worker poll loop, which has different
scaling/restart semantics than the chi HTTP server). Registers
`CommunicationApprovalWorkflow` and its Activities on an explicit named task
queue (e.g. `comms-approval-v1`, from config, never Temporal's default queue)
— satisfies "Workflow and worker are registered on an explicit task queue."

**5. Feature flag and integration point.** A new config field
(`AGENT_COMMS_WORKFLOW_ENABLED` plus a scoping value, e.g.
`AGENT_COMMS_WORKFLOW_TENANT_IDS` — a CSV allowlist, mirroring the existing
`agent_profiles.sender_allowlist` empty-means-allow-all-but-default-empty
pattern) gates a new branch at the single point in the codebase where a
`require_approval` policy result currently creates a DB-CAS `agent_actions`
row and an approval code
(`internal/agentapi/actions.go`'s `request_owner_approval` handling / the
propose_reply path that calls `policy.Evaluate`). When flagged on for the
tenant, that call instead starts (or signal-with-starts)
`CommunicationApprovalWorkflow` and returns; when off (default, and for
every tenant not on the allowlist), the existing `agent_actions` path is
untouched. This is deliberately a branch at the call site, not a rewrite of
`internal/agent/executor` or `internal/agentapi` — #341, not #340, is where
the decision-submission API and any UI-facing surface change; #340 itself
only needs the workflow to be startable and signalable, wired through the
minimum integration point necessary to prove it end-to-end and to satisfy
"Existing non-approval jobs continue to work during rollout" (epic
acceptance).

## Alternatives

1. **Replace `internal/agent/executor`'s CAS state machine outright with the
   Temporal workflow for every tenant.** Rejected: violates the epic's
   explicit non-goal ("removing the existing queue before the Temporal path
   is proven") and acceptance criterion ("Existing non-approval jobs continue
   to work during rollout"). It would also force a one-shot cutover of the
   crash-safety invariants (`send_random_id` persistence, atomic budget
   reservation) that are currently well-tested and already running toward
   C1/C2 production promotion — an all-or-nothing migration is exactly the
   kind of risk the epic's "feature flag, one test tenant first" delivery
   plan is designed to avoid.
2. **Model `tenant_id`/`account_id` as real new columns across
   `agent_profiles`/`agent_actions`/etc. instead of mapping them onto the
   existing `user_id` model.** Rejected for this issue: it is a much larger,
   cross-cutting schema migration unrelated to what #340 asks for (the
   workflow and signal contract), it is not requested by the epic, and it
   would touch every existing agent table's indexes/CAS queries during an
   already-risky introduction of a new orchestration engine. Flagged as an
   explicit open question instead; the mapping is confined to the new
   Temporal-facing identifiers.
3. **Use Temporal's native `CancelWorkflow`/`workflow.Context` cancellation
   for the `cancel` decision instead of a `DecisionSignal`.** Rejected:
   native cancellation is delivered asynchronously and does not naturally
   compose with "cancellation must not interrupt an already committed
   external side effect" — an Activity already in flight when a cancel
   arrives would need explicit `heartbeat`/cancellation-aware code to avoid
   a race, and native cancellation also does not go through the same
   `expected_revision`/`request_id` idempotency checks the other three
   decisions need. Treating all four decisions uniformly as one versioned
   signal (exactly as the issue specifies) keeps one code path, one
   validation order, and one audit trail for all four.
4. **Store workflow state only in Temporal (no `comms_approval_workflows`/
   `comms_approval_decisions` read-side tables).** Rejected: the issue's own
   acceptance criteria require product audit events "independently from
   Temporal history" and the epic explicitly says "not the only audit store"
   — a Temporal-only source of truth would fail both. The read-side tables
   also give #341's future listing API (`GET /v1/approvals?status=pending`)
   something to query without a live round-trip to Temporal for every list
   request.

## Platform impact

- **Migrations**: additive only (`comms_approval_workflows`,
  `comms_approval_decisions`), following the repo's existing idempotent
  `CREATE TABLE IF NOT EXISTS` + `addColumnIfMissing` hand-rolled migration
  convention (`internal/db/agent_schema.go`, `internal/db/db.go`). No
  existing table's schema or data is touched. Both SQLite (local dev) and
  Postgres (production) variants required, per `Migrate()`'s existing
  dual-dialect pattern.
- **Backward compatibility**: fully backward compatible by construction —
  the feature flag defaults to off/empty-allowlist, so no existing tenant's
  behavior changes until explicitly opted in. The existing `agent_actions`
  CAS path, `/mctl approve|reject`, and all current tests remain unchanged.
- **New runtime dependency**: a reachable Temporal Server (self-hosted or
  Temporal Cloud) becomes a new external dependency for any tenant on the
  flag — this is new operational surface for `mctl-gitops` (not scoped in
  this proposal; deployment/GitOps wiring is deferred, matching how
  `cmd/agent-worker`'s deployment was a separate GitOps PR from its
  application-code PR in the existing Communication Agent rollout history).
  Until the flag is enabled for any tenant, `cmd/comms-worker` can run
  connected to a dev/staging Temporal instance with zero production impact.
- **Resource impact**: one new long-lived worker process/image
  (`cmd/comms-worker`, own `Dockerfile.comms-worker`), analogous in kind to
  `cmd/agent-worker`'s existing separate image/deployment. `cmd/server`
  itself gains a small new code path (feature-flag check + workflow start
  call) but no new long-lived connections — the Temporal client/worker
  lifecycle lives entirely in `cmd/comms-worker`, keeping `cmd/server`'s
  existing startup/shutdown behavior unchanged for the non-flagged majority
  of traffic.
- **Risks and mitigations**:
  - *Risk*: two orchestration engines (DB-CAS and Temporal) both able to
    reach for the same underlying send capability creates a double-send
    hazard if a tenant/operation is accidentally routed through both.
    *Mitigation*: the feature-flag branch is a single, tenant-scoped decision
    point at proposal time (design item 5); `ExecuteActionActivity` reuses
    the same `send_random_id`-based idempotent send path
    (`internal/agent/executor`'s underlying primitives), so even a
    misconfiguration that somehow double-triggers a send is caught by
    Telegram's own server-side `random_id` dedup, matching the existing
    system's defense-in-depth.
  - *Risk*: workflow non-determinism (a common Temporal pitfall — calling
    `time.Now()`, iterating a Go map, or reading external state directly
    inside workflow code) breaking replay. *Mitigation*: all I/O and
    non-deterministic calls (policy evaluation, revalidation, execution,
    audit writes, `random_id` generation) are pushed into Activities;
    workflow code only does state-machine transitions, signal/timer
    selection, and Continue-As-New — enforced by the replay test required in
    Acceptance criteria (tasks.md T-series) and by keeping `workflow.go`
    free of any import outside `time`/the Temporal SDK/pure local types.
  - *Risk*: unbounded workflow history from a pathological repeated-edit
    loop. *Mitigation*: Continue-As-New threshold (design item 1).
  - *Risk*: schema/tenant-mapping open question (see requirements.md) is
    wrong and needs revisiting once true multi-account tenancy exists.
    *Mitigation*: the mapping is isolated to `WorkflowInput` construction
    and the two new tables' `tenant_id`/`account_id` columns — no existing
    table is coupled to this assumption, so a later correction does not
    require an existing-table migration.
  - *Risk*: introducing a second, less-proven "approve/reject" path could
    regress the careful crash-safety work already validated toward C1 (see
    `docs/reports/communication-agent-c1.md`). *Mitigation*: feature flag
    scoped to a single test tenant/account per the epic's explicit delivery
    plan; the existing C1/C2 rollout gates in
    `docs/plans/communication-agent.md` are unaffected since the flag stays
    off for the C1 preview tenant unless separately opted in.
