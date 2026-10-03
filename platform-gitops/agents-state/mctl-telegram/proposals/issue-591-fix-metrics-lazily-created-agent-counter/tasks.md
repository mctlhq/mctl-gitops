# Tasks: issue-591-fix-metrics-lazily-created-agent-counter

- [ ] 1. Add the closed label-value sets to `internal/metrics/metrics.go`: a `const`
      block with `ClaudeResultClassUsageLimit`/`ClaudeResultClassOther` and
      `JobCostResultSuccess`/`JobCostResultError`, plus package-level slices
      `claudeResultClasses` and `jobCostResults`. Place them next to the existing
      `PolicySurface*` const block (lines 165-179) and follow its comment style.
      — DoD: `go build ./...` passes; each const carries a comment naming the counter
      it labels; the slices are documented as the single source of truth for the
      zero baseline.

- [ ] 2. Pre-create the four children in `metrics.New()` (depends on 1): loop over
      `claudeResultClasses` calling `r.AgentClaudeResultErrorsTotal.WithLabelValues(class).Add(0)`
      and over `jobCostResults` calling `r.AgentJobCostUSDTotal.WithLabelValues(result).Add(0)`,
      inserted after the `MustRegister` block (metrics.go:390-421) and before
      `return r`. Include the explanatory comment: why a non-zero first sample makes
      `increase()` read 0, and that it is issue #591. **Amended:** also loop over
      the six `mctl_agent_jobs_total` statuses and all 18 x 6 = 108
      `AgentPolicyDenialsTotal` combinations — 118 series across four families.
      See requirements.md, "Scope expanded during implementation", for why the
      original exclusion of those two counters was reversed.
      — DoD: a fresh `metrics.New()` gathers metric families
      `mctl_agent_claude_result_errors_total` and `mctl_agent_job_cost_usd_total`,
      each with exactly two children at value 0, with no job ever processed.

- [ ] 3. Use the new constants at the increment sites in
      `internal/agentworker/claudeinvoker.go` (depends on 1): replace the `"success"`/
      `"error"` literals in `recordCost` (lines 247-250) and the `"other"`/`"usage_limit"`
      literals in `countResultError` (lines 266-269) with `metrics.JobCostResult*` /
      `metrics.ClaudeResultClass*`. No behavior change, no new import (the package
      already imports `internal/metrics`).
      — DoD: `go build ./... && go vet ./...` pass; `git grep -n '"usage_limit"\|"success"'
      internal/agentworker/claudeinvoker.go` returns nothing outside tests; the existing
      `claudeinvoker_test.go` metric tests still pass unmodified.

- [ ] 4. Update the struct-field doc comments for `AgentJobCostUSDTotal` (metrics.go:142-146)
      and `AgentClaudeResultErrorsTotal` (lines 148-152) so each states that its children
      are pre-created at zero at registry construction, and why (depends on 2).
      — DoD: both comments name issue #591 and the `increase()` baseline reason; the
      existing "Bound: 2 series" wording is preserved.

- [ ] 5. Update `docs/agent-worker.md` (depends on 2): in the "Metrics: `/metrics` on
      `AGENT_HEALTH_ADDR`" section, add a sentence that the two agent counters are the
      deliberate exception to the closing note "vec families with no children simply
      don't appear" — they are pre-created at zero so first-occurrence alerts work.
      Add a matching clarifying clause to the `MctlAgentClaudeUsageLimit` section of
      `docs/runbook.md` (near lines 408-415) noting its manual queries now return `0`
      rather than "no data" on an idle worker.
      — DoD: both docs read correctly against the new behavior; no alert expression text
      in either doc is altered.

- [ ] 6. Verify `deploy/alerts/mctl-telegram.rules.yaml` is untouched (depends on 2).
      — DoD: `git diff --stat deploy/` is empty for the PR; `deploy/alerts/runbook_links_test.go`
      and the promtool suite still pass.

## Tests

- [ ] T1. `TestNew_AgentCounterZeroBaseline` in `internal/metrics/metrics_test.go`:
      call `New()` with no other interaction, `Gather()`, locate
      `mctl_agent_claude_result_errors_total` and `mctl_agent_job_cost_usd_total` in the
      returned `[]*dto.MetricFamily`, and assert each has exactly 2 metrics whose label
      pairs are `{class=usage_limit}`/`{class=other}` and `{result=success}`/`{result=error}`
      and whose `GetCounter().GetValue()` is 0. Assert on the parsed families, not a
      string dump (issue DoD).
      — DoD: fails if either loop is removed from `New()` or a label value is renamed.

- [ ] T2. **Superseded.** Originally: assert `mctl_agent_policy_denials_total` is
      ABSENT from a freshly gathered `New()` registry. That decision was reversed
      during review — see requirements.md, "Scope expanded during implementation".
      The replacement asserts the opposite: all 108 children present at `0`, plus a
      guard that the label space is still 18 x 6 so the documented bound and the
      code cannot drift. A drift test in `internal/agent/policy` pins the reason
      list against the `DenyCode` constants, mirroring what `internal/db` does for
      the job statuses.

- [ ] T3. `TestCountResultError_FirstOccurrenceIsARealIncrease` in
      `internal/agentworker/claudeinvoker_test.go`: build `m := metrics.New()`, assert
      `testutil.ToFloat64(m.AgentClaudeResultErrorsTotal.WithLabelValues("usage_limit")) == 0`
      BEFORE any invocation, call `countResultError` once with an error wrapping
      `ErrClaudeUsageLimit`, and assert the value is 1 — the 0 -> 1 transition a
      Prometheus `increase()` can observe.
      — DoD: the pre-assertion fails on the current `main`.

- [ ] T4. Mirror of T3 for cost: a fresh registry reads 0 for both
      `AgentJobCostUSDTotal{result="success"}` and `{result="error"}`, and one
      `recordCost` with a positive `TotalCostUSD` and `IsError=false` moves only
      `success`. Reuse the existing `recordCost` test scaffolding at
      `claudeinvoker_test.go:305-345`.

- [ ] T5. Regression guard for the shared constructor: confirm
      `TestNew_RegistersAllMetrics` and `TestNew_RegistersIssue580Metrics` still pass
      unchanged, and run `go test ./...` to catch any test asserting an exact series
      count or exposition dump over the two affected families.

- [ ] T6. `go test ./cmd/agent-worker/...` — the `/metrics` handler tests
      (`health_server_test.go:78-120`) exercise `newHealthServer` with a real
      `metrics.New()`; confirm the four zero series appear in the served body and the
      `AGENT_METRICS_ALLOW_CIDR` guard behavior is unchanged.

## Rollback

The change is confined to `internal/metrics/metrics.go`, the two label-literal sites in
`internal/agentworker/claudeinvoker.go`, two docs, and tests — no schema, no config, no
alert-expression change, so a plain `git revert` of the merge commit is a complete and
safe rollback. After revert, the four series stop being emitted until first use; alerts
return to their current (issue #591) miss-the-first-occurrence behavior, which is a
detection gap, never a false alarm, so no operator action is needed beyond the normal
agent-worker rollout. If a problem is observed only in one process, the narrower rollback
is to move the two pre-init loops out of `New()` and into a worker-only initializer
called from `cmd/agent-worker/main.go` next to the existing
`AgentCredentialDomain.WithLabelValues(...).Set(1)` (design.md alternative A) — that
preserves the fix where it matters while removing the four series from `cmd/server`.

## Amendment — 2026-09-09

Tasks 2 and T2 above are amended in place rather than rewritten, so the reversal
stays legible. Anything in this file that still reads as though
`AgentPolicyDenialsTotal` or `mctl_agent_jobs_total` are out of scope is
superseded by requirements.md's "Scope expanded during implementation" section.
Implemented in mctlhq/mctl-telegram#593; do not re-run an implementer against
this proposal.
