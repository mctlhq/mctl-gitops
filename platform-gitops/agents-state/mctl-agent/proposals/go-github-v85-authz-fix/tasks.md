# Tasks: go-github-v85-authz-fix

- [ ] 1. Audit go-github usage across the codebase —
  DoD: a list of all `.go` files importing `go-github/v68` and all API calls
  (`github.Client` methods) is captured in the PR description. Calls to `MarkThreadDone`
  and the Custom Org Role API (known breaking changes) are explicitly flagged.

- [ ] 2. Update `go.mod` (depends on 1) —
  DoD: `go.mod` contains `github.com/google/go-github/v85`; `go mod tidy` finishes without
  errors; `go.sum` is updated.

- [ ] 3. Replace all `v68` → `v85` imports (depends on 2) —
  DoD: `grep -r "go-github/v68" .` returns no results in .go files; all imports are
  switched to v85.

- [ ] 4. Address breaking changes (depends on 3) —
  DoD: `go build ./...` finishes without errors; all type/signature changes are documented
  in the commit message.

- [ ] 5. Run the test suite (depends on 4) —
  DoD: `go test ./... -race` — all tests green; no new race conditions.

- [ ] 6. Add a test for cross-host redirect rejection (depends on 4) —
  DoD: the test creates a mock server that returns a redirect to a different host and
  asserts that `github.Client` returns an error and does NOT issue the request to the
  redirect URL.

- [ ] 7. Integration smoke test for PR creation (depends on 5) —
  DoD: a test alert `PodCrashLooping` flows through the full pipeline → a PR is opened in
  mctl-gitops with the correct content; no 401/403 responses from the GitHub API.

## Tests

- [ ] T1. `go test ./internal/skill/builtin/... -v` — all builtin skills compile and tests
  pass with the new go-github version.
- [ ] T2. Cross-host redirect test (created in task 6) — `go test ./... -run TestCrossHostRedirect`.
- [ ] T3. `go vet ./...` — no new warnings.
- [ ] T4. Staging deploy: image with v85 deployed in admins/staging; over one token
  rotation cycle (30 min) verify GitHub API calls succeed.

## Rollback

```bash
# In the mctl-agent repository:
git revert <commit-sha-upgrade>
# Rebuild the image with v68
# Update the image tag in the GitOps manifest of the admins tenant
```

ArgoCD reconciles the rollback automatically. The GitHub token is unaffected — rotation
continues independently of the go-github version.
