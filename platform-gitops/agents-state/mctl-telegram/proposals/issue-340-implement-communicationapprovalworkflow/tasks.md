# Tasks: issue-340-implement-communicationapprovalworkflow

- [ ] 1. Add `go.temporal.io/sdk` (and `go.temporal.io/api` transitively) to
      `go.mod`/`go.sum`; add a `Temporal` config block to `internal/config`
      (host:port, namespace, task queue name, feature-flag fields
      `AgentCommsWorkflowEnabled` / `AgentCommsWorkflowTenantIDs`) following
      the existing `config.Config` field/env-var conventions — DoD: `go build
      ./...` succeeds with the new dependency; new config fields have doc
      comments and default to disabled/empty; `go vet ./...` and
      `golangci-lint` pass.
- [ ] 2. Add `internal/db/comms_schema.go` with `comms_approval_workflows` and
      `comms_approval_decisions` tables (SQLite + Postgres variants), hooked
      into `Migrate()` alongside `migrateAgent`, using the existing
      `addColumnIfMissing`/idempotent `CREATE TABLE IF NOT EXISTS` pattern —
      DoD: fresh-DB migration and re-run-on-existing-DB migration both pass
      in a test (mirrors `internal/db/agent_schema.go`'s own test coverage
      style); no existing table's DDL changes.
- [ ] 3. Define `internal/comms` package types: `WorkflowInput`,
      `DecisionSignal` (with `signal_version`), `approvalState` enum and the
      `nextState(current, event) (next, ok)` transition table matching the
      issue's state diagram exactly, `ids.go` workflow/approval ID
      construction — DoD: table-driven unit tests cover every documented
      transition (`proposed -> waiting_approval -> approved -> executing ->
      completed|failed`, `edited -> validating -> waiting_approval|
      executing|denied`, `rejected`, `cancelled`, `expired`) and reject every
      undocumented transition.
- [ ] 4. Implement `Activities`: `PolicyEvaluateActivity` (wraps
      `internal/agent/policy.Evaluate`), `RevalidateActivity`
      (tenant/account ownership, capability, peer identity, proposal
      version, policy version, kill switch — mirrors
      `internal/agent/executor.send`'s pre-send checklist),
      `ExecuteActionActivity` (idempotent send via the existing
      `send_random_id` primitive/narrow `Sender` interface, not a new send
      implementation), `AuditActivity` (writes to `comms_approval_decisions`
      / `comms_approval_workflows` and to the existing hash-chained
      `audit_logs` via `Store.LogToolCall` or an equivalent) — DoD: each
      Activity has its own `RetryPolicy` (not a workflow-level blanket
      retry); non-retryable failures (policy deny, stale revision, kill
      switch on) return `temporal.NewNonRetryableApplicationError`; unit
      tests use `testsuite.WorkflowTestSuite`'s activity environment with
      mocked dependencies.
- [ ] 5. Implement `CommunicationApprovalWorkflow` in `workflow.go`: signal
      channel + `workflow.NewTimer` selector for `waiting_approval`, decision
      handling for `approve`/`reject`/`edit`/`cancel` per design.md, query
      handler `GetStatus`, Continue-As-New on an edit-count/history-length
      threshold (depends on 3, 4) — DoD: workflow code contains no direct
      I/O, no `time.Now()`/`math/rand` calls, no map iteration order
      dependency; all such calls are pushed into Activities or
      `workflow.Now`/`workflow.SideEffect`.
- [ ] 6. Implement duplicate/stale/conflicting-signal handling exactly as
      specified: reject `expected_revision` mismatch, reject `approval_id`
      mismatch, ignore duplicate `request_id` (depends on 5) — DoD: unit
      tests send two decisions for the same revision and assert only the
      first is accepted; a duplicate `request_id` after a decision already
      applied does not re-trigger `ExecuteActionActivity`.
- [ ] 7. Wire the feature-flag branch at the `require_approval` call site
      (propose_reply / `request_owner_approval` path in `internal/agentapi`)
      so a flagged tenant/account starts (or signal-with-starts)
      `CommunicationApprovalWorkflow` instead of creating an `agent_actions`
      pending-approval row, while every non-flagged tenant is unaffected
      (depends on 5) — DoD: an integration test proves both branches:
      flagged tenant reaches a running workflow (verifiable via the query
      handler), non-flagged tenant's existing `agent_actions` CAS flow is
      bit-for-bit unchanged (existing `internal/agentapi` tests still pass
      unmodified).
- [ ] 8. Add `cmd/comms-worker` (new binary, modeled on `cmd/agent-worker`'s
      structure) that connects to Temporal, registers
      `CommunicationApprovalWorkflow` and its Activities on an explicit named
      task queue, and a matching `Dockerfile.comms-worker` (depends on 5, 6)
      — DoD: binary builds; worker registration uses a config-driven task
      queue name, never the SDK default; `docker build -f
      Dockerfile.comms-worker .` succeeds locally.
- [ ] 9. Approval-expiry timer coverage: assert `expired` fires exactly once
      when no decision arrives before the durable timer, using
      `testsuite.TestWorkflowEnvironment`'s time-skipping (depends on 5) —
      DoD: test advances virtual time past the TTL and asserts terminal
      state `expired` and exactly one `AuditActivity` call for the
      expiry transition.
- [ ] 10. Worker/pod-restart survival test: start a workflow, simulate a
      worker restart (new `TestWorkflowEnvironment`/replay from persisted
      history), and confirm the workflow resumes waiting in the same state
      (depends on 5) — DoD: test asserts `waiting_approval` state and
      `approval_revision` are identical before and after the simulated
      restart.
- [ ] 11. Commit a Temporal replay test against a checked-in workflow history
      fixture (`internal/comms/testdata/*.json` captured from a real run),
      per the issue's explicit "Temporal replay test passes against
      committed workflow histories" acceptance criterion (depends on 5) —
      DoD: `go test` includes a replay test using
      `worker.ReplayWorkflowHistoryFromJSONFile` (or equivalent) against the
      committed fixture; CI fails if a future workflow-code change breaks
      determinism against that history.
- [ ] 12. Update `docs/plans/communication-agent.md` with a new section
      documenting the Temporal path (feature flag, task queue name, new
      tables, scope boundary with #341) so the plan file remains the single
      canonical source, per its own stated purpose (depends on 7, 8) — DoD:
      section added, cross-references #339/#340/#341, states current
      flagged/test-tenant-only status.

## Tests

- [ ] T1. Unit: `nextState` table covers every documented transition and
      rejects every undocumented one (task 3).
- [ ] T2. Unit/replay: `approve` — happy path executes exactly once and
      reaches `completed` (task 5, 6).
- [ ] T3. Unit/replay: `reject` — terminates without any `ExecuteActionActivity`
      call (task 5, 6).
- [ ] T4. Unit/replay: `edit` — creates a new `approval_revision`, re-runs
      `PolicyEvaluateActivity`, and correctly routes to either
      `waiting_approval` or `executing` depending on the mocked policy
      result; a case where policy again requires approval after edit is
      explicitly asserted (not implied) (task 5, 6).
- [ ] T5. Unit/replay: `cancel` — before execution starts, terminates
      cleanly with no side effect; after `ExecuteActionActivity` has been
      dispatched, a subsequent `cancel` signal cannot undo the already
      committed send (task 5, 6).
- [ ] T6. Duplicate `request_id` for an already-applied decision is a no-op
      (no second `ExecuteActionActivity` call, no second terminal audit
      event) (task 6).
- [ ] T7. Stale `expected_revision` signal is rejected without state change
      (task 6).
- [ ] T8. Signal with mismatched `approval_id` is rejected without state
      change (task 6).
- [ ] T9. Approval-timeout produces `expired` exactly once, even if the
      timer and a late-arriving signal race (task 9).
- [ ] T10. `ExecuteActionActivity` is idempotent under Activity retry
      (simulate a retry after a transient failure and assert no duplicate
      external send, mirroring `internal/agent/executor`'s existing
      `send_random_id` dedup test pattern) (task 4).
- [ ] T11. Query handler (`GetStatus`) returns state, current revision,
      expiry, and terminal result correctly at each state and never mutates
      workflow state (task 5).
- [ ] T12. Worker/pod restart: workflow resumes waiting in the identical
      state and revision after a simulated restart (task 10).
- [ ] T13. Replay test against the committed workflow-history fixture passes,
      and is wired into CI (`go test ./internal/comms/...`) (task 11).
- [ ] T14. Feature-flag integration test: flagged tenant/account routes to
      the workflow; every other tenant/account's existing `agent_actions`
      flow and its existing test suite are unaffected (task 7).
- [ ] T15. RevalidateActivity denies execution when tenant/account
      ownership, capability, peer identity, proposal version, policy
      version, or kill switch has changed since approval — one test per
      condition (task 4).
- [ ] T16. `go vet ./...`, `golangci-lint`, and `go test -race
      ./internal/comms/...` all pass, matching the repo's existing
      per-PR verification convention (`docs/plans/communication-agent.md`'s
      "Verification" sections).

## Rollback

The feature flag (`AgentCommsWorkflowEnabled` / tenant allowlist) is the
primary rollback lever: setting it back to disabled/empty routes all new
`require_approval` proposals back through the untouched
`agent_actions`/`internal/agent/executor` path immediately, with zero schema
rollback required, because no existing table was modified (only two new,
additive tables were created). Any workflow already running in Temporal at
disable time is left to finish or expire on its own durable timer — it does
not need to be forcibly terminated, since Activities gate every external
side effect through the same revalidation used by the existing path, so an
in-flight workflow completing after rollback cannot bypass current policy or
kill-switch state. If `cmd/comms-worker` itself needs to be pulled (e.g. a
Temporal SDK or infra issue), scaling it to zero replicas stops it from
executing Activities; workflows stay durably parked in Temporal (waiting on
their signal/timer) with no data loss, and can be resumed by redeploying the
worker once fixed, or left to expire via their existing TTL timer if the
decision is to abandon the Temporal path entirely. The two new tables
(`comms_approval_workflows`, `comms_approval_decisions`) can be dropped
independently at any time without touching `agent_actions`/`agent_jobs`,
since they are a read-side projection/audit trail, not a foreign-keyed
dependency of any existing table.
