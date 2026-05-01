# Tasks: go-toolchain-upgrade

- [ ] 1. Update `go.mod` toolchain directive — change the `go` line to `go 1.26.2` and add `toolchain go1.26.2`; run `go mod tidy` to refresh `go.sum`. — DoD: `go.mod` contains `go 1.26.2` and `toolchain go1.26.2`; `go.sum` is consistent; `go mod verify` exits 0.

- [ ] 2. Update Dockerfile builder image (depends on 1) — change the builder `FROM` line from `golang:1.24-*` to `golang:1.26.2-alpine` (or the project's distroless equivalent). — DoD: `docker build` completes without error using the new image; `go version` printed during build shows `go1.26.2`.

- [ ] 3. Update CI/CD pipeline YAML Go version references (depends on 1) — locate every Argo Workflows template, GitHub Actions workflow, or Makefile variable that hard-codes the Go version and update to `1.26.2`. — DoD: grep for `1.24` in pipeline files returns zero matches referencing the Go toolchain version; pipeline YAML passes linting.

- [ ] 4. Run full build and test suite locally against Go 1.26.2 (depends on 1, 2, 3) — execute `go build ./...`, `go vet ./...`, and `go test ./...` with the new toolchain. — DoD: all commands exit 0; no new warnings from `go vet` that did not exist under 1.24.

- [ ] 5. Open PR and pass CI (depends on 4) — submit the changes as a single PR titled "chore: upgrade Go toolchain to 1.26.2 (7 CVEs)". — DoD: CI pipeline is green; PR description links all 7 CVE IDs; at least one reviewer approves.

- [ ] 6. Post-deploy verification (depends on 5, after merge and ArgoCD sync) — confirm the running pod reports the new toolchain version and memory metrics are within baseline. — DoD: `kubectl exec` into the pod and `printenv GOVERSION` (or equivalent binary metadata) shows `1.26.2`; Prometheus RSS metric for the pod is within ±5% of the pre-upgrade 24-hour average.

## Tests

- [ ] T1. Table-driven build-tag compatibility test — add a `TestToolchainVersion` test in `internal/version/version_test.go` (table-driven, per Go project rule) that reads `runtime.Version()` and asserts it is >= `go1.26`; table rows cover exact version string format variants. — DoD: test passes under 1.26.2 and fails when run with a mocked version string below 1.26.
- [ ] T2. CVE regression test documentation — create `internal/security/cve_toolchain_test.go` with a table-driven test that documents each CVE ID and the Go version that fixed it, asserting `runtime.Version()` meets the minimum; serves as a living regression guard. — DoD: all 7 CVE rows pass; any future toolchain downgrade would cause test failure.
- [ ] T3. Existing unit tests unchanged — the full `go test ./...` suite must pass without modification to any test file. — DoD: test count is the same as on Go 1.24; zero tests deleted or skipped to accommodate the upgrade.
- [ ] T4. Memory steady-state check — run the mctl-agent binary under Go 1.26.2 with a synthetic alert load (existing load-test script or `go test -bench`) for 10 minutes; record RSS. — DoD: RSS under 1.26.2 is within ±5% of the RSS recorded under 1.24 in the same environment.

## Rollback
1. Revert the PR (GitHub "Revert" button) — this restores `go.mod`, `go.sum`, Dockerfile, and CI YAML to Go 1.24 in a single commit.
2. Trigger an ArgoCD sync to redeploy the previous image.
3. Confirm the pod is running the Go 1.24 binary by checking `runtime.Version()` or the image tag.
4. File a follow-up issue documenting why the rollback was needed; do not leave the service on Go 1.24 longer than necessary given the open CVEs.

Note: because this change contains no database migrations, no data-layer rollback is required.
