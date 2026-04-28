# Tasks: chi-security-patch

- [ ] 1. Update the chi/v5 dependency to v5.2.5 — DoD: `go.mod` contains `github.com/go-chi/chi/v5 v5.2.5`, `go.sum` is updated, `go mod tidy` runs without errors, the `go.sum` diff is reviewed.
- [ ] 2. Run unit tests (depends on 1) — DoD: `go test ./...` finishes successfully with no new failures.
- [ ] 3. Run integration tests for routing (depends on 1) — DoD: all HTTP routes (REST endpoints, `/mcp`, `/metrics`, `/healthz`) return the expected status codes; slash-redirect tests pass with the new RedirectSlashes behaviour.
- [ ] 4. Deploy to `admins` via ArgoCD (depends on 2, 3) — DoD: ArgoCD sync completes, the pod transitions to Running, `/healthz` answers 200, `/metrics` is available.

## Tests
- [ ] T1. RedirectSlashes test: a `GET /api/v1/services/` request (with trailing slash) is handled correctly — either redirects to `/api/v1/services` or returns 200 according to configuration; verify the patch removes the vulnerable behaviour (no path manipulation).
- [ ] T2. RouteHeaders test: if the `RouteHeaders` middleware is in use, the handler is invoked exactly once on a matching request (assertion on the call counter).
- [ ] T3. Post-deploy smoke test: a REST API endpoint (for example `GET /api/v1/tenants`) returns 200/401 correctly.
- [ ] T4. Post-deploy smoke test: the `/mcp` endpoint accepts a POST request and returns a correct response (not 404/500).
- [ ] T5. Post-deploy smoke test: `/metrics` returns 200 with prometheus metrics.

## Rollback
1. In `go.mod` revert `github.com/go-chi/chi/v5` to `v5.2.1`, run `go mod tidy`, rebuild the binary.
2. Deploy the previous image version via ArgoCD (the tag of the previous successful deploy).
3. The security fix remains unapplied — record it as a known issue in the security tracker; if necessary, temporarily disable the `RedirectSlashes` middleware as mitigation.
