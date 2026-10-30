# Tasks: issue-586-fix-audit-getbyworkflow-reports-a-failed

- [ ] 0. Check whether mctl-api#585 has merged (`grep -rn LookupByWorkflow internal/`). If it has, migrate the callers to `LookupByWorkflow`, delete `GetByWorkflow`, and skip the signature change in task 1. Every other task still applies. — DoD: the decision is recorded in the PR body.
- [ ] 1. In `internal/audit/logger.go`, change the `Log` interface to `GetByWorkflow(ctx context.Context, name string) (*Entry, error)` and `ListByStatus(...) ([]Entry, error)`. Update the in-memory `Logger` to return a `nil` error. — DoD: `Logger` compiles against the new interface, with the same lookup semantics.
- [ ] 2. Add `ParametersUnreadable bool` (`json:"-"`) to `audit.Entry`, with a doc comment explaining the marker-over-error choice. (depends on 1) — DoD: the field exists and is not serialized.
- [ ] 3. Update `internal/audit/postgres.go`: (depends on 1, 2) — DoD: `go vet ./internal/audit` is clean.
  - (a) `GetByWorkflow` derives its 5 s timeout from the caller's ctx. `pgx.ErrNoRows` gives `(nil, nil)`, and any other error gives a wrapped `(nil, err)`.
  - (b) `scanAuditEntry` sets `ParametersUnreadable` and logs the id and the error when params fail to decode.
  - (c) `ListByStatus` returns an error on a query failure and on `rows.Err()`, and still logs and skips individual scan failures.
- [ ] 4. Update `GetWorkflow` in `internal/api/handlers_read.go` to pass `r.Context()`. On an audit error, log it and return 503 "audit log unavailable, workflow may exist" before the cron fallback. On `ParametersUnreadable`, log it and return 503. (depends on 3) — DoD: the healthy-path code is unchanged, and the cron fallback runs only for `(nil, nil)`.
- [ ] 5. Update the non-admin gate in `GetWorkflowLogs`: an audit error or `ParametersUnreadable` is logged and returns 503. (depends on 3) — DoD: 403 "no owning team" is only reachable for `(nil, nil)` or an entry with no tenant.
- [ ] 6. Update `internal/api/audit_reconcile.go`: (depends on 3) — DoD: the reconciler compiles, and the existing reconcile tests pass.
  - `reconcileOnce` logs a `ListByStatus` error and ends the pass.
  - `reconcileBatch` skips `ParametersUnreadable` rows with a warning, so they are never expired from a wrong namespace.
- [ ] 7. Fix the remaining compile fallout: about 16 test call sites of `GetByWorkflow` and any `ListByStatus` callers, for example with a small `mustGetByWorkflow(t, log, name)` helper in each test package. (depends on 1) — DoD: `go build ./... && go vet ./...` pass.
- [ ] 8. Write the PR body. It covers the sweep result (`Log.List` and its three handlers listed as a follow-up), the #585 decision, and the mutation proof for each regression test: the mutation applied and the failing assertion line. (depends on all of the above) — DoD: the PR body contains each item.

## Tests

- [ ] T1. `GetWorkflow`, using a fake `audit.Log` whose `GetByWorkflow` returns `(nil, errors.New("pool closed"))`: the response is 503 for an admin and for a non-admin, and the fake executor records **zero** `GetWorkflowStatus` calls. Mutation proof: revert the 503 branch, and the test fails on the status assertion (404 or 200 instead of 503) and on the call-count assertion.
- [ ] T2. `GetWorkflowLogs` (non-admin), with the same failing fake: 503, not 403. Mutation proof: revert the gate change, and the test gets 403.
- [ ] T3. `GetWorkflow` with `(nil, nil)`: a non-admin gets 404 "workflow record not found in audit log", and an admin gets the cron fallback (the executor is called with namespace `argo-workflows`, then 200 with the cron `note`).
- [ ] T4. `GetWorkflowLogs` with `(nil, nil)`, non-admin: 403 "no owning team", unchanged.
- [ ] T5. `GetWorkflow` and `GetWorkflowLogs` with an entry where `ParametersUnreadable: true`, non-admin: 503. Mutation proof: remove the check, and `GetWorkflow` returns 200 or 502 for a user without tenant access.
- [ ] T6. Healthy path: an entry with `tenant_name` returns the same JSON keys as today (`workflow`, `audit`, `namespace`, `live`).
- [ ] T7. Reconciler: a fake `ListByStatus` returning an error makes no `UpdateStatus` calls and does not panic. A pending row with `ParametersUnreadable` is never passed to `GetWorkflowStatus` or expired.
- [ ] T8. `scanAuditEntry` unit test with a fake scan func that yields invalid JSON params: the row is returned with `ParametersUnreadable == true` and `Parameters == nil`.
- [ ] T9. Gated on `TEST_DATABASE_URL`, in `internal/audit/postgres_test.go`:
  - `GetByWorkflow` with an already-cancelled ctx returns a non-nil error and a nil entry.
  - An unknown workflow returns `(nil, nil)`.
  - A row inserted with `params = '"not-an-object"'::jsonb` comes back with `ParametersUnreadable`.
- [ ] T10. `go test ./...` passes.

## Rollback

Revert the PR. The change is code-only, with no schema or data migration and no new configuration, so a plain `git revert` followed by a normal deploy restores today's behaviour. That behaviour is 404, 403 or the cron fallback during audit outages.
