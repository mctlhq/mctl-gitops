# Tasks: issue-935-design-workitems-controlled-lease-aware

Implementation needs a separate approval of this proposal. No release, deployment or flag change is part of any
task.

- [ ] 1. Add the switch `MCTL_EXECUTION_REQUEST_OPERATOR_DRAIN`: create `ParseOperatorDrain` and `WithOperatorDrain`
  next to `internal/workitems/queue_switch.go`, read it in `cmd/api/main.go` the way `QueueWhileActiveEnv` is read
  (around line 1889), and fail startup on an invalid value. DoD: unit test for `""`, `off`, `on` and an invalid
  value; the default is off.
- [ ] 2. Make the schema additions in `executionRequestSchema` (`internal/workitems/execution_requests.go`):
  `revision`, `rejected_by`, `rejected_by_principal_id`, and `rejection_kind` with its CHECK. Add them to
  `executionRequestColumns`, `scanExecutionRequest` and `ExecutionRequest`, with `revision` serialized and
  `claim_token` still `json:"-"` (depends on nothing). DoD: `EnsureSchema` is idempotent on a fresh database and
  on an existing one; existing tests pass.
- [ ] 3. Bump `revision` in the claim, fulfil and dispatcher-reject UPDATEs. The dispatcher reject also sets
  `rejection_kind='claimant'`. In the `ExecutionRequestRejected` branch of `RejectExecutionRequest`, return
  `ClosedRequestError` when `rejection_kind='operator'` (depends on 2). DoD: the existing
  `execution_requests_test.go` tests pass, and new assertions check the revision increments.
- [ ] 4. Add `OpenExecutionRequests` to the store, with a keyset cursor on `(created_at, id)`, an optional tenant
  and state filter, a limit of 1..100, `open_execution_id`, and the item's tenant, state, state_version,
  visibility and owner (depends on 2). DoD: one bounded query; `EXPLAIN` uses
  `work_item_execution_requests_claimable`.
- [ ] 5. Add `OperatorRejectExecutionRequest` to the store, using `lockedRequest`, `replayed`/`remember`, the
  ordered checks (replay, closed, revision, live claim) and the guarded UPDATE that clears `claim_token`. Append
  the `execution_request_operator_rejected` event without reason text or token, and add the typed errors
  `RevisionMovedError` and `ClaimLiveError` (depends on 2, 3). DoD: no write to executions, approvals or item
  state, verified by test.
- [ ] 6. Add the `operatorDrain` gate (`isHumanAdmin`, failed audit on refusal) and the handlers for
  `GET /api/v1/execution-requests/open` and `POST /api/v1/execution-requests/{request_id}/operator-reject` in a
  new `internal/api/handlers_execution_request_drain.go`. This includes the opaque cursor with a filter hash,
  `canSeeWorkItem` per row, `requireWorkItemRole(..., operations.RoleAdmin, ...)`, a `claim_token` body
  refusal, and the error mapping 409 `execution_request_claim_live`, 412 `execution_request_revision_moved` and
  409 `execution_request_closed`. Audit with `RiskHigh` on success (depends on 4, 5). DoD: handler tests for
  each status code.
- [ ] 7. Mount both routes in `internal/api/router.go` in the execution-requests rate-limit group, only when the
  switch is on. When it is off, the routes answer 404 (depends on 1, 6). DoD: router test for on and off.
- [ ] 8. Add the routes, schemas and typed codes to the OpenAPI spec (`internal/openapi`), and document the
  operator procedure and rollback-evidence checklist in `docs/` (depends on 6). The docs must say explicitly that
  "pause dispatcher -> list -> reject by id" is invalid. DoD: the OpenAPI lint and tests pass, and the doc is
  reviewed.
- [ ] 9. Run `go fmt`, `go vet`, `golangci-lint` and `go test ./...` with `TEST_DATABASE_URL` set (depends on all).
  DoD: green.

## Tests
Real PostgreSQL (`TEST_DATABASE_URL`, as in `internal/workitems/execution_requests_test.go`):
- [ ] T1. Pending: operator-reject with the right revision moves the request to rejected; `revision` goes up by
  one; the event and the `rejected_by` column are set; the item's `state_version` and executions are unchanged;
  a new request can be created for the item afterwards.
- [ ] T2. Claimed with a live lease: the request is refused with 409 `claim_live` and the row is unchanged. The
  lease is then expired (clock injection, `s.now`), and the same call with the same revision succeeds.
- [ ] T3. Claimed with an expired lease: rejected. The former holder's fulfil then returns `ClosedRequestError`,
  and its reject also returns `ClosedRequestError`, never `Succeeded` or an attached execution.
- [ ] T4. Wrong claimant or token: the existing dispatcher reject and fulfil with a stale token after an operator
  reject are both refused, and no execution is created. The operator route never accepts `claim_token` (400).
- [ ] T5. Revision moved: discovery reads revision N, a service claim re-claims the lapsed request (N+1), and
  operator-reject with N returns 412 with the current revision and lease state.
- [ ] T6. Retries: the same actor, key and body replays with `replayed: true` and writes no second event; the
  same key with a different reason returns 409 `idempotency_key_reused`; a different key on a rejected request
  returns 409 closed.
- [ ] T7. Two dispatchers plus an operator: two goroutines loop claim and lease-lapse against the same request
  while the operator rejects with the latest observed revision. Exactly one terminal transition happens; there
  is never a fulfilled-and-rejected row; the one-open index holds.
- [ ] T8. Concurrent fulfil and operator reject: a holder fulfils at the instant its lease lapses, racing an
  operator reject under the advisory lock. Exactly one wins, and the loser gets a typed 409 or 412.
- [ ] T9. Mid-drain failure: the transaction aborts after the UPDATE (forced error in `appendEvent` through a
  test hook, or the connection is cancelled). The row stays open at the old revision, with no event and no audit
  entry. The retry with the same key succeeds once.
- [ ] T10. Discovery paging: with 250 open requests across 3 tenants, limit 50, and requests created while the
  walk runs, every row open at the start is returned exactly once. New rows appear at the tail. The filter-hash
  mismatch returns 400. Requests queued behind an open execution are listed with `open_execution_id` while
  queue-while-active is on, even though `ClaimExecutionRequest` skips them.
- [ ] T11. Authorization: the service principal, a relayed surface, a surface identity and a non-admin human all
  get 403 with a failed audit entry. No response or audit entry contains `xc_` tokens (grep the serialized
  output).
- [ ] T12. Switch off: both routes return 404, and the claim, fulfil and reject behaviour is byte-identical to
  today, apart from the new fields.

E2E (`e2e/`):
- [ ] T13. Create a request, claim it as the service principal, let the lease lapse, operator-reject it, then
  re-claim (204, nothing claimable) and fulfil with the old token (409 closed). Assert that the work item has no
  new execution and no `Succeeded` phase, and that the audit log contains the operator reject.

## Rollback
- The capability is inert until the switch is `on`. To roll back the behaviour, set it to `off` or remove it;
  the routes then disappear.
- To roll back the code, revert the change. The added columns are additive and defaulted, and older binaries
  ignore them, so no down-migration is required. Rows already rejected by an operator stay `rejected`. That is
  intended: a rejected request is terminal, and the requester can create a new one.
- If the revision bump in the existing paths causes an issue, revert task 3 alone. The operator UPDATE still
  re-checks state and lease under the item lock. Disable the drain until task 3 is restored.
