# Tasks: go-github-upgrade

- [ ] 1. **Audit current go-github call sites** — Search the codebase for all `go-github/v68` imports and list every method called. DoD: A comment in the PR description listing all used methods and confirming which (if any) are affected by v68→v85 breaking changes.

- [ ] 2. **Bump `go.mod` and update import paths** (depends on 1) — Run `go get github.com/google/go-github/v85@v85.0.0`, then replace all `/v68/` import paths with `/v85/`. DoD: `go mod tidy` succeeds; `go build ./...` succeeds with zero errors.

- [ ] 3. **Fix any compilation errors from breaking API changes** (depends on 2) — Address `MarkThreadDone` (int64→string) and any org-role method signature changes if used. DoD: `go build ./...` and `go vet ./...` are clean.

- [ ] 4. **Adopt structured error logging** (depends on 3) — Wrap the PR creation call sites to log `(*github.ErrorResponse).Type()` at ERROR level via `slog`. DoD: A failing GitHub API call in tests logs a structured `github_error_type` field.

- [ ] 5. **Update and run unit tests** (depends on 3) — Update any mock or stub that referenced v68 types. Run `go test ./...` with `-race`. DoD: All tests pass; no races detected.

- [ ] 6. **Staging smoke test — PR creation end-to-end** (depends on 5) — Deploy to staging; trigger a test alert that exercises the full pipeline (alert → diagnose → fix PR). DoD: A PR is successfully created in `mctlhq/mctl-gitops`; PR contains the correct branch name, title, body, and label; no errors in service logs.

- [ ] 7. **Verify cross-host redirect protection** (depends on 6) — In the staging environment, configure a test HTTP server that returns a 301 to a different host and point a GitHub API call at it. DoD: The go-github client does NOT forward the `Authorization` header to the redirect target (observable via the test server's request log).

- [ ] 8. **Deploy to production** (depends on 7) — Update the ArgoCD `Application` image tag (or merge the GitOps PR). DoD: ArgoCD reports `Synced` and `Healthy`; PR creation succeeds in production within the first 30 minutes post-deploy; no auth-related errors in logs.

## Tests

- [ ] T1. All existing unit tests pass with `-race` on the updated library.
- [ ] T2. Mock GitHub client test: `PullRequestsService.Create` is called with the correct repo owner, repo name, base branch, and head branch.
- [ ] T3. Error type test: when the mock returns a 403 `github.ErrorResponse`, the structured `github_error_type` field appears in the `slog` output.
- [ ] T4. Cross-host redirect test (staging only): `Authorization` header is stripped on host-change redirect (Task 7).

## Rollback
1. Revert the `go.mod` change to `github.com/google/go-github/v68` and rebuild.
2. Revert the ArgoCD image tag to the prior version.
3. Note: rollback re-exposes the cross-host redirect vulnerability — escalate to the security team and treat as a P2 security incident until the forward fix is re-deployed.
