# Tasks: modernc-sqlite-upgrade

- [ ] 1. VERIFY versions: confirm the current pin in `go.mod`, that v1.61.1 is the latest tag, and the minimum Go version it requires — DoD: facts recorded in the PR; if min Go > current toolchain, mark dependency on go-toolchain-bump.
- [ ] 2. Review release notes 1.35 to 1.61.1 for breaking changes (error codes, pragma defaults, busy handling, SQLite 3.53.4 changes) — DoD: list of relevant changes (depends on 1).
- [ ] 3. Capture baseline RSS and DB-call latency in `admins` (read-only) — DoD: numbers recorded.
- [ ] 4. Take a copy of the tickets and skill-metrics DBs for testing — DoD: copies available in a test location; production untouched.
- [ ] 5. Bump `modernc.org/sqlite` to v1.61.1, `go mod tidy` (depends on 1, 2) — DoD: builds.
- [ ] 6. Audit DB call sites and switch to Context variants where missing; handle context errors without leaving ticket state inconsistent (depends on 5) — DoD: all DB calls take a context; error handling reviewed.
- [ ] 7. Run integrity check and test suite on the DB copies (depends on 4, 5, 6) — DoD: `PRAGMA integrity_check` returns ok; tests pass.
- [ ] 8. Measure RSS and latency with the new build and compare to baseline (depends 3, 7) — DoD: RSS within 15% of baseline; otherwise stop and report.
- [ ] 9. Back up production DB files, deploy via ArgoCD to `admins` (depends on 8) — DoD: healthy pods, ticket pipeline processing, no new errors in logs.

## Tests
- [ ] T1. Migration test: open copies of production DBs with the new driver; integrity_check ok; row counts unchanged.
- [ ] T2. Busy-timeout test: hold a write lock in one connection, run a second call with a context cancelled after 100 ms; it returns promptly with a context error.
- [ ] T3. Concurrency test: ticket pipeline and webhook handlers writing concurrently show no lost writes.
- [ ] T4. Circuit breaker metrics: a context-cancelled DB call does not count as a skill failure.
- [ ] T5. Full `go test ./...` passes.

## Rollback
Revert the dependency bump PR and let ArgoCD sync the previous image. If data issues appear, restore the DB files from the pre-rollout backup (task 9). No schema change is involved.
