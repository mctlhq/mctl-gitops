# Tasks: chi-open-redirect-patch

- [ ] 1. Confirm `RedirectSlashes` middleware usage — audit `main.go` and all router-setup files to determine whether `middleware.RedirectSlashes` is explicitly registered; document the finding in the PR description. — DoD: PR description states "RedirectSlashes is [enabled|disabled]" with file + line reference; reviewer has confirmed the finding.

- [ ] 2. Bump chi to v5.2.5 in `go.mod` (depends on 1) — Edit `go.mod`: change `github.com/go-chi/chi/v5 v5.2.1` to `github.com/go-chi/chi/v5 v5.2.5`. Run `go mod tidy` to refresh `go.sum`. Commit both files. — DoD: `go.mod` shows `v5.2.5`; `go.sum` contains the new hash entries; `go mod verify` exits 0; no other dependency versions changed unless required by tidy.

- [ ] 3. Run vulnerability scan locally (depends on 2) — Execute `govulncheck ./...` against the updated module graph and confirm GO-2026-4316 is no longer reported. — DoD: `govulncheck` output contains zero findings for GO-2026-4316 / GHSA-vrw8-fxc6-2r93; output is pasted into the PR description.

- [ ] 4. Add `govulncheck` step to CI pipeline (depends on 2) — If not already present, add a `govulncheck ./...` step to the CI workflow (GitHub Actions / Tekton pipeline) that fails the build on any vulnerability finding. — DoD: CI configuration file updated; a test run with the old `v5.2.1` pinned (or a synthetic vuln) causes the step to fail; the run with `v5.2.5` passes.

- [ ] 5. Open and merge PR against mctl-gitops (depends on 3, 4) — Create a pull request with title `fix(deps): bump chi to v5.2.5 (GO-2026-4316)`. PR must include: updated `go.mod`, updated `go.sum`, CI passing, `govulncheck` output in description, link to GHSA-vrw8-fxc6-2r93. — DoD: PR approved by at least one maintainer; all CI checks green; PR merged to main branch of mctl-gitops.

- [ ] 6. Verify ArgoCD deployment (depends on 5) — Monitor the ArgoCD application for `mctl-api` in the `admins` tenant until it reports `Synced / Healthy`. Confirm the running pod reports the new image digest. — DoD: ArgoCD UI shows `Synced` and `Healthy`; `kubectl describe pod` for the new pod shows the updated image SHA; no increase in error rate observed in Prometheus for 15 minutes post-deploy.

## Tests

- [ ] T1. Unit / regression — Run `go test ./...` against the bumped module graph. All existing tests must pass. No new test failures introduced by the chi patch.
- [ ] T2. Vulnerability scan — `govulncheck ./...` must exit 0 with zero findings for GO-2026-4316 on the updated codebase.
- [ ] T3. Open redirect probe — Using `curl` or an integration test, send a request with `Host: evil.example.com` to a route that would trigger `RedirectSlashes` (e.g., `GET /api/v1/services` with a trailing slash variant). Assert the `Location` response header does NOT contain `evil.example.com`. This test must be included in the CI suite going forward.
- [ ] T4. OAuth PKCE callback smoke test — Execute the existing OAuth PKCE integration test suite (or a manual walkthrough in staging) to confirm the authorization callback still redirects to the legitimate registered URI and returns a valid authorization code to the correct client.
- [ ] T5. Route correctness — Validate that all registered chi routes continue to return expected status codes (a route table smoke test); no inadvertent 404s caused by any behavior difference in v5.2.5.

## Rollback

If a regression is detected after deployment:

1. Revert the `go.mod` / `go.sum` commit in the mctl-gitops repository (a single `git revert` of the bump commit is sufficient).
2. Push the revert commit to the main branch; ArgoCD will detect the change and redeploy the previous image automatically within its sync interval (default 3 minutes).
3. Confirm ArgoCD reports `Synced / Healthy` and the previous chi version (`v5.2.1`) is reflected in the running pod.
4. File a follow-up issue documenting the regression and coordinate with the chi maintainers before re-attempting the upgrade.

Note: rolling back to v5.2.1 restores the CVE exposure. If rollback is required, apply the interim mitigation of ingress-level `Host:` header normalization (strip or rewrite to the canonical hostname) immediately and treat remediation as a P1 incident.
