# Tasks: pgx-upgrade-v592

- [ ] 1. Update go.mod — change `github.com/jackc/pgx/v5` to v5.9.2 and run `go mod tidy` — DoD: go.mod and go.sum committed, module graph resolves cleanly.
- [ ] 2. Fix any compile-time breakage (depends on 1) — DoD: `go build ./...` passes with zero errors.
- [ ] 3. Run govulncheck (depends on 2) — DoD: `govulncheck ./...` reports no findings for CVE-2025-54236, CVE-2026-33815, CVE-2026-33816.
- [ ] 4. Run integration tests against Postgres (depends on 2) — DoD: all existing DB-layer tests pass; no query regressions.
- [ ] 5. Deploy to staging and smoke-test (depends on 3, 4) — DoD: mctl-api starts cleanly, `/healthz` returns 200, audit-log writes succeed.
- [ ] 6. Merge and deploy to production (depends on 5) — DoD: ArgoCD sync completes, no errors in Postgres connection logs.

## Tests
- [ ] T1. Unit tests for all pgx call-sites pass after the bump.
- [ ] T2. govulncheck clean for the three CVE IDs.
- [ ] T3. Integration test: insert + select on audit_logs and tenant tables returns correct data.
- [ ] T4. Load test: connection pool exhaustion behaviour unchanged.

## Rollback
Revert go.mod/go.sum to pgx v5.8.x and redeploy via ArgoCD. No data migration means rollback is instant and safe.
