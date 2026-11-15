# Tasks: issue-1004-feat-glovo-wire-the-approval-ledger-migr

- [ ] 1. Add `cmd/glovo-migrate` (one-shot, `-confirm=apply-glovo-approval-schema`,
  `GLOVO_MIGRATION_DB_URL`, `-glovo-runtime-role` default `glovo_runtime`,
  `-work-items-role` required) calling `workitems.ApplyGlovoApprovalSchema(...,
  workitems.WithWorkItemsRole(...))`, with optional ordered `-with-glovo/-with-bridge/
  -with-orders/-with-join` steps; print the operator ownership-transfer step on an
  ownership refusal; add the binary to the Dockerfile. — DoD: `run()` is unit-tested for
  flag validation (no DB connection on bad input) and, with `TEST_DATABASE_URL`, applies
  idempotently twice; `cmd/api` contains no call to any `ApplySchema`.
- [ ] 2. Add `func (s *Store) Pool() *pgxpool.Pool` to `internal/workitems/store.go` and pass
  it to `controlProof` in `cmd/api/main.go` instead of `nil`. — DoD: a `cmd/api` test shows
  `controlProof` receives a non-nil work-items pool when the store exists.
- [ ] 3. (depends on 2) Add `cmd/api/glovo_receipt.go` with `buildGlovoLedger`: construct
  `orders.NewStore` on the Glovo pool, build the work-items store with
  `workitems.WithGlovoOrders`, build `workitems.GlovoDecisions` and set
  `api.Options.GlovoApprovals`; fill `receipt.Deps` only with observed collaborators. —
  DoD: with any collaborator absent, `GlovoApprovals` stays nil or `Ready` reports
  `collaborator_missing`; production with Glovo disabled is byte-for-byte unchanged in
  routes and logs except the added reason field.
- [ ] 4. (depends on 3) Replace the `Build` stub in `cmd/api/main.go` with
  `receipt.Ready` then `receipt.NewFence(workItemsStore, ordersStore, glovoStore, gitReader)`;
  in `installWriteFence` evaluate `Build` only when `Gate && HoldLifted`; log the
  `NotReadyError` reason. — DoD: `installWriteFence` never calls `Set` while
  `glovoWriteFenceHoldLifted` is false, proven by a test where every other input is true.
- [ ] 5. (depends on 3) Start `receipt.Sweeper` from `cmd/api/main.go` as a separate
  goroutine (`MCTL_GLOVO_RECEIPT_SWEEP_INTERVAL`, default 30 s), with
  `mctl_api_glovo_receipt_sweep_moved_total` and `..._errors_total` counters; leave
  `bridge.Expirer` unchanged. — DoD: started exactly once when the ledger is wired, not
  started otherwise; test covers both.
- [ ] 6. Add `internal/glovo/membershipwatch` detector (live-owner scan, `IsMember` via
  `glovo.BoundedMembership`, `RevokeForMembership` on non-members, heartbeat only on a clean
  tick, `Probe()` false when heartbeat missing or older than 5 min) and install it with
  `glovo.WithMembershipRevocationProbe` in `glovoStoreOptions`; add a bounded live-owner
  listing on `glovo.Store` if none exists; start it from `cmd/api/main.go` when
  `glovoStore != nil`. — DoD: `MembershipRevocationWired()` is true only within 5 min of a
  clean scan, false otherwise, including after a panic or read error.
- [ ] 7. Payload ownership (OPEN-989-4): add a test asserting the only production caller
  of `bridge.Store.Enqueue` is `internal/glovo/control/dispatcher.go`, and a dispatcher test
  that a fingerprint mismatch refuses `basket_changed` without enqueuing; cite
  `internal/glovo/basket/contract/PROVENANCE` in the test comment. — DoD: adding any other
  `Enqueue` call site makes the test fail.
- [ ] 8. (depends on 1, 4, 6) Activation proof test under real roles
  (`TEST_DATABASE_URL`): create `glovo_migrator`, `glovo_runtime` and the work-items role,
  migrate with task 1, assert the hook is `bridge.CancelOpenForConnections` and cancels an
  open command under `glovo_runtime`, assert `receipt.Ready` nil with everything wired, and
  `installed=false` with the hold const false. — DoD: test passes; skipped without
  `TEST_DATABASE_URL`.
- [ ] 9. Record the final work-items role name and the one-database target (`mctl-api`
  database) in the PR description and in a comment on mctl-gitops#2563; no gitops change is
  applied. — DoD: PR description names the role, the database and the operator ownership
  step.
- [ ] 10. `go fmt`, `go vet`, `golangci-lint`, `go test ./...`. — DoD: all green.

## Tests

- [ ] T1. `cmd/glovo-migrate`: bad/missing `-confirm`, missing DSN, invalid or equal role
  names exit non-zero without connecting.
- [ ] T2. `cmd/glovo-migrate` (DB): two consecutive runs succeed; a relation owned by
  another role exits 2 with the transfer step printed.
- [ ] T3. `installWriteFence`: gate true, hold false, every other precondition true ->
  `installed=false`, `Set` not called, `Build` not called.
- [ ] T4. `installWriteFence`: gate and hold true (test seam), `Build` returns a
  `NotReadyError` -> `ReceiptReady=false`, not installed.
- [ ] T5. `buildGlovoLedger`: each missing collaborator -> nil `GlovoApprovals` or
  `collaborator_missing`; all present -> non-nil decisions with `Ready` delegating to
  `receipt.Ready`.
- [ ] T6. Sweeper wiring: started once with ledger, not started without; an error tick
  increments the error counter and the loop continues.
- [ ] T7. Membership detector: clean tick sets heartbeat; failing read does not; probe false
  at 5 min + 1 s; non-member owner triggers `RevokeForMembership`; nil detector probe false.
- [ ] T8. Payload single-writer test and dispatcher fingerprint-mismatch test.
- [ ] T9. Activation proof under real roles (task 8).
- [ ] T10. Existing `TestFenceEndToEndRevocation`, `TestVendoredContractMatchesProvenance`
  and `cmd/api` tests still pass.

## Rollback

All new runtime behaviour sits behind `GLOVO_ENABLED`, `MCTL_BRIDGE_ENABLED` and
`MCTL_GLOVO_CONTROL_ENABLED` (unset in production) and the const gates, so the immediate
rollback is leaving or setting those off; revert the PR to remove the code. The migration
binary is never run by the API; if a migration has been applied by the operator job, the
schemas are additive and idempotent and can stay in place while the code is reverted (the
work-items store tolerates the added Glovo tables and CHECKs only through
`ApplyGlovoApprovalSchema`'s widened state set, which is a superset). The membership
detector and sweeper stop with the pod; reverting removes them with no persisted state
besides revoked connections and `unknown` approvals, both of which are correct outcomes.
