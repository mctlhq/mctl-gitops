# Tasks: sqlite-upgrade

- [ ] 1. Update `go.mod` to `modernc.org/sqlite v1.50.0` — DoD: `go.mod` declares `v1.50.0`; `go mod tidy` runs cleanly and `go.sum` is regenerated without errors.

- [ ] 2. Run existing table-driven tests for all SQLite-backed components (tickets DB, skill metrics) against v1.50.0 (depends on 1) — DoD: `go test ./...` exits 0 with no failures in SQLite-touching packages.

- [ ] 3. Run the SQLite benchmark suite and confirm read/write latency regression ≤ 10 % vs. v1.34 baseline (depends on 1) — DoD: benchmark output attached to the PR; no metric exceeds the 10 % threshold.

- [ ] 4. Run `govulncheck ./...` and confirm zero findings for CVE-2025-70873 (depends on 1) — DoD: `govulncheck` output contains no reference to CVE-2025-70873.

- [ ] 5. Run the full unit and integration test suite (depends on 2, 3) — DoD: all existing tests pass; no regressions in any package.

- [ ] 6. Open and merge the fix PR (depends on 4, 5) — DoD: PR approved, CI green, merged; ArgoCD syncs the updated image to the `admins` tenant.

## Tests

- [ ] T1. `go test ./internal/...` — all table-driven tests for SQLite-backed packages pass with v1.50.0.
- [ ] T2. `go test -bench=. ./internal/...` — no benchmark shows > 10 % latency regression vs. v1.34 baseline.
- [ ] T3. `govulncheck ./...` — zero findings for CVE-2025-70873.
- [ ] T4. Post-deploy smoke test: confirm mctl-agent starts, opens the tickets DB, and `/readyz` returns 200.
- [ ] T5. Verify existing tickets survive the upgrade: no data loss or schema mismatch on a test copy of the production DB.

## Rollback
1. Revert the `go.mod` / `go.sum` changes via a new commit.
2. Trigger ArgoCD sync to roll back the `admins` deployment.
3. Verify `/healthz` and `/readyz` return 200 on the rolled-back pod.
4. Confirm the tickets DB is intact (SQLite file format is forward/backward compatible across this version range; no migration to undo).
5. Note: rollback reintroduces CVE-2025-70873; schedule an expedited re-attempt.
