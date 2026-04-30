# Tasks: chi-open-redirect-ghsa-mqqf

- [ ] 1. Audit mctl-api source for `RouteHeaders` usage — DoD: a comment in the PR notes every location where `RouteHeaders` is used (or confirms it is not used), so reviewers can assess whether the double-invocation fix in v5.2.5 changes observable behaviour.
- [ ] 2. Bump `go-chi/chi/v5` to v5.2.5 in `go.mod` and run `go mod tidy` (depends on 1) — DoD: `go.mod` shows `github.com/go-chi/chi/v5 v5.2.5`; `go.sum` is regenerated; `go build ./...` succeeds.
- [ ] 3. Run the full unit and integration test suite (depends on 2) — DoD: all existing tests pass with zero new failures; no test skips introduced by this change.
- [ ] 4. Run Trivy (or equivalent scanner) against the updated module graph (depends on 2) — DoD: scanner output contains no open finding for GHSA-mqqf-5wvp-8fh8 / GO-2026-4316.
- [ ] 5. Open PR to mctl-gitops with the updated `go.mod` and `go.sum` (depends on 3, 4) — DoD: PR description references GHSA-mqqf-5wvp-8fh8; at least one reviewer approves; CI is green.
- [ ] 6. Merge and verify ArgoCD sync for the `admins` tenant (depends on 5) — DoD: ArgoCD shows the `mctl-api` application synced and healthy; no rollback triggered within 30 minutes of deployment.

## Tests

- [ ] T1. Existing routing tests pass without modification — verifies that route registration and dispatch behaviour is unchanged for all REST and MCP endpoints.
- [ ] T2. Integration test: send a `GET` request with a backslash in the path to an endpoint that uses `RedirectSlashes` — the response `Location` header must be same-origin (no external domain), and the HTTP status must be 301 or 308, not a redirect to an external host.
- [ ] T3. Integration test: exercise any `RouteHeaders`-registered route once — verify the handler fires exactly once and produces the expected response body.
- [ ] T4. Trivy scan of the final Docker image reports zero open CVEs for `go-chi/chi` — confirms the vulnerability is resolved in the shipped artefact.

## Rollback
Revert the single `go.mod` line to `github.com/go-chi/chi/v5 v5.2.1` and re-run `go mod tidy`. Open a revert PR to mctl-gitops; ArgoCD will roll back to the previous image on sync. No schema or data changes were made, so no data rollback is needed. Expected rollback time: under 15 minutes.
