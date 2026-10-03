# Tasks: anthropic-sdk-v175-compaction-fix

- [ ] 1. Confirm status of sibling proposal `anthropic-sdk-compact-before-next-turn`
      (v1.74.0 bump + `CompactBeforeNextTurn()` wiring) — DoD: known whether it is
      merged, in-flight, or not started, to decide whether this proposal is a follow-up
      bump or should be folded into that same PR.
- [ ] 2. Bump `anthropic-sdk-go` to v1.75.0 in `go.mod`/`go.sum` via
      `go get github.com/anthropics/anthropic-sdk-go@v1.75.0 && go mod tidy` (depends
      on 1) — DoD: `go build ./...` succeeds; no call-site changes required.
- [ ] 3. Re-run (or add, if not yet present from the sibling proposal) a multi-turn
      diagnose-session test that exercises `CompactBeforeNextTurn()` and asserts the
      resulting compaction request contains no reply-only parameters (depends on 2) —
      DoD: test passes against v1.75.0 and is added to the permanent diagnose-phase
      test suite.
- [ ] 4. Verify `AddTools()` takes effect on the very next turn in a test that
      registers a tool mid-session (depends on 2) — DoD: test asserts the newly
      registered tool is usable on the immediately following turn, not one turn later.
- [ ] 5. Verify open-object tool-parameter unmarshalling preserves unmodeled extra
      fields (depends on 2) — DoD: a test fixture with an extra field on an open-object
      param round-trips without data loss.

## Tests
- [ ] T1. Regression: full existing diagnose-phase / LLMDiagnosis test suite passes
      unchanged after the v1.75.0 bump.
- [ ] T2. Compaction-request-shape test: a mocked/recorded multi-turn transcript
      confirms the post-compaction request omits reply-only parameters (see task 3).
- [ ] T3. `AddTools()` immediacy test (see task 4).
- [ ] T4. Open-object extra-field preservation test (see task 5).

## Rollback
Revert the `go.mod`/`go.sum` bump back to v1.74.0 in a single commit — this proposal
makes no call-site changes, so rollback is a pure dependency-version revert. If the
sibling `CompactBeforeNextTurn()` wiring itself needs to be rolled back, follow that
proposal's own rollback plan (disable the call site, optionally keep the SDK version).
Redeploy via ArgoCD sync to the previous `admins-mctl-agent` revision if a full
rollback is needed. No data migrations involved.
