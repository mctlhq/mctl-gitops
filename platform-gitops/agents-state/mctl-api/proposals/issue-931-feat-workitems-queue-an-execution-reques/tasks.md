# Tasks: issue-931-feat-workitems-queue-an-execution-reques

- [ ] 1. Add the switch. In `internal/workitems/queue_switch.go`, add
  `QueueWhileActiveEnv`, `ParseQueueWhileActive` and `WithQueueWhileActive`, and the
  `Store.queueWhileActive` field. In `cmd/api/main.go`, wire the config field, read the
  variable, validate it in `validate()` and pass the option to `workitems.NewStore`.
  - DoD: an invalid value refuses to start; empty means off; there are unit tests for the
    parser.
- [ ] 2. (depends on 1) Refactor `checkRunnable` to take `allowActive` and return the
  blocking execution id. `checkStart` passes false.
  - DoD: all existing `internal/workitems` tests pass unchanged.
- [ ] 3. (depends on 2) In `CreateExecutionRequest`, queue the request when the switch is
  on and the only blocker is an open execution:
  - add `queued_behind_execution_id` to the `execution_requested` event detail;
  - add the non-persisted response field;
  - make no change to replay, remember, the lock or the one-open index.
  - DoD: switch-on create returns 201 `pending`; switch-off create returns 409
    `execution_active` and stores nothing.
- [ ] 4. (depends on 1) Add the claim guard in `ClaimExecutionRequest`: a `NOT EXISTS`
  open-execution filter in the candidate SQL, plus a re-check under the item lock before
  the compare-and-set. Both apply only when the switch is on.
  - DoD: when the switch is off, the SQL string is identical to today's (asserted in a
    test).
- [ ] 5. (depends on 1) Add the orphan store methods `OpenExecutionsWithQueuedRequests`
  and `CloseOrphanedExecution` (compare-and-set on phase to `Error`, plus the
  `execution_orphan_closed` event) in `internal/workitems/orphans.go`.
  - DoD: a terminal execution is never modified.
- [ ] 6. Add `DescribeDevLoopRun(ctx, wf, runID)` to `temporalclient.Client`, to
  `Reconnecting` and to the `DevLoopClient` interface, with `ErrRunNotFound`. Update the
  fakes in the `internal/api` tests.
  - DoD: `go vet` is clean and the mock test covers not-found.
- [ ] 7. (depends on 5, 6) Add the sweeper `ReconcileOrphanedExecutions` in
  `internal/api/execution_orphan_reconciler.go`, started from `cmd/api/main.go` on a
  2-minute ticker only when the switch is on and both Temporal and the store are
  configured. It uses a 5-minute minimum age and a limit of 20, parses `engine_ref`, and
  fails closed on Running, ContinuedAsNew, Unknown and errors.
  - DoD: the sweeper unit tests pass with a fake `DevLoopClient` and real Postgres.
- [ ] 8. Docs: update `internal/openapi/openapi.yaml`, `docs/work-context-contract.md`
  (the Execution requests section) and the MCP tool text at `internal/mcp/workitems.go`
  around line 171, and add `docs/adr/0001-queue-execution-request-while-active.md`.
  - DoD: the docs match the behaviour. The MCP tool count is unchanged (`server_test.go`).
- [ ] 9. Run `go fmt`, `go vet`, `golangci-lint` and `go test ./...` with
  `TEST_DATABASE_URL` set.
  - DoD: everything is green, and the Postgres-backed tests ran rather than skipped.

## Tests

All tests below run against real PostgreSQL (`TEST_DATABASE_URL`), modelled on
`internal/workitems/execution_requests_test.go` and `store_test.go`, unless noted.

- [ ] T1. With the switch off, a resume create on an item with a Running execution
  returns `ConflictError{ErrExecutionActive}`. Afterwards there is no request row, no
  `execution_requested` event, and a retry with the same key is still refused (nothing
  was remembered).
- [ ] T2. With the switch on, the same create returns a `pending` request with the
  original `requested_by`, principal ids, surface, `intent_id`,
  `resumed_from_execution_id`, `expected_state_version` and `idempotency_key`. The event
  carries `queued_behind_execution_id`.
- [ ] T3. With the switch on, a replay with the same key and body returns
  `created=false`, both while the execution is open and after it closes, and the item has
  exactly one request row. The same key with a different body returns
  `ErrIdempotencyKeyReuse`.
- [ ] T4. With the switch on, the other refusals are unchanged: stale version, terminal
  item, start kind while an execution is open, unknown `resumed_from_execution_id`,
  redacted intent, and a second open request (`execution_request_open`).
- [ ] T5. With the switch on, claim returns nil while the execution is Running (whether
  the request is pending or claimed with a lapsed lease) and writes no claim event.
  Another item's unblocked request behind eight blocked ones is still claimed.
- [ ] T6. Table test over the four outcomes. The execution ends through
  `AttachExecution` as Succeeded, Failed, Error (cancel) and Error (timeout). After each,
  claim returns the queued request with its fields unchanged, and fulfil attaches exactly
  one new execution that resumes from the ended one.
- [ ] T7. With the switch on, when the item's `state_version` advances (a Transition)
  after the request was queued, fulfil returns `state_version_conflict`, attaches no
  execution, and the request can be rejected by the holder.
- [ ] T8. A race between the scan and the lock: an execution is attached between the
  candidate scan and the lock (simulated by attaching before the per-candidate
  transaction through a test hook), and the claim skips the candidate.
- [ ] T9. Orphan sweeper (real Postgres, fake `DevLoopClient`). The execution is closed
  to `Error` for each Temporal status Completed, Failed, Canceled, Terminated, TimedOut
  and `ErrRunNotFound`, after which the queued request becomes claimable. It is left open
  for Running, ContinuedAsNew, Unknown, a describe error, and a latest run that started
  after the execution. It is left alone when there is no queued request or the execution
  is younger than the minimum age.
- [ ] T10. A `CloseOrphanedExecution` compare-and-set: when the loop reports Succeeded
  first, the sweeper's close returns `closed=false` and the phase stays Succeeded.
- [ ] T11. `TestDevLoopApprove_SecondGrantOnOpenExecutionAfterFlip` in
  `internal/api/handlers_dev_loop_grant_test.go`. Using `startDevLoopRun`, the test
  requests and approves the first grant through `approveDevLoop`, asserts the execution
  is still Running, requests a second grant with `requestDevLoopGrant` under a new key,
  and approves it through `approveDevLoop` bound to the second `aar_`. The newest grant
  is decided, and the first stays decided and unchanged.
- [ ] T12. Unit tests for `ParseQueueWhileActive` (`""`, `off`, `on`, invalid) and a
  `cmd/api` `validate()` test showing that an invalid value refuses to start.

## Rollback

- Set `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE` to `off` (or unset it) in the mctl-api
  deployment and restart. Create returns 409 `execution_active` again, the claim guard is
  dropped and the sweeper stops.
- Requests already queued stay `pending` and are valid rows. With the guard off they are
  claimable, and fulfil refuses them with `execution_active` (deferred by the dispatcher)
  until the execution ends, which is today's fulfil behaviour.
- No schema change was made, so reverting the release is safe. The
  `execution_orphan_closed` events and the executions moved to `Error` remain as an audit
  history.
- mctl-agents#992 must stay in draft or disabled while the switch is off, as the rollout
  gate requires.
