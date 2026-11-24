# Tasks: issue-1177-spike-architecture-architecture-fitness

## S0: research (this proposal; no code changes)

- [ ] 1. Publish the S0 findings pinned to `1fd4ed5e`. These are the import
  graph, the leakage into `cmd/mcp`, the `workitems -> glovo` edge, the
  inventory of existing purity tests, and the CI/CODEOWNERS/ADR map. Include
  the reproduction commands.
  - DoD: anyone can rerun the commands in design.md on that commit and get
    the same counts: 78 packages, `cmd/mcp` with 675 dependencies including
    pgx, and `internal/mcp` with 8 internal edges.
- [ ] 2. Run an independent P1/P2/P3 review of this exact proposal revision
  (depends on 1).
  - DoD: review findings are recorded, and every P1 and P2 finding is
    resolved or explicitly accepted by the owner.
- [ ] 3. Get the owner decision on the open questions (depends on 2): the
  Python-versus-Go scope, whether code-owner review is required, whether a
  Merge Queue is enabled, and whether `auth` is an allowed edge or a
  baselined edge.
  - DoD: the answers are recorded in the proposal. An explicit owner GO for
    S1 is recorded against the reviewed digest, or a no-go.

## S1: offline pilot (only after an explicit owner GO in task 3)

- [ ] 4. Add the pure checker `classify(deps, directEdges, policy, baseline)`
  in `internal/mcp/boundary_test.go`. Matching is exact, or by prefix at a
  `/` boundary only (depends on 3).
  - DoD: unit cases T1-T6 pass, and no production file changes.
- [ ] 5. Add the `go list` wrapper with fail-closed guards (depends on 4).
  It fails when `go list` errors or returns fewer than 10 dependencies. It
  uses production files only. Each forbidden dependency is attributed to the
  direct edge that brings it in.
  - DoD: T7 and T8 pass.
- [ ] 6. Add the baseline literal: 7 edges (`auth`, `domains`, `lifecycle`,
  `usage`, `workitems`, `temporalclient`, `operations`), each with owner,
  reason and expiry, and a ceiling constant of 7 (depends on 5).
  - DoD: running the test on current `main` produces 0 failures and 0
    `ARCH-REPORT` lines.
- [ ] 7. Add the negative fixture module `internal/mcp/testdata/violator/`
  (own `go.mod`, imports `database/sql`) and the test that runs the wrapper
  against it (depends on 5).
  - DoD: the test fails if the planted violation is not reported, and
    `go test ./...` does not pick up `testdata`.
- [ ] 8. Add an authorization contract test for `NewServer` (depends on 3).
  It uses an `httptest` server and asserts that the bearer token is sent to
  `apiURL` only, and that API refusals (403/404) are passed through as tool
  errors.
  - DoD: T10 and T11 pass, and the `server_test.go` tool count is unchanged
    at 123.
- [ ] 9. Record the CI budget (depends on 6-8).
  - DoD: measure the `go test ./internal/mcp/` runtime before and after
    (local and in `validate.yml`). The added time is under 5 s, or the
    overrun is reported to the owner.
- [ ] 10. Start the measurement window (depends on 9): the 8-week
  pre-merge baseline, then 4 weeks of report-only data, stratified by
  changed-LOC bucket and model. Document gaps such as missing per-PR token
  attribution.
  - DoD: a descriptive report is produced with no causal claims. The S2
    go/no-go (switch to fail-on-new, remove baselined edges) is filed as a
    separate proposal.

## Tests

- [ ] T1. `classify`: a dependency list containing `github.com/jackc/pgx/v5`
  that is not in the baseline is reported as a new violation.
- [ ] T2. `classify`: `.../internal/glovo/orders` matches the forbidden
  prefix `/internal/glovo`. `github.com/jackc/pgxfoo` and
  `.../internal/glovoish` do not match.
- [ ] T3. `classify`: a baseline entry with no current matching edge is
  reported as stale, and the test fails.
- [ ] T4. `classify`: an entry missing owner, reason or expiry, or a
  baseline count above the ceiling, is a hygiene failure.
- [ ] T5. `classify`: an entry whose expiry is in the past is reported as
  expired (report-only).
- [ ] T6. `classify`: a wildcard or over-broad baseline entry, such as
  `internal/` or `*`, is rejected.
- [ ] T7. Wrapper: a simulated `go list` error, or fewer than 10
  dependencies, makes the test fail (fail closed).
- [ ] T8. Wrapper on the real `internal/mcp`: the 7 baselined edges are
  attributed correctly, with 0 new violations.
- [ ] T9. Negative fixture: the wrapper on `testdata/violator` reports
  `database/sql`.
- [ ] T10. Contract: a tool call from `NewServer` sends
  `Authorization: Bearer <token>` to the configured `apiURL`, and makes no
  request to any other host.
- [ ] T11. Contract: an API 403 or 404 response becomes a tool error. It is
  never an empty success.

## Rollback

S0 has nothing to roll back: it is a proposal only. S1 adds only
`internal/mcp/boundary_test.go`, the `testdata/violator/` fixture and the
contract test, with no production code, dependency, CI workflow or required
check. To roll back, revert that single PR. Because S1 is report-only, a
false positive cannot block merges. Only a checker-integrity or
baseline-hygiene failure can fail the test, and the owner can revert it or
fix it in one reviewed PR.
