# Tasks: chi-open-redirect

- [ ] 1. Update `go.mod` to `github.com/go-chi/chi/v5 v5.2.5` — DoD: `go.mod` declares `v5.2.5`; `go mod tidy` runs cleanly and `go.sum` is regenerated without errors.

- [ ] 2. Audit codebase for use of `middleware.RedirectSlashes` (depends on 1) — DoD: a grep of `internal/`, `cmd/`, and `main.go` confirms whether `RedirectSlashes` is used; result documented in the PR description.

- [ ] 3. If `RedirectSlashes` is used: add a test asserting that a crafted cross-host redirect URL does NOT result in an external redirect (depends on 2) — DoD: test added under the relevant handler package; test passes with v5.2.5 and would fail with v5.2.1.

- [ ] 4. Run the full unit and integration test suite (depends on 1) — DoD: all existing tests pass; no route or middleware regressions.

- [ ] 5. Run `govulncheck ./...` and confirm zero findings for GO-2026-4316 / GHSA-mqqf-5wvp-8fh8 (depends on 1) — DoD: `govulncheck` output contains no reference to GO-2026-4316.

- [ ] 6. Open and merge the fix PR (depends on 4, 5) — DoD: PR approved, CI green, merged; ArgoCD syncs updated image to `admins` tenant.

## Tests

- [ ] T1. `go test ./...` — all existing routing and middleware tests pass with chi v5.2.5.
- [ ] T2. `govulncheck ./...` — zero findings for GO-2026-4316.
- [ ] T3. If `RedirectSlashes` is active: new regression test confirms no external redirect on crafted URL.
- [ ] T4. Post-deploy smoke test: `POST /api/v1/alerts` with a minimal valid payload returns expected HTTP response code.

## Rollback
1. Revert the `go.mod` / `go.sum` changes via a new commit.
2. Trigger ArgoCD sync to roll back the `admins` deployment.
3. Verify `/healthz` returns 200 on the rolled-back pod.
4. Note: rollback reintroduces the open-redirect risk; schedule an expedited re-attempt and consider temporarily disabling `RedirectSlashes` as a stopgap if it is in use.
