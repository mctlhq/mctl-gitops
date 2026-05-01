# Tasks: go-oidc-dep-bump

- [ ] 1. Update `go.mod` to set `github.com/coreos/go-oidc/v3 v3.18.0` — DoD: `go.mod` contains the correct version line; `go mod tidy` runs without error; `go.sum` is regenerated and committed alongside `go.mod`; diff contains only `go.mod` and `go.sum` changes
- [ ] 2. Verify build and tests pass (depends on 1) — DoD: `go build ./...` exits 0; `go test ./...` exits 0 with no skipped auth-related tests; CI pipeline is green on the PR branch

## Tests

- [ ] T1. `go test ./...` passes in full — specifically the Dex JWT, GitHub OAuth, and OAuth JWT verification paths produce the same results as before the bump
- [ ] T2. `go mod verify` exits 0 confirming all module checksums match `go.sum`
- [ ] T3. CI `go mod tidy` idempotency check: running `go mod tidy` again on the committed `go.mod`/`go.sum` produces no diff

## Rollback
Revert `go.mod` and `go.sum` to the previous committed state (`git revert` or `git checkout HEAD~1 -- go.mod go.sum`) and run `go build ./...` to confirm the previous version restores cleanly. No infrastructure changes are involved; rollback is instantaneous and requires only a standard deployment of the reverted binary.
