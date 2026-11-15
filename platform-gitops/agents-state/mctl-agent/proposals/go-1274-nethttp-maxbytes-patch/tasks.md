# Tasks: go-1274-nethttp-maxbytes-patch

- [ ] 1. Record baseline: `go`/`toolchain` in `go.mod`, Dockerfile `FROM`, CI image — DoD: values written in the PR description; mismatch with `context/architecture.md` (Go 1.24) noted.
- [ ] 2. Verify the fixed release for GO-2026-6859 / CVE-2026-97054 in the Go vuln DB and release notes (depends on 1) — DoD: chosen version (1.26.11, 1.27.4 or later) justified in the PR with a source link.
- [ ] 3. Update `go.mod`, Dockerfile and CI image to the chosen version (depends on 2) — DoD: all three agree; image digest verified; `go build ./...` passes.
- [ ] 4. Add a required CI step `govulncheck ./...` (depends on 3) — DoD: the step runs on PRs and fails when GO-2026-6859 is reported (checked against the old toolchain).
- [ ] 5. Run tests and staging check (depends on 3) — DoD: full test suite green; oversized-body request to `/api/v1/alerts` returns an error and the pod stays up.
- [ ] 6. Deploy via ArgoCD to `admins` (depends on 4, 5) — DoD: pod Ready, `/healthz` OK, memory in line with the pre-change baseline.

## Tests
- [ ] T1. `govulncheck ./...` reports no GO-2026-6859 on the new build.
- [ ] T2. Oversized request body to each webhook endpoint (`/api/v1/alerts`, `/api/v1/telegram`, `/mcp`) does not crash the server.
- [ ] T3. Existing unit and integration tests pass unchanged.
- [ ] T4. `go version -m` of the built binary shows the pinned toolchain.

## Rollback
Revert the PR (go.mod, Dockerfile, CI image) and let ArgoCD sync the previous image tag. Keep the `govulncheck` step in place if it is only failing on the old version; mark it non-blocking temporarily if needed, and record why.
