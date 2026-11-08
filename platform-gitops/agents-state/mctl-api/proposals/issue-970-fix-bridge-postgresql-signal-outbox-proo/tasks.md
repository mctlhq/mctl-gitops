# Tasks: issue-970-fix-bridge-postgresql-signal-outbox-proo

- [ ] 1. Add an isolated PG test helper `pgIsolatedStore(t)` in `internal/bridge/outbox_pg_test.go`. It creates a
  per-test schema, opens the store with `search_path`, logs `SELECT version()` and drops the schema in
  `t.Cleanup`. — DoD: skips cleanly without `TEST_DATABASE_URL`; with it, `bridge_signal_outbox` exists only in the
  test schema and is dropped afterwards.
- [ ] 2. (depends on 1) Write `TestPGOutbox*` tests against the unchanged `LeaseSignals` SQL: lease basics
  (limit, order, due filter, terminal exclusion, visibility push); visibility expiry and re-lease; deterministic
  SKIP LOCKED with a lock-holding tx under a context deadline; a repeated N-goroutine race proving disjoint sets;
  real-path fixture via `enqueue` -> `claimOne` -> `SubmitResult`. — DoD: tests pass on PostgreSQL 16 in CI, or fail
  with the exact SQLSTATE logged.
- [ ] 3. (depends on 2) Only if task 2 fails on the original SQL: replace `LeaseSignals` with the
  `WITH due AS (... FOR UPDATE SKIP LOCKED) UPDATE ... FROM due` form in design.md, keeping ORDER BY, LIMIT, the
  status guard and the RETURNING columns. If task 2 passes, leave the SQL byte-identical. — DoD: the PR description
  records which branch applied, the PG version, the test names, the CI link and (if rewritten) the before/after runs.
- [ ] 4. (depends on 1) Write `TestPGOutbox*` tests for `RetrySignal`, `MarkSignalSent` and `MarkSignalUnknown`:
  column effects; terminal rows unchanged (full-row snapshot) after late mark/retry calls and never re-leased; the
  error branch (cancelled ctx -> wrapped error); `Dispatcher.RunOnce` over real rows with a fake signaler
  (nil / `ErrSignalTargetNotFound` / transient). — DoD: all pass in CI.
- [ ] 5. Change `Store.leaseLive` in `internal/bridge/store.go` so that, after the status switch and the token
  check, an elapsed `ExpiresAt` returns `ErrCommandExpired` before the `LeaseExpiresAt` check. Update the doc comment
  with the precedence list. — DoD: `go vet`, `golangci-lint` clean; no other production code changes.
- [ ] 6. (depends on 5) Add a table-driven unit test of `leaseLive` with an injected `s.now`
  (`internal/bridge/store_lease_test.go`), and add real-PG tests in `store_pg_test.go`: expired command TTL ->
  `command_expired` from both `SubmitResult` and `IssueWritePermit`, with no row or permit change; expired lease
  only -> `lease_stale`; forged token on an expired command -> `lease_stale`; valid token -> success. — DoD: pass
  locally without a DB (unit) and in CI with PG.
- [ ] 7. (depends on 5) Add `bridge.ErrCommandExpired: 409` to the error-mapping table in
  `internal/api/handlers_bridge_test.go`. — DoD: test passes; `bridgeStatus` is unchanged.
- [ ] 8. (depends on 2, 4, 6) Add a `validate.yml` step that runs `go test -p 1 -count=1 -v -run 'TestPG'
  ./internal/bridge/` and fails on any `--- SKIP`. — DoD: CI log shows the PG version line and the bridge PG tests
  as PASS, not SKIP.
- [ ] 9. Open the PR against `main` with `MCTL_BRIDGE_ENABLED` default and `refusingFence` untouched, and no
  P3 cleanups. — DoD: lint, CodeQL, Trivy and govulncheck are green, and fresh Claude APPROVED plus agy PASS on the
  same head SHA (or an explicit owner hold) before merge.

## Tests
- [ ] T1. `TestPGOutboxLeaseDueOrderLimit`: limit, order, due/terminal filtering, visibility push.
- [ ] T2. `TestPGOutboxVisibilityTimeoutReleases`: a leased row becomes leasable after the visibility timeout.
- [ ] T3. `TestPGOutboxSkipLockedDoesNotBlock`: rows locked by another tx are skipped; returns within the deadline.
- [ ] T4. `TestPGOutboxConcurrentLeasersDisjoint`: N parallel leasers, repeated runs, pairwise disjoint sets.
- [ ] T5. `TestPGOutboxRetrySignal`: attempts, error code and `next_attempt_at`, then re-leasable once due.
- [ ] T6. `TestPGOutboxTerminalStatesImmutable`: sent/unknown rows unchanged after late mark/retry calls; never leased.
- [ ] T7. `TestPGOutboxFromSubmitResult`: a real submitted result's outbox row is leased and marked sent.
- [ ] T8. `TestPGOutboxDispatcherRunOnce`: sent / unknown / retry outcomes on real rows.
- [ ] T9. `TestPGOutboxLeaseError`: a cancelled context returns a wrapped error.
- [ ] T10. `TestLeaseLivePrecedence` (unit): the full precedence table, including expired command vs expired lease.
- [ ] T11. `TestPGExpiredCommandTTL`: `command_expired` from SubmitResult and IssueWritePermit; no writes.
- [ ] T12. `TestPGExpiredLeaseAndStaleToken`: `lease_stale` for an expired lease on a live command and for a forged
  token; success for a valid token.
- [ ] T13. Handler mapping: `ErrCommandExpired` -> 409 `command_expired`, `ErrLeaseStale` -> 409 `lease_stale`.

## Rollback
Revert the PR. There are no schema or data migrations, and the bridge is disabled by default
(`MCTL_BRIDGE_ENABLED=false`), so a revert only restores the old `lease_stale` code for unswept expired commands
and, if task 3 applied, the original `LeaseSignals` SQL. Test schemas are dropped per test. Any left in the CI test
database by a crashed run can be removed with `DROP SCHEMA bridge_t_* CASCADE`.
