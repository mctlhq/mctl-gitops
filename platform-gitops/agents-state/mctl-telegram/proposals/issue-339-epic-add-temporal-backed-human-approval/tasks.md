# Tasks: issue-339-epic-add-temporal-backed-human-approval

- [ ] 1. Provision a Temporal server + persistence store reachable from
      `mctl-telegram`'s deployment (self-hosted in `labs`, per
      requirements.md Open Question 1; tracked/executed in `mctl-gitops`,
      out of this repo but a hard prerequisite) — DoD: a Temporal namespace
      exists, is reachable from a `labs` pod, and a smoke-test workflow can
      be started and completed against it manually (e.g. via `tctl`/`temporal`
      CLI).
- [ ] 2. Add `go.temporal.io/sdk` to `go.mod`/`go.sum`; confirm it builds
      clean under `go vet ./...` and does not pull in anything the
      Dockerfile's multi-stage build can't vendor — DoD: `go build ./...`
      succeeds with the new dependency present and unused.
- [ ] 3. Add `agent_actions.temporal_workflow_id` / `temporal_run_id`
      nullable columns via `addColumnIfMissing` in
      `internal/db/agent_schema.go`, both dialects — DoD: fresh and
      already-migrated (sqlite and Postgres) test DBs both apply cleanly;
      existing `agent_schema_test.go` still passes; new columns default
      NULL and are never read by `policy.Evaluate` or the state machine.
- [ ] 4. Add `Store.UpdateAgentActionPayload(ctx, userID, id int64,
      newPayload string) (bool, error)` — CAS-guarded on `status =
      pending_approval`, reseals the payload with `Crypt.SealForUser`,
      leaves status unchanged — DoD: unit test proves it no-ops (returns
      `false`) against a non-`pending_approval` row, matching
      `UpdateAgentActionStatus`'s existing CAS-loss convention.
- [ ] 5. Extract `Executor.ApproveActionID(ctx, userID, actionID int64)
      error` and `Executor.RejectActionID(ctx, userID, actionID int64)
      error` from the code-lookup logic already in `Approve`/`Reject`
      (`executor.go:147-214`), and reimplement `Approve`/`Reject` (the
      code-typed entry points `/mctl approve|reject` use) as thin wrappers
      that resolve the code to an ID first — DoD: existing `executor_test.go`
      passes unmodified in behavior (same error sentinels,
      `ErrApprovalCodeNotFound`/`ErrLostRace`/`ErrApprovalExpired`); no
      second approval implementation exists.
      (depends on: none)
- [ ] 6. Add `Executor.EditAndApprove(ctx, userID, actionID int64,
      newPayload string) error`: loads the action, re-runs
      `policy.Evaluate` against `newPayload`, and on non-`Deny` calls
      `UpdateAgentActionPayload` then `ApproveActionID`; on `RequireApproval`
      returns a typed `ErrEditRequiresApproval` (distinct from a hard
      failure) that callers can distinguish from `Deny` — DoD: table-driven
      test covering allow/deny/require_approval outcomes for the revalidated
      text, mirroring `policy_test.go`'s existing style.
      (depends on: 4, 5)
- [ ] 7. Implement `internal/agent/approvalflow` package: `ApprovalWorkflow`,
      the `decision` signal type, `DecideActivity`/`ExpireActivity`, and the
      deterministic `agent-approval-{user_id}-{action_id}` workflow ID
      scheme — DoD: workflow unit tests using
      `go.temporal.io/sdk/testsuite` cover approve, reject, edit
      (require_approval loop-back with remaining TTL, not a fresh one),
      cancel, timer-fires-first (expiry), duplicate signal after a decision
      is discarded, and a simulated worker restart (replay) producing the
      same terminal outcome.
      (depends on: 5, 6)
- [ ] 8. Wire `Store.DenyPendingActionsForConversation`
      (`agent_actions.go:827-842`, already used by `/mctl takeover`) into
      the `cancel` activity path — DoD: integration test proves `cancel`
      denies sibling non-terminal actions in the same conversation, not just
      the signaled action, while `reject` on the same fixture leaves
      siblings untouched.
      (depends on: 7)
- [ ] 9. Audit every Temporal-driven transition
      (approve/reject/edit/cancel/expire) through the existing hash-chain
      writer (`store.go:1025-1096`), and — as a corequisite bug fix
      unrelated to Temporal but required for acceptance criterion "every
      transition is available through the product audit API" — also audit
      the legacy (non-Temporal) `/mctl approve|reject` decisions, which are
      not currently written to `audit_logs` — DoD: `VerifyAuditChain` passes
      after a full approve/reject/edit/cancel/expire cycle on both the
      Temporal and legacy paths; `GET /api/audit` shows every transition for
      a test account with entries distinguishable by `tool_name`.
      (depends on: 5, 7)
- [ ] 10. Add `AgentTemporalApprovalEnabled` /
      `AgentTemporalApprovalTenants` to `internal/config/config.go`
      (env-var + CSV convention matching `blocked_senders`) — DoD: config
      test confirms default-off, and a tenant not in the CSV never touches
      the Temporal client even when the global flag is on.
      (depends on: none)
- [ ] 11. Wire workflow start into `handleProposeReply`
      (`internal/agentapi/actions.go`) behind the flag from Task 10, with
      fail-safe behavior when the Temporal client errors (DB insert already
      committed; log and continue, do not fail the HTTP call) — DoD:
      integration test with a fake/unreachable Temporal client proves the
      HTTP response and DB row are unaffected by a Temporal start failure.
      (depends on: 7, 10)
- [ ] 12. Extend `control.ParseCommand`/`control.Router` with
      `CmdEdit`/`CmdCancel` and a `Signaler` interface (mirroring
      `Approver`), routing through Temporal signals when the flag is on and
      through the Task 5/6 executor methods directly when it is off — DoD:
      `command_test.go`/`router_test.go` cover both flag states for all four
      decision types, including the not-a-command-yet `/mctl edit <code>
      <text>` parsing (only the first token after the code is the code,
      matching the existing approve/reject convention documented in
      `command.go:72-78`).
      (depends on: 6, 7, 10)
- [ ] 13. Add `POST /actions/{id}/approve|reject|edit|cancel` to
      `internal/agentapi`, `Idempotency-Key`-aware, same Signaler/executor
      duality as Task 12 — DoD: `server_test.go`-style tests cover aud
      enforcement (existing `aud=agent` pattern), idempotent replay, and both
      flag states.
      (depends on: 12)
- [ ] 14. Build `cmd/temporal-worker` as an independently deployable
      binary/image, following `cmd/agent-worker`'s existing
      separate-process/separate-image precedent (`Dockerfile.agent-worker`)
      — DoD: `docker build` succeeds for a new `Dockerfile.temporal-worker`;
      the binary connects to a Temporal namespace and registers
      `ApprovalWorkflow`/its activities; a health endpoint exists mirroring
      `cmd/agent-worker/health_server.go`.
      (depends on: 7)
- [ ] 15. Extend `HardDeleteAccount`'s purge path to terminate any live
      Temporal workflow for the deleted `user_id` before purging
      `agent_actions` (requirements.md Open Question 6) — DoD: test proves a
      workflow started for a test user is terminated (not merely
      orphaned) when that account is hard-deleted.
      (depends on: 7)
- [ ] 16. Update `docs/plans/communication-agent.md` and
      `docs/runbook.md` with the Temporal rollout stage (flag names, test
      tenant, kill-switch/rollback procedure) — DoD: runbook has an explicit
      "Temporal approval flow" section with the same level of detail as the
      existing kill-switch/replica-boundary sections.
      (depends on: 10-14)

## Tests

- [ ] T1. Workflow unit tests (Task 7) for all four decisions plus expiry,
      using `testsuite.WorkflowTestSuite` — no real Temporal server needed.
- [ ] T2. Duplicate-decision test: two signals (approve then reject, or two
      approves) delivered to the same workflow — assert only the first is
      acted on and the DB CAS independently rejects a hypothetical second
      execution attempt even if workflow-side dedup were bypassed.
- [ ] T3. Stale-decision test: a signal delivered after the timer has
      already fired and expired the action — assert no execution, and that
      this matches the outcome of a signal that arrives concurrently with
      expiry (race both orderings in the test).
- [ ] T4. Restart/replay test: simulate a worker crash mid-wait (Temporal
      test env history replay) and confirm the resumed workflow reaches the
      same terminal state with no owner-visible loss.
- [ ] T5. Edit-then-revalidate test: edited payload that now contains a URL
      (policy denies) must not execute; edited payload that now trips
      `require_approval` (e.g. exceeds `MaxAutonomousTurns`) must return the
      workflow to waiting with the *remaining* TTL, not a fresh one — assert
      via a controllable test clock that the total wait window never exceeds
      the original `AGENT_APPROVAL_TTL`.
- [ ] T6. Cancel-vs-reject scope test: `cancel` denies sibling pending
      actions in the same conversation; `reject` does not.
- [ ] T7. Feature-flag isolation test: with the flag on for tenant A and off
      for tenant B, a `require_approval` action for B never starts a
      workflow and never calls the Temporal client; an unreachable Temporal
      server does not block or fail tenant B's flow at all.
- [ ] T8. Audit-completeness test: full approve/reject/edit/cancel/expire
      cycle (both flagged-in and flagged-out) produces a verifiable
      (`VerifyAuditChain`) `audit_logs` entry for every transition,
      retrievable via `GET /api/audit`.
- [ ] T9. Idempotent-start test: `handleProposeReply` called twice for the
      same job-tied action (simulating an at-least-once queue redelivery,
      matching the existing `InsertAgentAction` idempotency contract) starts
      at most one live workflow execution for that action ID.
- [ ] T10. Existing non-approval regression suite: `go test -count=1 ./...`,
      `go vet ./...`, and the existing adversarial policy tests
      (`internal/agent/policy/adversarial_output_test.go`) must still pass
      unmodified — this proposal must not change `Allow`/`Deny` behavior for
      any tenant, flagged in or out.

## Rollback

1. **Immediate (no deploy needed):** set `AGENT_TEMPORAL_APPROVAL_ENABLED=false`
   or remove the test tenant from `AGENT_TEMPORAL_APPROVAL_TENANTS`. New
   `require_approval` actions for that tenant immediately fall back to the
   existing DB-sweep-and-command-router path (Task 11/12/13's `if enabled`
   branches). This is the same posture the runbook already documents for
   `AGENT_KILL_SWITCH`.
2. **In-flight workflows when disabling:** any `ApprovalWorkflow` already
   running for that tenant continues to run to completion (approve, reject,
   edit, cancel, or timer-expiry) — it does not need to be killed, because
   every activity it can call is the same CAS-guarded `Store`/`Executor`
   method the legacy path uses, so it cannot execute anything the legacy
   path itself would forbid. If an immediate stop is required anyway (e.g. a
   workflow bug), terminate the specific workflow ID via the Temporal
   CLI/UI — the DB row is left in `pending_approval` and the existing
   `ExpireStaleAgentActions` sweep expires it on schedule, exactly as if
   Temporal had never been involved.
3. **Full revert:** redeploy the pre-Temporal binary. The two new
   `agent_actions` columns (`temporal_workflow_id`/`temporal_run_id`) are
   inert and ignored; no data migration is required to go backward. Scale
   `cmd/temporal-worker` to zero or delete its deployment; the Temporal
   server itself can be left running (idle) or torn down independently since
   nothing in the main server or agent-worker path depends on it once the
   flag is off.
4. **Schema rollback is never required.** Per this repo's existing migration
   posture (additive `addColumnIfMissing`, no destructive changes), a full
   rollback needs no `DOWN` migration — the new columns simply go unused.
