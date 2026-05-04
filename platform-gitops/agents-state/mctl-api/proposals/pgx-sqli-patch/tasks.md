# Tasks: pgx-sqli-patch

- [ ] 1. Audit pgx protocol mode in mctl-api source — DoD: Every construction of `pgxpool.Config` and `pgx.ConnConfig` in the codebase has been inspected; a written note confirms whether `PreferSimpleProtocol` is set to `true` anywhere. Result is committed as `context/decisions/0002-pgx-query-protocol.md` describing the finding, exploitability verdict for CVE-2025-54236, and any compensating controls if simple protocol is in use.

- [ ] 2. Bump pgx to v5.9.2 in go.mod (depends on 1) — DoD: `go get github.com/jackc/pgx/v5@v5.9.2` has been run; `go.mod` declares `github.com/jackc/pgx/v5 v5.9.2`; `go.sum` is updated; `go mod tidy` produces no diff; the change is committed with message referencing CVE-2025-54236 and CVE-2026-4427.

- [ ] 3. Run govulncheck and confirm clean bill of health (depends on 2) — DoD: `govulncheck ./...` exits 0 with no findings for `jackc/pgx`, `jackc/pgconn`, `jackc/pgproto3`, or `jackc/pgtype`; output is saved as `govulncheck-pgx-sqli-patch.txt` and committed alongside the go.mod change or attached to the PR.

- [ ] 4. Update CI pipeline to enforce govulncheck on every build (depends on 3) — DoD: The CI configuration (GitHub Actions or equivalent) includes a `govulncheck ./...` step that fails the build on any HIGH or CRITICAL finding; a SARIF report is archived as a build artefact; this step runs before the container image is pushed.

- [ ] 5. Build and push updated container image (depends on 4) — DoD: A new container image is built from the patched source; image digest is recorded; the image passes the existing container vulnerability scan with no NEW findings relative to the pre-patch baseline.

- [ ] 6. Update ArgoCD Application manifest and deploy to admins (depends on 5) — DoD: The ArgoCD Application manifest references the new image digest; ArgoCD sync completes without error; the rolling update replaces all pods in the `admins` namespace; no increase in Postgres connection error rate is observed on the `/metrics` endpoint within 15 minutes of rollout completion.

## Tests

- [ ] T1. Unit test — confirm no regression in query execution: run the full existing Go test suite (`go test ./...`) against a real or test-double Postgres instance; all tests pass with pgx v5.9.2.
- [ ] T2. govulncheck scan: `govulncheck ./...` must exit 0 with zero findings for the pgx module family (CVE-2025-54236, CVE-2026-4427 must both be absent).
- [ ] T3. Protocol mode assertion test: add or extend a test that constructs the application's `pgxpool.Config` and asserts `PreferSimpleProtocol == false`; this test must live in the repository and run in CI so protocol-mode drift is caught automatically in future.
- [ ] T4. Integration smoke test: after deployment to `admins`, execute a representative read and write against the tenant-identity and audit-log tables (via an existing health-check or integration test script) and verify correct results are returned.
- [ ] T5. Metrics baseline check: compare the `pg_*` and connection-pool metrics from `/metrics` before and after the upgrade; assert no statistically significant increase in error counters or latency percentiles.

## Rollback

If the upgrade introduces an unexpected regression:

1. Revert the `go.mod` / `go.sum` commit to restore `pgx/v5 v5.8`.
2. Rebuild the container image from the reverted source and push with a `-rollback` tag.
3. Update the ArgoCD Application manifest to reference the previous image digest (which must be retained and not garbage-collected until this proposal is fully closed).
4. Trigger an ArgoCD sync; verify pod replacement completes and `/metrics` returns to baseline.
5. Open a follow-up issue documenting the regression, with reproduction steps, before re-attempting the upgrade.

Note: rolling back does not resolve the CVEs. If a rollback is needed, the security team must be notified immediately so compensating network controls (e.g., restricting Postgres port access, adding a WAF rule) can be applied while the root cause of the regression is investigated.
