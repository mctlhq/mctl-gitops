# Tasks: sqlite-v150-upgrade

- [ ] 1. Update `go.mod` and `go.sum` — replace `modernc.org/sqlite v1.34` with `modernc.org/sqlite v1.50.0`; run `go mod tidy` — DoD: `go.mod` references v1.50.0, `go mod verify` passes, no other dependency versions change unexpectedly.

- [ ] 2. Compile the binary (depends on 1) — run `go build ./...` — DoD: zero compilation errors; the new `ColumnInfo` struct is additive and does not conflict with any existing code.

- [ ] 3. Add startup SQLite version log line (depends on 2) — in the DB initialisation function, execute `SELECT sqlite_version()` and log the result at `INFO` level using `slog`: `{"msg":"sqlite_version","version":"…"}` — DoD: the log line appears in pod stdout on startup; the logged version is ≥ 3.50.2.

- [ ] 4. Run table-driven unit tests for tickets DB and skill-metrics store (depends on 3) — DoD: `go test ./internal/...` passes; all table-driven test cases for ticket state transitions and circuit-breaker counter increments pass without modification.

- [ ] 5. Run full test suite (depends on 4) — DoD: `go test ./...` passes with no failures or data-race warnings (`-race` flag).

- [ ] 6. Update vendor directory if vendoring is used (depends on 5) — run `go mod vendor` — DoD: `vendor/modernc.org/sqlite` reflects v1.50.0; CI builds cleanly.

- [ ] 7. Deploy to staging and verify (depends on 6) — DoD: pod starts cleanly; startup log contains `sqlite_version` ≥ 3.50.2; ticket creation and resolution flow works end-to-end in staging; ArgoCD application in `admins` shows healthy.

## Tests

- [ ] T1. Unit test: after DB initialisation, query `SELECT sqlite_version()` and assert the returned string is ≥ `3.50.2` using a semver comparison helper.
- [ ] T2. Table-driven test: all existing ticket state machine transitions (open → in-progress → resolved, open → stale → auto-resolved) pass against the upgraded library.
- [ ] T3. Table-driven test: skill-metrics increment and circuit-breaker threshold check pass against the upgraded library.
- [ ] T4. Data-race test: run `go test -race ./...`; assert zero race conditions reported in DB access paths.

## Rollback

1. Revert `go.mod`/`go.sum` to `modernc.org/sqlite v1.34`.
2. Remove the `SELECT sqlite_version()` startup log line (optional — it is harmless on the old version too).
3. Run `go build ./...` and `go test ./...`.
4. Re-deploy via ArgoCD sync to the previous image tag.
5. Note: rollback re-exposes CVE-2025-6965; treat as a temporary state and re-attempt the upgrade at the next maintenance window.
