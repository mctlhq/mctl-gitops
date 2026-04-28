# Tasks: pgx-sql-injection-fix

- [ ] 1. Bump pgx/v5 to v5.9.2 in go.mod — DoD: `go.mod` declares
  `jackc/pgx/v5 v5.9.2`; `go mod tidy` exits 0 with no unexpected removals;
  `go.sum` updated and committed.

- [ ] 2. Verify binary fingerprint (depends on 1) — DoD: `go version -m
  ./bin/mctl-api | grep pgx` outputs `v5.9.2`; no other pgx version appears
  in the module graph (`go mod graph | grep pgx` shows a single entry).

- [ ] 3. Run govulncheck and confirm CVEs closed (depends on 2) — DoD:
  `govulncheck ./...` reports zero findings for CVE-2025-54236,
  CVE-2026-4427, CVE-2026-33815, and CVE-2026-33816; output captured as a
  CI artifact.

- [ ] 4. Open and merge PR through standard review (depends on 3) — DoD: PR
  approved by at least one owner; all CI checks green (build, unit tests,
  integration tests, govulncheck); merged to main.

- [ ] 5. GitOps image promotion to `admins` (depends on 4) — DoD: ArgoCD
  shows the new image tag synced and healthy in the `admins` namespace;
  readiness probe passing; no error-rate spike observed in Prometheus for
  5 minutes post-deploy.

## Tests

- [ ] T1. Unit regression — run `go test ./...` on the updated module; all
  existing tests pass with no new failures or data races (`-race` flag).

- [ ] T2. SQL-injection regression — add or confirm a test that passes a
  dollar-quoted string (e.g., `$$foo$$`) as a query parameter to an identity
  or audit-log query and asserts the value is stored/returned verbatim without
  triggering any additional SQL execution.

- [ ] T3. DataRow negative-length fuzz — add or confirm a test (or use the
  upstream pgproto3 test vectors) that feeds a crafted DataRow with a negative
  field-length byte sequence to the protocol parser and asserts a clean error
  return (no panic, no goroutine crash).

- [ ] T4. Integration smoke — deploy the patched binary to a staging/preview
  environment backed by a real Postgres instance; exercise the `/identities`
  and audit-log endpoints; assert HTTP 200 responses and correct DB writes.

- [ ] T5. govulncheck gate — add `govulncheck ./...` as a required step in
  the CI pipeline so future vulnerability regressions are caught automatically.

## Rollback
ArgoCD maintains the previous revision of the `mctl-api` deployment manifest.
If the new pod fails its readiness probe, ArgoCD's automated sync will revert
to the last healthy revision within the configured sync timeout (default 5 min).

For a manual rollback:
1. In the ArgoCD UI (or via `argocd app rollback mctl-api`), select the
   previous revision and click "Rollback".
2. Confirm the old image tag is running: `kubectl -n admins get pod -l
   app=mctl-api -o jsonpath='{.items[0].spec.containers[0].image}'`.
3. Re-open the security finding in the issue tracker and schedule a re-attempt
   after root-cause analysis.

No database state is changed by this upgrade, so no data rollback is required.
