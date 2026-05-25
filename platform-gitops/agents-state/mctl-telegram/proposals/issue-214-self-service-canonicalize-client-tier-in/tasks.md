# Tasks: issue-214-self-service-canonicalize-client-tier-in

- [ ] 1. Add `slog` to imports in `internal/oauth/enable_access.go` — DoD:
  `go build ./internal/oauth/...` passes; no new import-cycle warnings from
  `go vet`.

- [ ] 2. Edit `finishEnable` in `internal/oauth/enable_access.go` (line 503)
  to call `s.store.SetAccessTier(r.Context(), es.tgID, db.TierClient)` for
  non-admin users, logging but not propagating the error (depends on 1) —
  DoD: the function body matches the snippet in `design.md`; `go build
  ./...` and `go vet ./...` pass.

- [ ] 3. Add `stubLoginAs(tgID int64) LoginFunc` helper to
  `internal/oauth/enable_access_test.go` — a variant of `stubLogin` that
  persists a session blob and returns the supplied `tgID` instead of the
  hardcoded admin `210408407` — DoD: helper compiles; the existing tests
  that use `stubLogin` are unchanged.

- [ ] 4. Add `TestFinishEnable_WritesClientTier` to
  `internal/oauth/enable_access_test.go` near `TestResolveScopes_AutoApprove`
  (depends on 2, 3) — DoD: test exists, uses Telegram ID `888000999` (not
  in `AdminTelegramIDs`), drives the full phone → code → 302 flow, then
  asserts `store.GetAccessTier(ctx, 888000999) == db.TierClient`; `go test
  ./internal/oauth/...` passes.

- [ ] 5. Extend `TestEnableAccess_HappyPath_NoTwoFA` in
  `internal/oauth/enable_access_test.go` to assert that `GetAccessTier` for
  the admin ID `210408407` returns `""` after the flow (admin guard) (depends
  on 2) — DoD: assertion added; existing test still passes.

## Tests

- [ ] T1. `TestFinishEnable_WritesClientTier` — non-admin user completes
  enable_access; `store.GetAccessTier` returns `db.TierClient` afterward.
- [ ] T2. `TestEnableAccess_HappyPath_NoTwoFA` (extended) — admin user
  completes enable_access; `store.GetAccessTier` returns `""` (no DB tier
  written for admins).
- [ ] T3. `go test ./internal/oauth/...` — all pre-existing tests pass
  unchanged.
- [ ] T4. `go build ./...` — no build errors.
- [ ] T5. `go vet ./...` — no vet warnings.

## Rollback

The change is a single three-line addition to `finishEnable` plus a
`slog` import. To roll back: revert the commit or remove the
`if !s.cfg.AdminTelegramIDs[es.tgID] { ... }` block and the `slog`
import from `enable_access.go`. No DB migration was added, so there is
no schema to undo. Users who had `access_tier = 'client'` written during
the window the fix was deployed will retain that tier after rollback; they
will continue to receive scopes via the DB-first path in `isClientTier`,
which is the correct and desired behaviour. A rolled-back deployment cannot
produce new writes but is fully compatible with existing written rows.
