# Tasks: chi-v5-security-upgrade

- [ ] 1. Run `go get github.com/go-chi/chi/v5@v5.2.5 && go mod tidy` — DoD: `go.mod`
  declares `github.com/go-chi/chi/v5 v5.2.5`; the v5.2.1 entry is absent from `go.mod`
  and `go.sum`; `go mod verify` exits 0.

- [ ] 2. Build the service (depends on 1) — DoD: `go build ./...` exits 0 with zero
  compilation errors; `go vet ./...` exits 0 with zero warnings.

- [ ] 3. Run the full test suite (depends on 2) — DoD: `go test ./...` exits 0; no
  previously passing test is now failing or skipped; test output shows all endpoint handler
  tests green.

- [ ] 4. Build and push the container image (depends on 3) — DoD: image tagged
  `mctl-agent:<next-semver>` is pushed to the container registry; image manifest references
  the chi v5.2.5 binary (verifiable via `go version -m` on the binary inside the image).

- [ ] 5. Deploy to `admins` tenant via ArgoCD (depends on 4) — DoD: ArgoCD sync status
  transitions to `Synced` and `Healthy`; `GET /healthz` returns HTTP 200; no new error
  logs appear in the 10 minutes following rollout.

## Tests

- [ ] T1. Unit: `TestRouterEndpointsRespond_ChiV525` — spin up the chi router in a test
  HTTP server and confirm each registered route (`/api/v1/alerts`, `/api/v1/telegram`,
  `/api/v1/tickets`, `/api/v1/skills`, `/api/v1/skills/register`, `/mcp`, `/healthz`,
  `/readyz`) returns the expected status code for a minimal valid request. This test must
  pass on both v5.2.1 (baseline) and v5.2.5 (post-upgrade) without modification.
- [ ] T2. Unit: `TestGoModNoOldChiVersion` — a test that reads `go.mod` and asserts the
  string `"go-chi/chi/v5 v5.2.1"` is absent; acts as a regression guard.
- [ ] T3. Smoke: post-deploy — after ArgoCD sync, send a real AlertManager webhook payload
  to `POST /api/v1/alerts` and confirm the ticket is created in the SQLite DB with the
  correct status; confirms the router is wired correctly in production.

## Rollback
1. In the ArgoCD application manifest, revert the image tag to the previous `mctl-agent`
   image (the one built against chi v5.2.1). Trigger a manual sync. The rollback takes
   effect within one ArgoCD reconcile cycle (typically under 2 minutes).
2. If a full code rollback is needed, `git revert <sha>` on the single-commit change and
   push; the CI/CD pipeline will build and deploy the reverted image automatically.
3. No database migration, no Kubernetes manifest change, and no secret rotation is needed
   for rollback — the change is entirely in the Go binary.
