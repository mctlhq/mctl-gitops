# Tasks: issue-162-fix-monitor-dedup-on-alert-name-and-exem

- [ ] 1. In `internal/ticket/store.go`, add an `alertName` parameter to `Store.FindDuplicate`, add `AND alert_name=?` to its query (still through `s.rebind`), and update the doc comment to match `FindRecentlyResolved` (empty name matches only empty name). — DoD: package compiles; query binds args in order tenant, service, type, alertName, StatusResolved, StatusSuppressed.
- [ ] 2. (depends on 1) Update the `alertStore` interface in `internal/monitor/alerthandler.go` and make `processAlert` pass `alertName` to `FindDuplicate`. — DoD: `go build ./...` passes.
- [ ] 3. (depends on 1) Make `internal/monitor/poller.go` and `internal/monitor/github_webhook.go` pass `""` as alertName, with a short comment saying their tickets carry no alert name. — DoD: no behaviour change for those paths; existing poller and webhook tests pass.
- [ ] 4. In `processAlert`, gate the flap-cooldown block with `severity != ticket.SeverityCritical` and update the `AlertHandler.FlapCooldown` field comment to say critical alerts are exempt. — DoD: critical alerts never call `FindRecentlyResolved`; non-critical behaviour unchanged.
- [ ] 5. (depends on 2) Update the `blockingStore.FindDuplicate` wrapper and any other test doubles in `internal/monitor/alerthandler_test.go` to the new signature. — DoD: `go vet ./...` passes.
- [ ] 6. Add the tests below, then run `go test ./...` and `go vet ./...`. Check by hand that each new test fails with its production change reverted. — DoD: all green; the revert check is noted in the PR description.

## Tests
- [ ] T1. `internal/ticket/store_test.go` `TestStoreFindDuplicateKeyedByAlertName`: create an open ticket with `AlertName: "CPUThrottlingHigh"`, `Type: TypeResourceLimit`.
  - `FindDuplicate(..., "TenantMemoryQuotaHigh")` returns nil.
  - `FindDuplicate(..., "CPUThrottlingHigh")` returns that ticket.
  - `FindDuplicate(..., "")` returns nil.
  - A blank-name ticket is found by `FindDuplicate(..., "")`.
  (Fails on revert because the name-blind query matches.)
- [ ] T2. Update `TestStoreFindDuplicate` to the new signature with `""` (unchanged semantics for blank-name tickets).
- [ ] T3. `internal/ticket` dialect check: on a `Store{dialect: "postgres"}`, assert that `rebind` of the `FindDuplicate` query yields `$1..$6` and no `?`. This covers the Postgres placeholder path without a live database. Extract the query into a package-level const so the test can reference it.
- [ ] T4. `internal/monitor/alerthandler_test.go` `TestAlertHandlerDedupKeyedByAlertName`: fire `CPUThrottlingHigh`, then `TenantMemoryQuotaHigh` on the same namespace/pod. Expect 2 `onTicket` callbacks and 2 open tickets. Firing `CPUThrottlingHigh` again still yields 2 callbacks, and the first ticket's fingerprint/UpdatedAt is touched. (Fails on revert: 1 callback.)
- [ ] T5. Keep `TestAlertHandlerDedup` and `TestAlertHandlerDedupBumpsUpdatedAt` passing: the same alert name re-firing is still deduplicated.
- [ ] T6. `TestAlertHandlerFlapCooldownCriticalBypass`: with `FlapCooldown = 10m`, fire, resolve, then re-fire `PodCrashLooping` (classified critical) with a fingerprint. Expect 2 callbacks. (Fails on revert: 1 callback.)
- [ ] T7. The existing `TestAlertHandlerFlapCooldown` (`CPUThrottlingHigh`, warning) still expects 1 callback, which confirms a warning inside the window is still suppressed. Add an explicit assertion comment that it covers the warning case.

## Rollback
Revert the merge commit and cut a patch release (per CLAUDE.md: release branch + PR, then tag without `v`). There is no schema or data migration. Tickets created under the new keying stay valid and resolve through the normal fingerprint-scoped path.
