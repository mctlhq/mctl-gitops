# Tasks: anthropic-sdk-compact-before-next-turn

- [ ] 1. Bump `anthropic-sdk-go` to v1.74.0 in `go.mod`/`go.sum` via
      `go get <module>@v1.74.0 && go mod tidy` — DoD: `go build ./...` succeeds,
      existing test suite passes unchanged.
- [ ] 2. Locate the diagnose-phase tool-runner construction used by LLMDiagnosis (and
      any other diagnose-phase skill performing multi-turn tool calls) (depends on 1)
      — DoD: exact file/function(s) identified and referenced in the PR description.
- [ ] 3. Wire in a call to `CompactBeforeNextTurn()` on the tool runner between turns
      of the diagnose loop (depends on 2) — DoD: code change is scoped to the
      tool-runner turn loop only; single-turn diagnose sessions are provably unaffected
      (see T2).
- [ ] 4. Extend existing skill/ticket metrics instrumentation (if not already present)
      to record per-diagnose-session token usage and latency (depends on 3) — DoD:
      metrics are emitted and queryable through mctl-agent's existing metrics/ticket
      storage, without touching circuit-breaker thresholds.
- [ ] 5. Capture a before/after comparison (token usage, latency) for diagnose sessions
      over a representative window post-deploy (depends on 4) — DoD: comparison
      documented in the PR or a follow-up note; expected direction (reduction in token
      usage / latency) confirmed or, if not observed, flagged for follow-up
      investigation.

## Tests
- [ ] T1. Unit/integration test: a multi-turn diagnose session (3+ turns, using a
      mocked or recorded Anthropic API transcript) invokes `CompactBeforeNextTurn()`
      between turns and completes with a correct diagnosis, matching pre-change
      expected output on the same fixture.
- [ ] T2. Unit test: a single-turn diagnose session (no follow-up tool call required)
      produces identical behavior/output before and after this change (confirms
      compaction doesn't alter the no-op single-turn path).
- [ ] T3. Regression test: full existing diagnose-phase / LLMDiagnosis test suite
      passes unchanged after the SDK bump and the `CompactBeforeNextTurn()` wiring.
- [ ] T4. Metrics test: per-session token usage and latency values are recorded and
      retrievable for at least one exercised diagnose session in a test/staging run.

## Rollback
Revert the `CompactBeforeNextTurn()` call site (task 3) as a single, isolated commit —
this is the only behavior-affecting change; the SDK version bump itself (task 1) can
remain even if compaction is reverted, since v1.74.0 has no breaking changes.
If quality regressions are observed (per task 5's before/after comparison), disable the
`CompactBeforeNextTurn()` call first before considering a full SDK downgrade.
Redeploy via ArgoCD sync to the previous `admins-mctl-agent` revision if a full
rollback is needed. No data migrations involved.
