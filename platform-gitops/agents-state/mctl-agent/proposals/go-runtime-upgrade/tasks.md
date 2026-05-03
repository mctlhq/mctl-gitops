# Tasks: go-runtime-upgrade

- [ ] 1. Update `go.mod` to `go 1.26.2` and `toolchain go1.26.2` — DoD: `go.mod` declares both directives; `go mod tidy` runs cleanly and `go.sum` is regenerated without errors.

- [ ] 2. Update Dockerfile build stage from `golang:1.24` to `golang:1.26.2` (depends on 1) — DoD: `Dockerfile` references `golang:1.26.2`; `docker build` succeeds locally and in CI.

- [ ] 3. Update CI pipeline toolchain pin (e.g., `.github/workflows/*.yml` or equivalent) to `go 1.26.2` (depends on 1) — DoD: all CI job definitions that specify a Go version reference `1.26.2`; pipeline green.

- [ ] 4. Run `go vet ./...` and fix any deprecation warnings introduced by Go 1.25/1.26 (depends on 1) — DoD: `go vet` exits 0 with no warnings on the updated toolchain.

- [ ] 5. Run the full unit and integration test suite against Go 1.26.2 (depends on 2, 3, 4) — DoD: all existing tests pass; no new test failures introduced by toolchain change.

- [ ] 6. Run `govulncheck ./...` and confirm zero findings for CVE-2026-32283, CVE-2026-32280, CVE-2026-32281 (depends on 1) — DoD: `govulncheck` output contains no references to the three target CVEs.

- [ ] 7. Open and merge the fix PR into main (depends on 5, 6) — DoD: PR approved, CI green, merged; ArgoCD syncs the updated image to the `admins` tenant.

## Tests

- [ ] T1. `go test ./...` — all existing table-driven tests pass with Go 1.26.2 toolchain.
- [ ] T2. `govulncheck ./...` — zero findings for the three crypto CVEs.
- [ ] T3. Post-deploy `/healthz` and `/readyz` return HTTP 200 within 10 seconds of rollout.
- [ ] T4. Run the test suite 3× in CI to catch any GC-timing-related flakiness introduced by Green Tea GC.

## Rollback
1. Revert the `go.mod` / `go.sum` / Dockerfile / CI changes via a new commit (do not force-push).
2. Trigger a new ArgoCD sync to roll the `admins` deployment back to the Go 1.24 image.
3. Verify `/healthz` returns 200 on the rolled-back pod.
4. The three CVEs remain present in the rolled-back binary; schedule an expedited re-attempt.
