# Pre-initialize the agent worker's lazily-created counter children so the first occurrence is a real increase

## Context

`mctl_agent_claude_result_errors_total{class}` and `mctl_agent_job_cost_usd_total{result}`
are `prometheus.CounterVec`s constructed in `internal/metrics/metrics.go` (`New()`,
lines 373-381) whose children are only materialized on first use, inside
`ClaudeInvoker.recordCost` and `ClaudeInvoker.countResultError`
(`internal/agentworker/claudeinvoker.go:234-271`). A Prometheus counter whose first
observed sample is already non-zero yields `increase() == 0` for that first sample,
because the first scrape becomes the range's baseline. The two alerts mirrored in
`deploy/alerts/mctl-telegram.rules.yaml` — `MctlAgentClaudeUsageLimit`
(`sum(increase(mctl_agent_claude_result_errors_total{class="usage_limit"}[15m])) > 0`)
and `MctlAgentJobCostHigh` (both clauses over `increase(mctl_agent_job_cost_usd_total[1h])`)
— can therefore miss the first, and in the usage-limit case very likely the only,
occurrence they exist to catch. `agentworker.Worker.Loop` is sequential, so once the
Claude credential's pool is exhausted no second increment arrives to rescue the
expression.

The fix is the documented Prometheus practice: create the children with value `0`
when the registry is built, so a real zero baseline exists before the worker accepts
any job. Both label spaces are closed and tiny — `class` is `usage_limit`/`other`,
`result` is `success`/`error` — four series in total. The promtool cases in
`deploy/alerts/mctl-telegram.rules_test.yaml` do not catch the gap because every
seeded `input_series` starts at `0` (e.g. `values: '0+1x20'`), which is exactly the
synthetic zero the real process never emits today. This is a missed-detection bug,
not a false alarm: nothing currently mis-fires.

## User stories

- AS an operator on call for the communication agent I WANT the usage-limit alert to
  fire on the very first usage-limit stop after a worker start SO THAT I learn the
  Claude credential is exhausted instead of silently watching a stalled queue.
- AS an operator running a cost-bounded test window I WANT the job-cost alert to see
  the spend of the first expensive job SO THAT a single runaway job cannot spend an
  hour's budget undetected.
- AS a maintainer of `internal/metrics` I WANT the closed label sets of these two
  counters expressed once in code SO THAT a new class or result value cannot be added
  at the increment site without also being given a zero baseline.

## Acceptance criteria (EARS)

- WHEN `metrics.New()` returns THE SYSTEM SHALL have already created the children
  `mctl_agent_claude_result_errors_total{class="usage_limit"}`,
  `mctl_agent_claude_result_errors_total{class="other"}`,
  `mctl_agent_job_cost_usd_total{result="success"}` and
  `mctl_agent_job_cost_usd_total{result="error"}`, each with value `0`.
- WHILE a freshly started `cmd/agent-worker` process has claimed no job THE SYSTEM
  SHALL expose those four series at `0` on the `/metrics` route served by
  `newHealthServer` (`cmd/agent-worker/health_server.go`).
- WHEN `ClaudeInvoker.countResultError` classifies the first usage-limit error THE
  SYSTEM SHALL move `mctl_agent_claude_result_errors_total{class="usage_limit"}` from
  `0` to `1`, so `increase(...[15m])` over that transition is `1`, not `0`.
- WHEN `ClaudeInvoker.recordCost` records the first job's spend THE SYSTEM SHALL add
  it to a child that already existed at `0`, so both clauses of
  `MctlAgentJobCostHigh` observe the full amount as an increase.
- WHEN `metrics.New()` returns THE SYSTEM SHALL also have created every child of
  `mctl_agent_jobs_total` (six statuses) and of `mctl_agent_policy_denials_total`
  (18 reasons x 6 surfaces), each with value `0` — 118 series in total across the
  four families. **Superseded criterion:** this originally read "SHALL leave
  `mctl_agent_policy_denials_total` with no children"; see "Scope expanded during
  implementation" below for why that was reversed.
- IF a future label value is added to the `class` or `result` label THEN THE SYSTEM
  SHALL take its zero baseline from the same exported, single-source-of-truth list
  that `countResultError` and `recordCost` select their label value from.
- WHEN the test suite runs THE SYSTEM SHALL assert the four zero-valued children by
  gathering metric families from the registry and inspecting label pairs and values,
  not by comparing an exposition-format string dump.
- WHILE this change is in effect THE SYSTEM SHALL leave every alert expression in
  `deploy/alerts/mctl-telegram.rules.yaml` byte-identical.

## Out of scope

- Any change to alert expressions, `for:` durations, thresholds, or annotations in
  `deploy/alerts/mctl-telegram.rules.yaml` (a mirror; see the comment at line 199) or
  in the deployed copy in `mctl-gitops`
  (`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-ops.yaml`).
- The PromQL "newly appearing positive series" workaround (`X > 0 unless X offset 15m`),
  explicitly rejected in the issue.
- `mctl_agent_credential_domain`, which is already set explicitly at worker startup
  (`cmd/agent-worker/main.go:98`) and is an info gauge, not a counter.
- Other lazily-created `CounterVec`s in the registry (HTTP, auth, session, bridge,
  tool families). Their alerts are rate/ratio-based over high-traffic series where a
  first-sample baseline is not a realistic miss; auditing them is a separate concern.

## Open questions

- Should the zero baseline live in `metrics.New()` (every process, including
  `cmd/server`, gets the four series) or behind a worker-only initializer called from
  `cmd/agent-worker/main.go`? This proposal takes `New()`: `docs/agent-worker.md`
  states the worker deliberately reuses the same registry constructor "so every
  `mctl_*` name stays defined in exactly one file", a worker-only call site can be
  forgotten by a future entrypoint, and four constant-zero series on `cmd/server`
  contribute exactly `0` to every `sum(increase(...))` in both affected rules.
- Whether to add a promtool case to `deploy/alerts/mctl-telegram.rules_test.yaml`
  seeding a series that starts at `1` (the pre-fix shape) to document that PromQL
  cannot see it. Treated as out of scope here: such a case asserts a non-firing alert
  for a state the emitter can no longer produce, and the DoD asks for a registry-level
  test instead.

## Scope expanded during implementation (2026-09-09)

Two counters this document had placed out of scope were brought back in during
review of the implementing PR, mctlhq/mctl-telegram#593. Both exclusions rested on
reasoning that did not survive contact with a reviewer, and this section records
the reversal so the shipped code and this document do not disagree.

**`mctl_agent_jobs_total` (six statuses).** Never mentioned here, because this
issue was framed around the two agent-worker counters. But it is the *denominator*
of `MctlAgentJobCostHigh`, and a lazily created denominator makes the first
finished job after a server restart read as zero finished jobs — the guarded ratio
becomes `+Inf` and the rule can fire on ordinary spend. Raised as a P2 by the Codex
reviewer; fixed in commit `d4b47ea`.

**`mctl_agent_policy_denials_total` (108 combinations).** The exclusion argued
that `MctlAgentPolicyDenialRateHigh`'s `> 4` floor means one first denial cannot
fire the rule anyway. True, and it answers a different question: if the first
*five* denials for one reason land between two scrapes, the series is first
observed at `5`, every later sample reads `5`, `increase()` over the window is `0`,
and the rule misses its own documented "at least 5 denials" case — in exactly the
burst scenario ("worker hammering a paused account") it exists for. Raised as a P2
by the Codex reviewer; fixed in commit `f6db8cf`. 108 zero series is a cheap price
for the floor meaning what it says.

The "byte-identical alert expressions" criterion held throughout: `git diff --stat
deploy/` on the implementing branch is empty. The separate change to
`MctlAgentJobCostHigh`'s denominator and thresholds is
mctlhq/mctl-telegram#596, and is not part of this proposal.
