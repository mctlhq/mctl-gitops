# Tasks: go-github-v85-upgrade

- [ ] 1. Audit call sites for breaking-API symbols — DoD: grep output confirms zero uses of `GetOrgRole`, `CreateCustomOrgRole`, `UpdateCustomOrgRole`, `MarkThreadDone` in the mctl-agent codebase; result documented in the PR description.

- [ ] 2. Update `go.mod` and `go.sum` — replace `github.com/google/go-github/v68` with `github.com/google/go-github/v85`; run `go mod tidy` — DoD: `go.mod` references `v85`, `go.sum` is consistent, `go mod verify` passes.

- [ ] 3. Replace all import paths in Go source files — find-replace `go-github/v68` → `go-github/v85` across `*.go` files (depends on 2) — DoD: `grep -r "go-github/v68"` returns zero matches; `go build ./...` succeeds.

- [ ] 4. Fix any compilation errors from API changes (depends on 3) — DoD: `go build ./...` produces zero errors; if any of the four changed symbols were found in step 1 (contrary to expectation), they are updated to v85 signatures.

- [ ] 5. Run full unit and integration test suite (depends on 4) — DoD: `go test ./...` passes with no failures; test coverage for the GitHub PR creation path is unchanged or improved.

- [ ] 6. Update vendor directory if vendoring is used (depends on 5) — run `go mod vendor` — DoD: `vendor/github.com/google/go-github` directory reflects v85; CI uses vendor directory without download.

- [ ] 7. Deploy to staging and validate PR creation end-to-end (depends on 6) — DoD: at least one test alert triggers a fix PR successfully in staging; ArgoCD application in `admins` shows healthy after rollout.

## Tests

- [ ] T1. Unit test: mock GitHub HTTP server returns a redirect to a different host; assert that the go-github v85 client returns an error and does NOT follow the redirect.
- [ ] T2. Unit test: mock GitHub HTTP server returns a redirect to a path containing `..`; assert the client returns an error.
- [ ] T3. Integration test: existing PR creation path for at least two builtin skills (e.g., OOMKilled, ArgoCDDrift) produces a valid PR object against the test repository.
- [ ] T4. Regression test: `go vet ./...` and `staticcheck ./...` pass cleanly.

## Rollback

1. Revert `go.mod` and `go.sum` to the v68 entries (keep in git history as a prior commit).
2. Revert import path find-replace (`v85` → `v68`) in Go source files.
3. Run `go build ./...` and `go test ./...` to confirm clean build.
4. Re-deploy via ArgoCD sync to the previous image tag.
5. The installation token is short-lived (30 min rotation); no credential revocation needed.
