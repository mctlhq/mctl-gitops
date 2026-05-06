# Tasks: go-runtime-upgrade-v2

- [ ] 1. Update `go.mod` — change the `go` directive to `go 1.26.2`, add
  `toolchain go1.26.2`, and bump `github.com/go-chi/chi/v5` to v5.2.5.
  Run `go mod tidy` to regenerate `go.sum`. — DoD: `go.mod` declares
  `go 1.26.2` and `toolchain go1.26.2`; chi is listed at v5.2.5; `go mod
  tidy` exits 0 and `go.sum` is committed; no other dependency versions
  change except patch-level indirect bumps forced by tidy.

- [ ] 2. Update Dockerfile builder stage to `golang:1.26.2-alpine` (depends
  on 1). — DoD: the Dockerfile `FROM` line for the builder stage references
  `golang:1.26.2-alpine`; `docker build` succeeds locally and in the PR
  pipeline.

- [ ] 3. Update CI toolchain pin to Go 1.26.2 (depends on 1) — if the CI
  workflow (e.g., `.github/workflows/*.yml`) or a `.go-version` file
  explicitly pins a Go version, update it to `1.26.2`. — DoD: all CI job
  definitions that specify a Go version reference `1.26.2`; no CI step
  downloads or uses a different Go version.

- [ ] 4. Run `go vet ./...` against Go 1.26.2 and resolve any findings
  (depends on 1, 3). — DoD: `go vet ./...` exits 0 on the updated toolchain
  with zero reported issues; any deprecation warnings addressed in the same
  commit.

- [ ] 5. Run the full unit and integration test suite against Go 1.26.2
  three times in CI (depends on 2, 3, 4). — DoD: all existing tests pass on
  all three runs; zero new test failures attributable to the toolchain or
  chi version change; flaky tests (if any surface) documented and either
  fixed or filed as separate issues before merge.

- [ ] 6. Run `govulncheck ./...` and confirm zero findings for the three
  target CVEs (depends on 1). — DoD: `govulncheck` output contains no
  references to CVE-2026-32283, CVE-2026-32280, or CVE-2026-32289.

- [ ] 7. Open, review, and merge the fix PR (depends on 5, 6). — DoD: PR
  approved by at least one reviewer, all CI checks green, PR merged to
  main; ArgoCD syncs the updated image to the `admins` tenant automatically
  on the next sync cycle.

- [ ] 8. Post-deploy smoke check (depends on 7). — DoD: /healthz and /readyz
  return HTTP 200 on the new pod within the existing probe timeout; no error
  spike visible in structured logs in the five minutes following rollout.

## Tests

- [ ] T1. `go test ./...` — all existing table-driven tests pass with Go
  1.26.2 toolchain on three consecutive CI runs.
- [ ] T2. `govulncheck ./...` — zero findings for CVE-2026-32283,
  CVE-2026-32280, and CVE-2026-32289.
- [ ] T3. `go vet ./...` — exits 0 with zero reported issues.
- [ ] T4. `docker build` succeeds with `golang:1.26.2-alpine` builder stage
  and produces a runnable image.
- [ ] T5. Post-deploy: GET /healthz and GET /readyz each return HTTP 200
  within 10 seconds of the new pod becoming Ready.
- [ ] T6. Post-deploy: submit a synthetic AlertManager webhook and confirm
  the agent processes it end-to-end (ticket created, skill matched, no
  panic) on the updated binary.

## Rollback
1. Revert the `go.mod`, `go.sum`, Dockerfile, and CI workflow changes with
   a new commit (do not force-push main).
2. Merge the revert commit; CI rebuilds the image from the Go 1.24 toolchain.
3. ArgoCD detects the new image tag on its next sync and rolls the `admins`
   deployment back to the Go 1.24 pod.
4. Verify GET /healthz returns HTTP 200 on the rolled-back pod.
5. Note: the three CVEs (CVE-2026-32283, CVE-2026-32280, CVE-2026-32289) are
   present again in the rolled-back binary. Schedule an expedited re-attempt
   within 48 hours and investigate the root cause of the failure before
   re-trying.
