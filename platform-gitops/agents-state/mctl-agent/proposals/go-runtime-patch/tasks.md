# Tasks: go-runtime-patch

- [ ] 1. **Update `go.mod` toolchain directive** — Add `toolchain go1.24.8` line to `go.mod`. DoD: `go mod tidy` runs without error; `go version -m ./mctl-agent` (after build) reports `go1.24.8`.

- [ ] 2. **Update Dockerfile builder stage** (depends on 1) — Change the builder `FROM` line to `golang:1.24.8-alpine` (or the equivalent non-alpine variant used by the project). DoD: `docker build` succeeds; `RUN go version` in the build layer prints `go1.24.8`.

- [ ] 3. **Update CI workflow Go version pin** (depends on 1) — Change `go-version` input in all `actions/setup-go` steps to `'1.24.8'` (or `'1.24'` with `check-latest: true` if dynamic patch resolution is preferred). DoD: CI pipeline passes on the updated branch.

- [ ] 4. **Run `go vet ./...` and fix any new findings** (depends on 1) — Execute the vet pass locally and in CI to surface any new checks introduced in 1.24.8. DoD: Zero new vet errors; any existing suppressed findings documented.

- [ ] 5. **Run the full test suite** (depends on 2, 3, 4) — `go test ./...` with race detector (`-race`). DoD: All tests pass; no new race conditions detected.

- [ ] 6. **Run `govulncheck ./...`** (depends on 5) — Verify that the 10 CVEs from the 2026-04-07 batch no longer appear in the output. DoD: `govulncheck` reports zero vulnerabilities for the packages in the 2026-04-07 advisory.

- [ ] 7. **Deploy to staging and verify** (depends on 6) — Deploy the patched image to the `admins` staging environment. DoD: `/healthz` returns 200; service processes a test alert end-to-end; no errors in logs.

- [ ] 8. **Deploy to production (`admins` tenant)** (depends on 7) — Update the ArgoCD `Application` image tag or let the GitOps pipeline pick up the new image. DoD: ArgoCD reports the application as `Synced` and `Healthy`; monitoring shows no error-rate spike for 15 minutes post-deploy.

## Tests

- [ ] T1. Unit tests pass with `-race` flag on go1.24.8.
- [ ] T2. `govulncheck` reports no findings for CVE-2026-27140, CVE-2026-32283, CVE-2026-27143, CVE-2026-27144, CVE-2026-32280, CVE-2026-32281, CVE-2026-32289, CVE-2026-32288, CVE-2026-33810, CVE-2026-32282.
- [ ] T3. Docker image build succeeds and `go version` inside the image reports `go1.24.8`.
- [ ] T4. Staging smoke test: POST a sample AlertManager webhook payload to `/api/v1/alerts`; verify a ticket is created and the correct skill is matched.

## Rollback
The previous image tag is retained in the container registry. To roll back:
1. Revert the ArgoCD `Application` image tag to the previous tag (or revert the GitOps PR).
2. ArgoCD will resync and redeploy the prior image within 3 minutes.
Note: rolling back undoes the CVE fix — escalate to the security team immediately and treat as a P1 incident until the forward fix is re-deployed.
