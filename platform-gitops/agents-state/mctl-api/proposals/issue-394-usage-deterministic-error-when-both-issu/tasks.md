# Tasks: issue-394-usage-deterministic-error-when-both-issu

- [ ] 1. In `internal/usage/types.go` `(*Record).validateCorrelation()`, replace `map[string]*int64{"issue_number": ..., "pr_number": ...}` with an ordered `[]struct{ name string; v *int64 }{{"issue_number", r.IssueNumber}, {"pr_number", r.PRNumber}}`, and add a short comment saying the order is fixed so the error is deterministic. — DoD: no map is used for these fields; the error messages are byte-for-byte identical to before; `go build ./...` passes.
- [ ] 2. (depends on 1) Add tests in `internal/usage/usage_test.go` covering both numbers invalid (see Tests). — DoD: the tests pass against the new code and fail (at least intermittently, with high probability over repeated iterations) against the old map-based code.
- [ ] 3. (depends on 1, 2) Run `go fmt ./...`, `go vet ./...`, `golangci-lint run` and `go test ./internal/usage/... ./internal/api/...`. — DoD: all clean and green.

## Tests
- [ ] T1. Both non-positive with a repo: `{TargetRepo: "mctlhq/x", IssueNumber: 0, PRNumber: -1}`. `Validate()` returns an error that wraps `ErrInvalidRecord` and contains `issue_number must be positive` and not `pr_number`. Repeat 50 times in a loop.
- [ ] T2. Both set without a repo: `{IssueNumber: 12, PRNumber: 13}`. The error contains `issue_number requires target_repo` on every one of 50 iterations.
- [ ] T3. Mixed: `{TargetRepo: "mctlhq/x", IssueNumber: 5, PRNumber: 0}`. The error names `pr_number must be positive`. This confirms the second field is still checked when the first is valid.
- [ ] T4. The existing `TestCorrelationShapesAreValidatedAtIngest` valid and invalid tables still pass unchanged. Optionally add the T1/T2 inputs to its `invalid` table as well.

## Rollback
Revert the single commit. It touches only `internal/usage/types.go` and `internal/usage/usage_test.go`, with no schema, config or API-contract change, so a revert followed by a normal redeploy restores the previous behaviour (still correct, just with a nondeterministic message).
