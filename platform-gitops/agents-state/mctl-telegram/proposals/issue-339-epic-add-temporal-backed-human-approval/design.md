# Design: issue-339-epic-add-temporal-backed-human-approval

## Current state

The Communication Agent's approval lifecycle is fully implemented today
without Temporal, as a DB state machine plus two background sweeps and a
command router. Read directly from the clone:

- **Policy decision.** `internal/agent/policy/policy.go`'s `Evaluate(Input)
  Result` is pure (no I/O) and returns `Allow | RequireApproval | Deny`.
  `mode == observe` and several other conditions (turn budget, intent
  allowlist, rate limit) accumulate into `RequireApproval` reasons
  (`policy.go:368-388`).
- **Action state machine.** `internal/db/agent_actions.go` defines
  `agent_actions.status` as a one-way machine (`proposed → pending_approval →
  approved → executing → executed`, with `rejected`/`expired`/`denied` side
  exits) enforced by `UpdateAgentActionStatus`'s compare-and-set against
  `allowedActionTransitions` (`agent_actions.go:409-426`). Approval codes are
  a per-user AES-GCM-sealed value plus a blind-index hash
  (`approvalCodeHash`/`protectApprovalCode`, `agent_actions.go:96-118`),
  never stored plaintext.
- **Proposing an approval.** `internal/agentapi/actions.go`'s
  `handleProposeReply` calls `policy.Evaluate`; on `RequireApproval` it calls
  `insertActionWithApprovalCode` (job-tied) or
  `insertStandaloneApprovalWithNotification` (`actions.go:104-121`), which
  atomically inserts the `agent_actions` row and the `owner_notifications`
  row that carries the approval code into Saved Messages.
- **Deciding.** `internal/agent/control/command.go`'s `ParseCommand`
  recognizes `/mctl approve|reject <code>` (only those two decisions exist
  today — no `edit`, no `cancel`). `control/router.go`'s
  `handleApprove`/`handleReject` call `executor.Executor.Approve`/`Reject`
  (`executor.go:147-214`). `Approve` re-checks the approval TTL itself
  (`ApprovalTTL`, `executor.go:163-176`) before doing a CAS
  `pending_approval → approved` and then `send()`.
- **Executing.** `Executor.send` (`executor.go:242-420`) re-runs
  `policy.Evaluate` immediately before the RPC (approval and send are not
  atomic — takeover, kill switch, rate limit can all change in between),
  persists a Telegram `random_id` in the same statement that flips
  `approved → executing` (`ReserveAgentActionSend`, `agent_actions.go:495-588`)
  **before** issuing the send RPC, so a crash mid-send is recovered by
  `Executor.RecoverStuck` retrying the identical send — MTProto dedups on
  `random_id` server-side (`executor.go:12` package doc, `executor.go:437-473`).
- **Expiry.** `Store.ExpireStaleAgentActions` (`agent_actions.go:699-716`)
  is a periodic, tenant-less sweep (`sweeper.AgentExecutor`, wired in
  `cmd/server/main.go:276`) moving `pending_approval` rows past
  `AGENT_APPROVAL_TTL` (default 24h, `internal/config/config.go:133,179`) to
  `expired`. `Executor.Approve` additionally re-checks the TTL itself
  (`ExpireAgentActionIfStale`, `agent_actions.go:718-749`) so a race with the
  sweeper cannot let an owner approve an already-stale draft
  (`executor.go:163-176`, documented as a #307 finding fix).
- **Audit.** Every transition is *not yet* uniformly on the product audit
  trail — `agentapi` handlers call `s.audit(ctx, userID, tool, status,
  reason)` for the HTTP surface, and `audit_logs` is a tamper-evident hash
  chain (`internal/db/db.go:88-96`, `internal/db/store.go:1025-1096`,
  `VerifyAuditChain`) exposed via `GET /api/audit` and the `get_my_audit_log`
  MCP tool. Owner `/mctl approve|reject` decisions themselves are **not**
  currently written to `audit_logs` — only the original `propose_reply` call
  is. This is an existing gap this proposal must close for `require_approval`
  actions specifically, independent of Temporal.
- **Feature flags & tenant scoping conventions.** No LaunchDarkly/config
  service exists. Flags are plain env-var booleans
  (`AgentEnabled`/`AGENT_ENABLED`, `AgentKillSwitch`/`AGENT_KILL_SWITCH`,
  `internal/config/config.go:139-182`) and per-tenant scoping is done via CSV
  columns on `agent_profiles` (`sender_allowlist`, `blocked_senders`,
  `agent_schema.go:280-282`), not a separate tenant table.
- **No Temporal dependency exists yet.** `go.mod` has no
  `go.temporal.io/sdk` (confirmed: `grep -ri temporal go.mod go.sum` finds
  nothing). This is a net-new infrastructure and code dependency, not an
  extension of something already wired in.
- **Precedent for a second worker process.** `cmd/agent-worker` (Option C,
  `docs/agent-worker.md`, `docs/plans/communication-agent.md` PR 8) is
  already a separate Go binary/image/deployment that talks to
  `internal/agentapi` over HTTP long-poll rather than sharing the main
  server process — the pattern this proposal's Temporal worker should follow
  rather than embedding a Temporal worker inside `cmd/server`.

## Proposed solution

Add Temporal as an **additional, feature-flagged orchestration layer
strictly scoped to the `require_approval` wait**, not a replacement for the
policy engine, the `agent_actions` state machine, or the audit chain. The DB
row remains the single source of truth for "has this action executed
yet" — Temporal's job is to hold the wait durably, deliver the decision
signal, fire the expiry timer, and give operators workflow-history
visibility, while every consequential state change still goes through the
same CAS-guarded `Store` methods that exist today.

**1. New package `internal/agent/approvalflow` (workflow + activities).**

- `ApprovalWorkflow(ctx workflow.Context, in ApprovalWorkflowInput) error` —
  one workflow execution per `agent_actions` row that reaches
  `pending_approval`. Deterministic **Workflow ID**:
  `agent-approval-{user_id}-{action_id}` so a redelivered "start workflow"
  call (mirroring the existing idempotent-insert pattern in
  `InsertAgentAction`) is a safe no-op via Temporal's own
  `WorkflowIDReusePolicy` / `AllowDuplicateFailedOnly` semantics — the same
  "redelivery must dedupe onto the existing row" property
  `InsertAgentAction`'s doc comment already documents for the DB side
  (`agent_actions.go:120-141`).
- The workflow registers one Signal channel (`decision`) accepting
  `{Type: approve|reject|edit|cancel, Payload string, IdempotencyKey
  string, DecidedBy int64}` and starts a `workflow.NewTimer` for
  `AGENT_APPROVAL_TTL`. `workflow.Selector` waits on whichever fires first.
- On the **first** signal accepted, the workflow records it locally
  (`decided = true`) so any further signal on the same channel — a duplicate
  `/mctl approve`, a redelivered HTTP decision — is discarded and logged via
  `workflow.GetLogger`, satisfying "duplicate signal" without relying on
  Temporal alone: the DB-side CAS (`UpdateAgentActionStatus`,
  `ReserveAgentActionSend`) is unchanged and independently rejects a second
  transition attempt even if two workflow executions somehow raced.
- Each branch calls one **activity**, never touches the DB or Telegram
  directly (workflow code must stay deterministic and side-effect-free —
  standard Temporal practice, and it also keeps `policy.Evaluate` itself
  completely outside workflow code, per the issue's non-goal):
  - `approve` → `DecideActivity{Kind: Approve}` wraps the existing
    `Executor.Approve` path, but keyed by `action_id` (no code lookup needed
    — the workflow already resolved identity) instead of the code-typed
    entry point. Extract the code-independent core of `Approve`
    (`executor.go:147-194`, from `GetAgentActionByCode` onward) into a new
    `Executor.ApproveActionID(ctx, userID, actionID int64) error` that both
    the existing `/mctl approve` path and this activity call, so there is
    exactly one approval implementation, not two.
  - `reject` → `DecideActivity{Kind: Reject}` calls the equivalent
    `Executor.RejectActionID`.
  - `edit` → `DecideActivity{Kind: Edit, Payload: newText}` calls a new
    `Executor.EditAndApprove(ctx, userID, actionID int64, newPayload
    string) error`: loads the action, re-runs `policy.Evaluate` against
    `newPayload` (same `policy.Input` shape `send()` already builds,
    `executor.go:277-286`), and only if the revalidated decision is not
    `Deny` does it update `agent_actions.payload_encrypted` (new `Store`
    method `UpdateAgentActionPayload`, CAS-guarded on `status =
    pending_approval` exactly like `UpdateAgentActionStatus`) and then calls
    the same `ApproveActionID` path. A revalidated `RequireApproval` returns
    a typed error the workflow interprets as "go back to waiting", not as a
    Temporal Activity failure — the workflow re-arms the signal wait with
    the **remaining** TTL (not a fresh one) rather than treating the edit as
    a new draft with a new full waiting period, so an edit cannot be used to
    indefinitely extend an approval past its original deadline.
  - `cancel` → `DecideActivity{Kind: Cancel}` calls
    `Executor.RejectActionID` for this action **and**
    `Store.DenyPendingActionsForConversation` (already exists,
    `agent_actions.go:827-842`, currently only called from
    `control.Router.handleTakeover`) for the rest of that conversation's
    non-terminal actions — this is the concrete mechanism behind "cancel the
    overall communication workflow" (see requirements.md Open Question 2).
  - Timer fires first → `ExpireActivity` calls the existing
    `Store.ExpireAgentActionIfStale` (`agent_actions.go:718-749`) — reusing
    the exact single-row expiry method the executor's own TTL re-check
    already uses, so there is still only one expiry code path.
- Every activity call, on success, additionally writes one `audit_logs` row
  via a small new `Store.InsertAuditEntry`-style call (reusing the existing
  hash-chain writer path in `store.go:1025-1096`, currently only invoked
  from `agentapi`) so `approve`/`reject`/`edit`/`cancel`/`expire` are on the
  product audit trail regardless of which path (Temporal or legacy) decided
  them — this also closes the pre-existing gap noted in "Current state"
  above (owner decisions were never audited before this proposal).

**2. Starting the workflow.** `handleProposeReply`
(`internal/agentapi/actions.go:227-238`), at the point it sets
`base.Status = db.ActionPendingApproval`, gains a feature-flag check
(`AGENT_TEMPORAL_APPROVAL_ENABLED` and the acting `user_id` present in
`AGENT_TEMPORAL_APPROVAL_TENANTS`). If enabled, after the existing insert
succeeds it starts (or no-ops onto) the `ApprovalWorkflow` via a Temporal
client call using the deterministic workflow ID above. If the Temporal
server is unreachable, the HTTP call still succeeds (the DB insert already
committed) and the existing `ExpireStaleAgentActions` sweep remains the
backstop expiry path for that row — this is the "fail safe, never silently
allow" requirement.

**3. Deciding.** `control.ParseCommand` (`command.go`) gains `CmdEdit` and
`CmdCancel`, parsed the same way `CmdApprove`/`CmdReject` are (first token
after the code is the code; for `edit`, everything after the code is the
replacement text). `control.Router` gains `handleEdit`/`handleCancel`.
For a flagged-in tenant, `handleApprove`/`handleReject`/`handleEdit`/
`handleCancel` send a Temporal signal (via a small `Signaler` interface,
mirroring the existing `Approver` interface's testability shape,
`router.go:14-24`) instead of calling the executor directly; for a
flagged-out tenant they call the executor exactly as today. `internal/
agentapi` gains parallel HTTP endpoints (`POST /actions/{id}/approve`,
`/reject`, `/edit`, `/cancel`) with an `Idempotency-Key` header, for the
"agent API/UI" exposure the issue asks for, using the same Signaler/Approver
duality.

**4. New Temporal worker process.** `cmd/temporal-worker`, following
`cmd/agent-worker`'s precedent as an independently deployable binary/image
rather than embedding the Temporal worker inside `cmd/server` — this keeps a
Temporal SDK crash or a bad workflow deploy from taking down the main HTTP
server, and lets it scale/restart independently, matching
`docs/agent-worker.md`'s stated rationale for Option C's separate process.

**5. Schema changes.** Two new nullable columns on `agent_actions`
(idempotent `addColumnIfMissing` pattern already used throughout
`agent_schema.go`): `temporal_workflow_id TEXT`, `temporal_run_id TEXT` — set
when a workflow is started, used to correlate a DB row back to Temporal
workflow history for debugging, never read by policy or the state machine
itself (backward compatible: existing rows/tenants have them NULL forever if
the flag stays off).

**6. Feature flag & rollout scoping.** `internal/config/config.go` gains
`AgentTemporalApprovalEnabled bool` (`AGENT_TEMPORAL_APPROVAL_ENABLED`) and
`AgentTemporalApprovalTenants string` (`AGENT_TEMPORAL_APPROVAL_TENANTS`,
CSV of user IDs — same `containsID`/CSV convention as
`blocked_senders`/`sender_allowlist`, `policy.go:419-430`). Both default to
off/empty, so a fresh deploy is a no-op until explicitly turned on for the
one test tenant the issue's Delivery section requires.

## Alternatives

1. **Move the entire propose → policy → execute job lifecycle into Temporal
   workflows** (one workflow per `agent_jobs` row, replacing the HTTP
   long-poll worker model). Rejected: this is a much larger blast-radius
   change touching `cmd/agent-worker`, the Agent API's job-claim contract,
   and the `agent_jobs`/`agent_job_attempts` tables that
   `docs/plans/communication-agent.md` describes as already hardened and
   validated through C1. It also risks pulling policy logic into workflow
   code (an explicit non-goal) and directly contradicts "do not remove the
   existing queue before the Temporal path is proven."

2. **Keep the current DB-sweep design and just shorten the sweep interval /
   add a dedicated signal-like mechanism (e.g. a Postgres LISTEN/NOTIFY or a
   long-poll endpoint) instead of adopting Temporal.** Rejected: the issue
   explicitly mandates Temporal for its worker-restart durability, timer,
   and history-audit properties; a hand-rolled notify mechanism would
   duplicate Temporal's crash-recovery and duplicate-signal guarantees with
   strictly more code to maintain in this repo, and would not satisfy the
   literal ask.

3. **Let Temporal own the approval decision AND execution (the workflow
   itself calls Telegram/Executor.send directly from an activity, treating
   the workflow as the new source of truth for status).** Rejected: this
   would make Temporal workflow history the only record of what happened
   (an explicit non-goal — "treating Temporal history as the only product
   audit store"), and would require re-deriving all of `Executor.send`'s
   crash-safety logic (persisted `random_id`, `ReserveAgentActionSend`'s
   atomic budget CAS) inside workflow/activity code instead of reusing the
   already-hardened, already-tested `Executor` methods. The chosen design
   keeps `Executor`/`Store` as the only code path that ever calls
   `Sender.SendWithRandomID`, with Temporal strictly upstream of it.

## Platform impact

- **New infrastructure dependency**: a Temporal server (self-hosted
  cluster in `labs`, per Open Question 1) plus its own persistence store
  (Postgres, reusing existing operational patterns rather than a new
  database technology). New GitOps service definitions in `mctl-gitops`
  (out of this repo's scope but a hard prerequisite — this repo cannot be
  deployed with the flag on until that exists).
- **Migrations**: two new nullable columns on `agent_actions`
  (`temporal_workflow_id`, `temporal_run_id`) via the existing
  `addColumnIfMissing` idempotent-ALTER pattern (`agent_schema.go:36-168`
  shows a dozen precedents for exactly this). No backfill needed — NULL for
  every pre-existing row and for every tenant that never enables the flag.
  Fully backward compatible: a rollback to a pre-Temporal binary simply
  ignores the two extra columns (matches this repo's existing "Recreate
  deployment, no dual-write compatibility required" migration posture noted
  in `agent_schema.go:84-86` for a different column, but here even weaker
  since these two columns are purely additive/optional).
- **Resource impact**: one new deployable (Temporal worker process/image,
  `cmd/temporal-worker`), plus whatever the Temporal server itself costs
  (separate from this repo's pod budget). Approval workflows are
  low-volume (one per `require_approval` action, bounded by
  `MaxAutonomousTurns`/`MaxMsgsPerMinute` policy limits already in place) —
  no meaningful load concern for the test-tenant rollout scope.
- **Risks + mitigations**:
  - *Two systems can disagree about action state.* Mitigated by keeping the
    DB row authoritative: every Temporal activity that mutates state goes
    through the same CAS-guarded `Store`/`Executor` methods the legacy path
    uses, so a workflow bug can at worst leave a row stuck in
    `pending_approval` (safe — the DB sweep still expires it), never
    double-execute (the CAS on `approved → executing` and
    `ReserveAgentActionSend`'s budget check are unchanged and still the last
    line of defense).
  - *Feature-flag leakage — a tenant's decision routed through both the
    Temporal signal path and the legacy executor path simultaneously.*
    Mitigated by making the flag check the single branch point in
    `control.Router` and `agentapi` handlers (one `if enabled` per handler,
    not per call site), and by the fact that even a double-routed decision
    is caught by the underlying CAS (only one of the two calls can win the
    `pending_approval → approved` transition).
  - *Temporal server unavailability blocking new approvals.* Mitigated by
    the "fail safe" requirement above — the DB insert (and therefore the
    owner's ability to see/approve via the DB-driven notification) always
    happens first and independently; only the durable-wait/timer
    convenience is lost, and the existing minute-scale sweep remains a
    functioning (if less precise) expiry backstop.
  - *Orphaned or leaked workflow executions for deleted accounts.*
    Mitigated by extending `HardDeleteAccount`'s purge (Open Question 6) to
    terminate any live workflow for the deleted `user_id` before purging
    `agent_actions`, plus a short Temporal-side retention policy as
    defense in depth.
  - *`edit` being used to bypass the approval TTL.* Mitigated by the
    workflow re-arming the signal wait with the *remaining* time budget
    (see Proposed solution §1), not a fresh TTL, on every edit-then-recheck
    cycle.
