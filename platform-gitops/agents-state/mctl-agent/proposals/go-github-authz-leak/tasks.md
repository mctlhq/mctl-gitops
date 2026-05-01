# Tasks: go-github-authz-leak

## Breaking API change migration plan

The following breaking changes between go-github v68 and v85.0.0 must be resolved before the version bump compiles:

| # | Symbol | Change | Action |
|---|---|---|---|
| B1 | `MarkThreadDone` | Parameter type `int64` → `string` | Convert all call sites: wrap `int64` IDs with `fmt.Sprintf("%d", id)` or refactor the ID type to `string` at the point of storage |
| B2 | `GetOrgRole` | Signature updated | Audit all call sites; update to new signature per v85 release notes; if unused in mctl-agent, confirmed by compile error only |
| B3 | `CreateCustomOrgRole` | Signature updated | Same as B2 |
| B4 | `UpdateCustomOrgRole` | Signature updated | Same as B2 |

---

- [ ] 1. Audit all go-github call sites in mctl-agent — run `grep -r "go-github/v68" .` and `grep -r "github\.MarkThreadDone\|GetOrgRole\|CreateCustomOrgRole\|UpdateCustomOrgRole" .` to enumerate every affected file. — DoD: a list of every file and line number that imports or calls the changed symbols is documented in the PR description.

- [ ] 2. Update `go.mod` and `go.sum` (depends on 1) — change the require directive from `github.com/google/go-github/v68` to `github.com/google/go-github/v85 v85.0.0`; run `go get` and `go mod tidy`. — DoD: `go.mod` contains `require github.com/google/go-github/v85 v85.0.0`; `go mod verify` exits 0; no v68 reference remains in `go.mod` or `go.sum`.

- [ ] 3. Update all import paths from `/v68/` to `/v85/` (depends on 2) — use `sed` or IDE refactor to replace `github.com/google/go-github/v68` with `github.com/google/go-github/v85` in every `.go` file. — DoD: `grep -r "go-github/v68" .` returns zero matches in `.go` files.

- [ ] 4. Migrate `MarkThreadDone` call sites — breaking change B1 (depends on 3) — for every call site identified in task 1 that passes an `int64` thread ID, convert the argument to `string`. Prefer storing the thread ID as a `string` from the point of receipt to avoid `fmt.Sprintf` churn. — DoD: `go build ./...` exits 0 for all packages containing `MarkThreadDone`; no `int64`-to-`string` implicit conversion warnings.

- [ ] 5. Migrate `GetOrgRole`, `CreateCustomOrgRole`, `UpdateCustomOrgRole` call sites — breaking changes B2–B4 (depends on 3) — update signatures at each call site per the v85 release notes. If these functions are not called in mctl-agent, document that in the PR description. — DoD: `go build ./...` exits 0 globally; no remaining references to the old signatures.

- [ ] 6. Update test mocks and fixtures (depends on 4, 5) — any test that instantiates a go-github type or uses a mock HTTP server returning v68-shaped responses must be updated to match v85 types. — DoD: `go test ./...` exits 0; no test is deleted or skipped; coverage does not decrease.

- [ ] 7. Run full CI and open PR (depends on 6) — push the branch and confirm the pipeline is green. PR title: "security: upgrade go-github v68 → v85.0.0 (authz header leakage fix)". — DoD: CI is green; PR description enumerates the security fix (cross-host redirect rejection) and all four breaking-change migrations (B1–B4); at least one reviewer approves.

- [ ] 8. Post-deploy smoke test (depends on 7, after merge and ArgoCD sync) — trigger a synthetic alert that causes mctl-agent to open a PR in `mctlhq/mctl-gitops` and verify it succeeds end-to-end. — DoD: a PR is created in `mctlhq/mctl-gitops` with the expected content; no error logs related to go-github; GitHub API response is 201.

## Tests

- [ ] T1. Table-driven unit test for cross-host redirect rejection — add `internal/github/redirect_test.go` with a table-driven test that spins up two local HTTP test servers (same-host and cross-host) and asserts that the go-github client forwards the `Authorization` header only to the same host and drops it on cross-host redirects. Table rows: same-host redirect (header forwarded), cross-host redirect (header stripped/error returned). — DoD: test passes under v85.0.0; test would fail if run against a client without cross-host redirect rejection.

- [ ] T2. Table-driven test for `MarkThreadDone` type migration — add test rows to the existing notification tests (or a new `internal/github/notifications_test.go`) covering: valid string thread ID, empty string (expect error), numeric string (expect success). — DoD: all rows pass; no `int64` type assertion in test code.

- [ ] T3. Regression test for PR-creation pipeline — the existing table-driven tests for the fix-PR skill must continue to pass without modification to test logic. — DoD: `go test ./internal/skill/...` and `go test ./internal/github/...` pass with the same test count as before the upgrade.

- [ ] T4. Integration test (staging environment) — deploy the upgraded image to a staging or preview environment and confirm that the end-to-end alert-to-PR flow completes successfully. — DoD: a PR appears in the staging gitops repository; no error events in the pod logs during the test run.

## Rollback
1. Revert the PR (GitHub "Revert" button) — this restores `go.mod`, `go.sum`, and all call sites to go-github v68 in a single commit.
2. Trigger an ArgoCD sync to redeploy the previous image tag.
3. Confirm the running pod is using the v68 image by checking the image tag in `kubectl describe pod`.
4. The GitHub installation token is not affected by the rollback; no credential rotation is needed.
5. File a follow-up issue describing the regression before re-attempting the upgrade. The cross-host redirect vulnerability remains open until the upgrade is successfully re-applied — treat as a P1 security debt item.

Note: no database migrations are involved; rollback is purely a binary swap.
