# Design: issue-591-fix-metrics-lazily-created-agent-counter

## Current state

**Where the counters are defined.** `internal/metrics/metrics.go` holds a single
`Registry` struct and a single constructor, `New()` (line 226), which builds a fresh
`prometheus.Registry`, constructs every collector, and `MustRegister`s them in one
block (lines 390-421). The two counters in question are:

```go
r.AgentJobCostUSDTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
    Name: "mctl_agent_job_cost_usd_total", ...
}, []string{"result"})                                  // metrics.go:373

r.AgentClaudeResultErrorsTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
    Name: "mctl_agent_claude_result_errors_total", ...
}, []string{"class"})                                   // metrics.go:378
```

Their doc comments on the struct fields (lines 142-152) already declare the bound:
"Bound: 2 series (success, error)" and "Bound: 2 series (usage_limit, other)". Neither
bound is expressed as code — the values exist only as string literals at the increment
sites.

**Where they are incremented.** Both live in `internal/agentworker/claudeinvoker.go`:

- `recordCost` (line 234) computes `result := "success"`, flips it to `"error"` when
  `res.IsError`, and calls
  `c.Metrics.AgentJobCostUSDTotal.WithLabelValues(result).Add(cost)` (line 252), guarded
  by `if c.Metrics != nil` because `ClaudeInvoker.Metrics` is documented optional
  (line 81-84).
- `countResultError` (line 262) sets `class := "other"`, flips it to `"usage_limit"`
  when `errors.Is(err, ErrClaudeUsageLimit)` (the sentinel from
  `internal/agentworker/worker.go:208`), and calls
  `c.Metrics.AgentClaudeResultErrorsTotal.WithLabelValues(class).Inc()` (line 270).

`WithLabelValues` is what materializes a child. Until one of these two functions runs,
the `CounterVec` has no children at all, and a vec with no children emits no metric
family from `Gather()`.

**Where the registry is built for the worker.** `cmd/agent-worker/main.go:97` calls
`metrics.New()`, immediately sets the info gauge
`m.AgentCredentialDomain.WithLabelValues(credentialDomainID).Set(1)` (line 98) — an
existing precedent for "initialize a series at startup, before any work" — then wires
`m` into the `ClaudeInvoker` (`Metrics: m`) and into `newHealthServer(...)`
(`cmd/agent-worker/health_server.go:34`), which serves `promhttp.HandlerFor(m.Prometheus, ...)`
on `/metrics` behind an optional `AGENT_METRICS_ALLOW_CIDR` guard. `cmd/server/main.go:114`
calls the same `metrics.New()`. `docs/agent-worker.md` (the "Metrics: `/metrics` on
`AGENT_HEALTH_ADDR`" section) records the reason the worker shares the constructor
rather than owning a bespoke registry: "so every `mctl_*` name stays defined in exactly
one file", and already notes that "vec families with no children simply don't appear".

**The alerts that depend on this.** `deploy/alerts/mctl-telegram.rules.yaml` is a
mirror-only copy (see its comment at line 199-205; the deployed copy lives in
mctl-gitops). `MctlAgentClaudeUsageLimit` (line 251) is
`sum(increase(mctl_agent_claude_result_errors_total{class="usage_limit"}[15m])) > 0`
with `for: 0m`. `MctlAgentJobCostHigh` (line 388) is a ratio over
`increase(mctl_agent_job_cost_usd_total[1h])` `and` an absolute
`sum(increase(mctl_agent_job_cost_usd_total[1h])) > 0.50` floor. Both read `0` for a
series whose first-ever sample is already non-zero.

**Why the existing tests miss it.** Every `input_series` in
`deploy/alerts/mctl-telegram.rules_test.yaml` starts at zero (`values: '0+1x20'`,
lines 60, 80, 166, 187) — the synthetic zero the real process never emits.
`internal/metrics/metrics_test.go` explicitly works around lazy creation instead of
asserting against it: `TestNew_RegistersAllMetrics` calls `.Add(0)` on each vec child
by hand (lines 64-67) with the comment "Prometheus lazy-registers some vec children
until first use". The Go tests in `internal/agentworker/claudeinvoker_test.go` read
`before`/`after` with `testutil.ToFloat64` (lines 305-355), so they pass whether or not
a zero baseline exists.

## Proposed solution

Give the four children a zero baseline inside `metrics.New()`, and make the closed
label sets explicit in code so the baseline and the increment sites cannot drift apart.

**1. Exported label-value constants and their closed sets** (`internal/metrics/metrics.go`).
Add a `const` block plus two package-level slices, directly modeled on the existing
`PolicySurface*` const block (lines 165-179) that already establishes this convention
for the denial counter:

```go
// Closed label-value set for AgentClaudeResultErrorsTotal's `class`.
const (
    ClaudeResultClassUsageLimit = "usage_limit"
    ClaudeResultClassOther      = "other"
)

// Closed label-value set for AgentJobCostUSDTotal's `result`.
const (
    JobCostResultSuccess = "success"
    JobCostResultError   = "error"
)

// claudeResultClasses / jobCostResults enumerate those sets so New() can give
// every child a zero baseline. Adding a value here is the only supported way to
// add one at an increment site.
var claudeResultClasses = []string{ClaudeResultClassUsageLimit, ClaudeResultClassOther}
var jobCostResults      = []string{JobCostResultSuccess, JobCostResultError}
```

**2. Pre-initialization in `New()`**, immediately after the `MustRegister` block and
before `return r`:

```go
// Pre-create the children of the two agent-worker counters so each has a real
// zero baseline before any job is claimed. A counter whose first observed
// sample is already non-zero makes increase() read 0 over that sample, which
// would let MctlAgentClaudeUsageLimit and MctlAgentJobCostHigh miss the first —
// and, given Worker.Loop's sequential processing, possibly only — occurrence
// they exist for (issue #591). Four series total; both label sets are closed.
// AgentPolicyDenialsTotal is deliberately excluded: 18 x 6 = 108 series, most of
// which cannot occur, and its rule has a > 4 floor.
for _, class := range claudeResultClasses {
    r.AgentClaudeResultErrorsTotal.WithLabelValues(class).Add(0)
}
for _, result := range jobCostResults {
    r.AgentJobCostUSDTotal.WithLabelValues(result).Add(0)
}
```

`Add(0)` (not `Inc()`) materializes the child at zero. This is the idiom the repo's own
test already uses at `metrics_test.go:45-67`; the change moves it from the test into
production code, which is where the issue says it belongs.

**3. Use the constants at the increment sites** (`internal/agentworker/claudeinvoker.go`).
`recordCost` becomes `result := metrics.JobCostResultSuccess` / `metrics.JobCostResultError`,
and `countResultError` becomes `class := metrics.ClaudeResultClassOther` /
`metrics.ClaudeResultClassUsageLimit`. The package already imports
`github.com/mctlhq/mctl-telegram/internal/metrics` for the `Metrics *metrics.Registry`
field, so no new dependency edge and no import cycle (`internal/metrics` imports nothing
from `internal/agentworker`). Behavior is byte-identical; the point is that a future
third class value must be added to `claudeResultClasses` to have a constant to use.

**4. Tests** (`internal/metrics/metrics_test.go`, `internal/agentworker/claudeinvoker_test.go`).
A new `TestNew_AgentCounterZeroBaseline` gathers from `New().Prometheus.Gather()`,
finds the two metric families, and asserts each contains exactly the expected label
pairs with `GetCounter().GetValue() == 0` — inspecting `dto.MetricFamily` label/value
structure, per the DoD's "rather than asserting on a string dump". The same test asserts
`mctl_agent_policy_denials_total` is absent from the gathered output on a fresh
registry, locking in the scope decision. A second test in `internal/agentworker`
asserts the end-to-end shape: a fresh `metrics.New()` reads `0` for
`{class="usage_limit"}`, and after one usage-limit `countResultError` it reads `1` —
i.e. a genuine 0 -> 1 delta a Prometheus `increase()` can see.

**5. Doc touch-up** (`docs/agent-worker.md`). The metrics section currently tells the
reader that vec families with no children simply don't appear; add one sentence noting
the four agent counters are the deliberate exception, pre-created at zero so
first-occurrence alerts work. `docs/runbook.md` needs no expression changes, but the
`MctlAgentClaudeUsageLimit` section's manual queries (lines 408-415) now return a `0`
sample instead of "no data" on an idle worker, which is worth one clarifying clause.

Why this shape: it is the smallest change that makes the guarantee unconditional. The
alert expressions stay simple (the issue's stated goal), the fix lives on the emitting
side in exactly one file, and there is no startup call an entrypoint can forget.

## Alternatives

**A. A worker-only initializer called from `cmd/agent-worker/main.go`** — e.g.
`m.InitAgentWorkerCounters()` next to the existing `AgentCredentialDomain` set at line 98.
Closest to the issue's literal wording ("when the worker's registry is built") and keeps
`cmd/server`'s exposition free of four agent series. Dropped because the guarantee then
depends on a call site: any future entrypoint or test harness that builds a registry and
runs a `ClaudeInvoker` (the pattern in `claudeinvoker_test.go:305`, `:332`, `:445`)
silently loses the baseline, which is precisely the failure mode being fixed. The cost of
the chosen approach is four constant-zero series on `cmd/server`, which contribute exactly
`0` to `sum(increase(...))` in both affected rules and to every documented runbook query.

**B. Fix it in PromQL** — `X > 0 unless X offset 15m` to detect a newly appearing positive
series. Explicitly rejected in the issue and re-confirmed here: a worker restart resets the
series and re-fires it, the expression must be duplicated in both the mirror
(`deploy/alerts/`) and the deployed mctl-gitops copy, and it is materially harder to cover
with a promtool case than a Go test over a `dto.MetricFamily`.

**C. Register the two counters as `prometheus.Collector`s with a custom `Describe`/`Collect`
that always emits all children** — a hand-rolled wrapper guaranteeing the full label
cross-product regardless of use. Dropped as heavy machinery for four series, and it would
diverge from how the other 25+ collectors in `New()` are built, which is the codebase's
strongest convention here.

**D. Extend it to `AgentPolicyDenialsTotal` too, for symmetry** — dropped for the reason
the issue gives: 108 series, most representing reason/surface pairs that cannot occur
(the `PolicySurface*` set is consumed by distinct call sites that can only produce a
subset of `policy.DenyCode`s), and `MctlAgentPolicyDenialRateHigh`'s `> 4` floor means a
first denial cannot fire it anyway.

## Platform impact

- **Migrations:** none. No schema, no config, no environment variable.
- **Backward compatibility:** no metric name, type, help string, or label name changes,
  so dashboards and the deployed VictoriaMetrics rules are unaffected. The only observable
  difference is that four series now exist at `0` from process start instead of appearing
  on first use. `increase()`, `rate()`, and `sum()` over them are unchanged for any window
  that already contained data.
- **Cardinality / resource impact:** +4 series per `cmd/agent-worker` replica and +4 per
  `cmd/server` replica. Negligible against the existing families; no allocation on the hot
  path (children are created once at startup and `WithLabelValues` then hits the vec's
  existing-child fast path).
- **Risk: existing tests that assume absence.** `internal/metrics/metrics_test.go`'s
  `TestNew_RegistersAllMetrics` and `TestNew_RegistersIssue580Metrics` prime children with
  `.Add(0)` / `.Inc()`; those lines become redundant for the two affected vecs but stay
  correct. Any test asserting an exact series count or a full exposition dump over these
  families would now see two children where it saw one. Mitigation: run
  `go test ./...` and grep for `CollectAndCompare` / `GatherAndCount` over the two names
  before merging (`TestReplicaIDGauge` at `metrics_test.go:165` is the only
  `CollectAndCompare` in the file and it targets `TelegramReplicaID`).
- **Risk: a reviewer reads the extra `cmd/server` series as a bug.** Mitigated by the
  code comment in `New()` and the `docs/agent-worker.md` sentence, both of which name
  issue #591 and state the tradeoff.
- **Risk: alert behavior change.** `MctlAgentJobCostHigh`'s ratio denominator
  (`mctl_agent_jobs_total{status="completed"}`) is untouched and still `or vector(0)`-guarded,
  so a zero numerator baseline cannot introduce a divide-by-zero fire. `MctlAgentClaudeUsageLimit`
  is `> 0` on a sum of increases; a permanently-zero series adds nothing. Net effect is
  strictly more detection, no new false-positive path.
- **Operational note:** the fix takes effect on the next agent-worker rollout; it does not
  retroactively repair a series already created above zero. An operator wanting the baseline
  immediately can restart the worker pod, which is safe (`Worker.Loop` claim fencing is
  attempt-based; see `verifyJobCompleted` in `claudeinvoker.go:209-217`).


## Amendment — 2026-09-09, after implementation review

This design's scope (two counters, four series, `mctl_agent_jobs_total` explicitly
left untouched and `or vector(0)`-guarded) was widened during review of
mctlhq/mctl-telegram#593 to four families and 118 series. The reasoning is recorded
in `requirements.md` under "Scope expanded during implementation"; read that section
before treating any scope statement above as current.

What did **not** change: no alert expression was touched by that PR, in the mirror
or in `mctl-gitops`, and the `or vector(0)` guard on `MctlAgentJobCostHigh` stays —
a zero baseline only helps once it has actually been scraped, so the guard still
covers older images, a scrape gap, and a total loss of the emitting target.
