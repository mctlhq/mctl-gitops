# Tasks: go-github-v85-migration

- [ ] 1. Run `go get github.com/google/go-github/v85@v85.0.0 && go mod tidy` in the
  repository root — DoD: `go.mod` references `github.com/google/go-github/v85`; the v68
  entry is absent from `go.mod` and `go.sum`; `go mod verify` exits 0.

- [ ] 2. Rewrite all import paths from `v68` to `v85` across the codebase (depends on 1)
  — DoD: `grep -r "go-github/v68" .` returns no matches; `go build ./...` exits 0 (even
  before breaking-change fixes, confirming the path rewrite is complete and isolated from
  API changes).

- [ ] 3. Fix `ActivityService.MarkThreadDone` call site(s) to use the v85 parameter type
  (depends on 2) — DoD: the call site compiles with the v85 signature; the argument value
  is semantically equivalent to the v68 call; a unit test exercises the updated call path.

- [ ] 4. Fix any custom org role option call sites to use the corrected v85 API (depends
  on 2) — DoD: `go build ./...` and `go vet ./...` both exit 0; if no such call site
  exists in mctl-agent, task is marked done with a one-line comment in the PR description
  confirming absence.

- [ ] 5. Run the full test suite (depends on 3, 4) — DoD: `go test ./...` exits 0 with no
  skipped tests that were previously passing; test coverage on the GitHub PR creation path
  is unchanged or improved.

- [ ] 6. Validate in the staging environment by triggering a synthetic alert that drives
  the fix pipeline to open a real PR in the test fork of `mctlhq/mctl-gitops` (depends
  on 5) — DoD: PR is created successfully; PR metadata (title, body, branch) matches the
  expected format; no error logs referencing the GitHub client are emitted.

- [ ] 7. Deploy to `admins` tenant via ArgoCD and monitor GitHub API error rate for 24
  hours (depends on 6) — DoD: error rate on GitHub API calls is within the pre-upgrade
  baseline (measured from `slog` error counts); no incidents are raised; ArgoCD sync
  status is `Synced`.

## Tests

- [ ] T1. Unit: `TestGitHubPRCreation_v85` — mock GitHub server returns 201; assert
  `PullRequestsService.Create` is called with the correct owner, repo, and
  `NewPullRequest` fields; assert returned PR URL is non-empty.
- [ ] T2. Unit: `TestMarkThreadDone_v85Signature` — assert the call compiles and passes
  the correct parameter type; mock server returns 204.
- [ ] T3. Unit: `TestGoModNoV68References` — a test that shell-execs
  `grep -r "go-github/v68" .` and asserts the output is empty; acts as a regression guard
  to prevent accidental re-introduction of the old import.
- [ ] T4. Integration: `TestFixPipelineEndToEnd_v85` — full pipeline test with a real (or
  WireMock-equivalent) GitHub API stub; confirms PR creation succeeds and the ticket is
  marked as fixed in the SQLite DB.

## Rollback
1. Revert the migration commit (`git revert <sha>`) and push to the release branch. ArgoCD
   will detect the updated image tag and redeploy the v68-based build.
2. Because `go.sum` is committed, the reverted build is deterministic — no re-fetching of
   modules is required.
3. If the rollback is triggered after a PR has already been opened via the v85 path, those
   PRs are unaffected (they exist on GitHub independently of the library version).
