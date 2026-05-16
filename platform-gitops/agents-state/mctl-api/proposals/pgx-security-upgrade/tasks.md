# Tasks: pgx-security-upgrade

- [ ] 1. Bump pgx to v5.9.2 in go.mod — run `go get github.com/jackc/pgx/v5@v5.9.2 && go mod tidy`; commit updated `go.mod` and `go.sum`. DoD: `go list -m github.com/jackc/pgx/v5` returns `v5.9.2`.

- [ ] 2. Review v5.9.0–v5.9.2 release notes for breaking changes (depends on 1) — diff the changelog entries for `pgxpool`, `pgconn`, and `pgx` packages; flag any changed defaults for connection reset, SCRAM, or TLS options. DoD: documented review comment in the PR describing any behavior differences and confirming no mctl-api code changes are needed.

- [ ] 3. Update connection pool configuration if required (depends on 2) — if step 2 uncovers changed pool defaults, adjust the pool config in `config/postgres.go` (or equivalent) to preserve current behavior. DoD: pool config produces the same observable behavior as on v5.8 in local dev.

- [ ] 4. Run unit + integration tests against a local Postgres instance (depends on 3) — execute `go test ./...` including any `_integration_test.go` files with a live database. DoD: zero new test failures attributable to the pgx bump.

- [ ] 5. Deploy to staging and observe for 24 hours (depends on 4) — promote the updated image to the staging environment; monitor Prometheus metrics for connection errors, query latency, and pool saturation. DoD: no anomalies detected over the 24-hour window; Prometheus alert rules silent.

- [ ] 6. Promote to production (depends on 5) — merge PR, let ArgoCD apply the updated image. DoD: production mctl-api pod running image built with pgx v5.9.2; deployment health check green.

## Tests

- [ ] T1. **CVE regression test** — write a test that exercises the simple-protocol path (if any) with a dollar-quoted string literal as input and confirms no SQL injection occurs. Should remain green after upgrade.

- [ ] T2. **Pool stability test** — run a 10-minute load test against the staging API (1000 RPS mixed read/write); assert zero connection-pool exhaustion errors and zero unexpected disconnects in pgx metrics.

- [ ] T3. **Existing integration suite** — confirm all tests in `db/` and `identity/` packages pass without modification.

## Rollback
1. Revert the `go.mod` / `go.sum` changes: `git revert <commit-sha>`.
2. Rebuild and redeploy the image with pgx v5.8.
3. ArgoCD will detect the image change and roll back automatically if the new image fails health checks.
4. If already promoted: use ArgoCD UI or `argocd app rollback mctl-api` to restore the previous revision.
