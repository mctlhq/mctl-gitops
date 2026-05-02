# Tasks: chi-upgrade-v525

- [ ] 1. Update go.mod — change `github.com/go-chi/chi/v5` to v5.2.5 and run `go mod tidy` — DoD: go.mod and go.sum committed, `go build ./...` passes.
- [ ] 2. Verify no compile-time breakage (depends on 1) — DoD: `go build ./...` and `go vet ./...` pass with zero errors or warnings.
- [ ] 3. Run routing test suite (depends on 2) — DoD: all HTTP handler and middleware tests pass; no 404 or redirect regressions.
- [ ] 4. Manual smoke-test of RedirectSlashes behaviour in staging (depends on 2) — DoD: trailing-slash redirect goes to the same host; a crafted external-redirect URL is NOT followed.
- [ ] 5. Deploy to production (depends on 3, 4) — DoD: ArgoCD sync completes; HTTP error rate unchanged in Prometheus metrics.

## Tests
- [ ] T1. `go build ./...` and `go vet ./...` clean.
- [ ] T2. All existing route and middleware unit tests pass.
- [ ] T3. Negative test: request to `//evil.com/foo` (or equivalent open-redirect payload) does NOT redirect to an external domain.
- [ ] T4. Positive test: trailing-slash redirect (e.g. `/api/v1/services` to `/api/v1/services/`) works correctly.

## Rollback
Revert go.mod and go.sum to chi v5.2.1 and redeploy via ArgoCD. No data migrations or configuration changes are involved; rollback is immediate. Note: v5.2.1 is not in the CVE-2025-69725 vulnerable range, so rollback carries no security regression.
