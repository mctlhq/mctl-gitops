# Tasks: bump-go-toolchain

- [ ] 1. Update `go.mod` — change the `go` directive from `go 1.24` to `go 1.26.2` —
  DoD: `head -3 go.mod` shows `go 1.26.2`; the file is otherwise unchanged.

- [ ] 2. Update the Dockerfile build-stage base image to `golang:1.26.2-alpine` (or the distroless
  equivalent in use) (depends on 1) —
  DoD: the Dockerfile `FROM` line for the build stage references `golang:1.26.2`; `docker build`
  succeeds locally or in CI.

- [ ] 3. Update the CI workflow `go-version` pin to `"1.26.2"` (depends on 1) —
  DoD: the CI YAML file specifies `go-version: "1.26.2"` and CI completes a successful build.

- [ ] 4. Run `go mod tidy` to ensure module graph consistency with Go 1.26 (depends on 1) —
  DoD: `go mod tidy` exits 0 with no changes to `go.mod` beyond those already made, or any
  required transitive adjustments are reviewed and committed.

- [ ] 5. Run the full test suite with the new toolchain (depends on 2, 3, 4) —
  DoD: `go test ./...` exits 0; no previously-passing tests fail.

- [ ] 6. Open a PR with all changes; ensure CI passes (depends on 5) —
  DoD: CI is green; PR description references CVE-2026-32280 and CVE-2026-32281 and this proposal.

## Tests

- [ ] T1. Confirm `go version` reported by the CI build step is `go1.26.2` — checked in CI logs
  as part of task 3.

- [ ] T2. Run `govulncheck ./...` (or equivalent vulnerability scanner configured in CI) against
  the updated module graph and confirm no outstanding `crypto/x509` vulnerabilities are reported —
  DoD: scanner exits 0 or reports only informational findings unrelated to the patched CVEs.

- [ ] T3. Run the full table-driven unit tests for all builtin Go skills
  (`internal/skill/builtin/...`) under the new toolchain —
  DoD: all tests pass; no new failures introduced by the toolchain change.

## Rollback
Revert the three declaration points (`go.mod`, `Dockerfile`, CI workflow) via `git revert
<merge-commit>`. The previous Docker image built with Go 1.24 remains available in the registry
under its original tag; redeploy that image via ArgoCD sync. No database or secret changes need to
be undone. Note that reverting re-exposes the service to CVE-2026-32280 and CVE-2026-32281 until
the upgrade is re-applied — rollback should be treated as temporary and re-attempted promptly.
