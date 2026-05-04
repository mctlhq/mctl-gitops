# Tasks: bump-go-github

- [ ] 1. Run `go get github.com/google/go-github/v85@v85.0.0 && go mod tidy` in the repo root —
  DoD: `go.mod` declares `github.com/google/go-github/v85 v85.0.0`; `go.sum` is consistent; no
  other module version is changed unexpectedly.

- [ ] 2. Update all import paths from `github.com/google/go-github/v68/github` to
  `github.com/google/go-github/v85/github` across all `.go` files (depends on 1) —
  DoD: `grep -r "go-github/v68"` returns zero matches; project compiles with `go build ./...`.

- [ ] 3. Resolve any API surface changes — type errors, renamed fields, removed methods — that
  surface after the import-path update (depends on 2) —
  DoD: `go build ./...` and `go vet ./...` both exit 0 with no errors.

- [ ] 4. Run the full unit-test suite (depends on 3) —
  DoD: `go test ./...` exits 0; no tests are skipped that were previously passing.

- [ ] 5. Open a PR with the changes; ensure CI passes (depends on 4) —
  DoD: GitHub Actions (or equivalent) reports green; PR description references this proposal and
  lists the three security fixes addressed.

## Tests

- [ ] T1. Verify existing GitHub-client unit tests continue to pass after the import-path update —
  all table-driven tests in `internal/skill/builtin/` and any `github_client_test.go` files exit 0.

- [ ] T2. Add a new test `TestGitHubClientRejectsXHostRedirect` that spins up two local HTTP servers
  (host A and host B), configures the v85 client to point at host A, and asserts that a 301 redirect
  from host A to host B causes the client to return an error rather than following the redirect —
  DoD: test exists, is table-driven per project convention, and passes.

- [ ] T3. Add a test `TestGitHubClientRejectsDotDotPath` that attempts to construct a request URL
  containing a `..` segment and asserts the client returns a path-validation error —
  DoD: test exists and passes.

## Rollback
Revert the `go.mod`/`go.sum` changes and import-path updates via `git revert <merge-commit>`.
Because this is a dependency-only change with no schema or API surface modifications, rollback
restores the previous binary behavior completely. No database migrations or configuration changes
need to be undone. Redeploy via the standard ArgoCD sync.
