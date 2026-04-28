# Tasks: go-upgrade

- [ ] 1. Update the Go directive in go.mod and the toolchain in CI/Dockerfile — DoD: `go.mod` contains `go 1.26`, `Dockerfile` uses `golang:1.26.2-alpine` (or the current patch), the CI workflow (`*.yml`) is updated, the changes are captured in a PR.
- [ ] 2. Verify direct dependency compatibility with Go 1.26 (depends on 1) — DoD: for each direct dependency (chi, pgx, mcp-go, client-go, go-oidc, prometheus/client_golang, httprate) the `go` directive in their `go.mod` is checked; required bumps are performed; `go mod tidy` finishes successfully.
- [ ] 3. Build and run unit tests under Go 1.26 (depends on 1, 2) — DoD: `go build ./...` and `go test ./...` finish without errors; no test fails due to the toolchain switch.
- [ ] 4. Check `GODEBUG` defaults and release notes (depends on 1) — DoD: the Go 1.25 and 1.26 release notes are reviewed for `GODEBUG` default changes affecting TLS, HTTP, crypto; explicit `GODEBUG=...` env vars are added to the deploy config if needed.
- [ ] 5. Run integration tests (depends on 3, 4) — DoD: all integration tests, including TLS connections to external services (Vault, ArgoCD, Argo Workflows, Backstage), pass in the staging environment.
- [ ] 6. `govulncheck ./...` (depends on 3) — DoD: no findings for stdlib CVEs from the Go 1.25/1.26 security fixes; the result is captured in the PR description.
- [ ] 7. Deploy to `admins` via ArgoCD (depends on 5, 6) — DoD: ArgoCD sync completes, the pod transitions to Running, `/healthz` answers 200, `/metrics` is available, the logs contain no TLS errors.

## Tests
- [ ] T1. `go version` in the CI build output prints `go1.26.x`.
- [ ] T2. `govulncheck ./...` — no stdlib findings.
- [ ] T3. TLS integration test: an outbound request to Vault (`secrets.mctl.ai`) succeeds (200/204 response, no TLS handshake error).
- [ ] T4. Auth integration test: Dex JWT verification via JWKS works correctly (crypto/x509 chain validation).
- [ ] T5. Post-deploy smoke test: all three bearer authentication types (GitHub PAT, Dex JWT, OAuth JWT) are accepted and authorize requests correctly.
- [ ] T6. Post-deploy `/metrics` and `/healthz` check — both endpoints return 200.

## Rollback
1. In `go.mod` revert the directive to `go 1.24`, restore the previous values in the Dockerfile and CI workflow.
2. Rebuild the image with the rollback tag via CI.
3. Deploy the previous image version via ArgoCD.
4. The open stdlib CVEs remain unfixed — record as a known issue in the security tracker with rationale and the date of the next upgrade attempt.
5. If the rollback cause is a dependency incompatibility, open a separate issue with the specific dependency and version conflict.
