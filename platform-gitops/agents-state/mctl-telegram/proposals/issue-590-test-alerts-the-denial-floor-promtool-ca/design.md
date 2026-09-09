# Design: issue-590-test-alerts-the-denial-floor-promtool-ca

## Current state

Three files matter, all read in the clone.

**`deploy/alerts/mctl-telegram.rules.yaml`** is a non-deployed mirror. Its
header (lines 1-44) states that nothing applies the file, that the live rules
are in mctl-gitops under
`platform-gitops/infra-components/observability/vm-rules/`, and that the file is
kept only so `deploy/alerts/runbook_links_test.go` can validate every
`runbook_url` anchor against `docs/runbook.md`. `MctlAgentPolicyDenialRateHigh`
lives in the `mctl-telegram-agent` group (lines 318-339):

```
(
  sum by (reason) (rate(mctl_agent_policy_denials_total[30m]))
  /
  scalar(sum(rate(mctl_agent_jobs_total{status="processing"}[30m])) or vector(0))
) > 0.20
and
sum by (reason) (increase(mctl_agent_policy_denials_total[30m])) > 4
```

with `for: 0m`. The rule comment (lines 269-317) explains each part: grouping by
`reason`, the `mctl_agent_jobs_total{status="processing"}` denominator proxy
(incremented in `Queue.Claim`, `internal/agent/queue/queue.go`), the provisional
`0.20` threshold, the `or vector(0)` guard, and the floor — "`> 4` rather than
`>= 5`: increase() extrapolates to a float".

**`deploy/alerts/mctl-telegram.rules_test.yaml`** holds ten promtool cases. The
one at issue, lines 124-137, is commented "T4b: stays silent. A single denial in
a near-idle window ... Kills a dropped floor clause — without it, this exact
input would fire." Its two series each step `0 -> 1` at `t=1m` and then hold
flat through `t=30m`.

**`.github/workflows/build.yml`** runs the suite in the `promtool-check` job
(lines 171-191): it pins `PROM_VERSION=2.52.0`, extracts `.spec` from the
PrometheusRule CRD with `yq` into `/tmp/rules.yaml` (which is why the test file's
`rule_files:` entry is the absolute path `/tmp/rules.yaml`), runs
`promtool check rules`, then `promtool test rules`.

### What was measured, not assumed

Both promtool versions were downloaded into `/tmp` and run against a `.spec`
extraction of the mirror rules, unmodified and with the floor mutated from
`> 4` to `> -1`:

| toolchain | existing case + mutated floor | proposed case + intact rule | proposed case + mutated floor |
|---|---|---|---|
| promtool 2.52.0 (the CI pin) | **FAILED** (mutation caught) | SUCCESS | **FAILED** (mutation caught) |
| promtool 3.5.0 | SUCCESS (mutation survives) | SUCCESS | **FAILED** (mutation caught) |

With the rule intact, the full existing suite is green under both versions.
With the floor mutated to `> -1`, the existing suite fails under 2.52.0 (the
existing case catches it) and passes entirely under 3.5.0 (no case catches it).

The cause is a Prometheus behaviour change, not a mistake unique to this file.
Prometheus 2.x range selectors are closed on both ends, so `[30m]` at
`eval_time: 30m` includes the `t=0` sample; the flat series then has a real
`0 -> 1` delta, the share is `1/1 = 100%`, the extrapolated denial count is
about 1.03, the floor suppresses the alert, and relaxing the floor makes it
fire. Prometheus 3.0 made range selectors left-open; `t=0` drops out, both
series read as the constant `1`, both rates are `0`, `0/0 = NaN`, `NaN > 0.20`
is false, and the case is silent for arithmetic reasons no matter what the
floor says. The issue's analysis is therefore correct for Prometheus 3.x — and
for the mctl-gitops environment where it was observed — and premature for this
repository's pinned CI. The important consequence is the same either way: the
case's mutation-killing power is an accident of the pinned version, and a
routine toolchain bump silently removes it.

## Proposed solution

Replace the two input series of the denial-floor case in
`deploy/alerts/mctl-telegram.rules_test.yaml` with series that keep rising
inside the evaluation window, and rewrite the case comment. Nothing else
changes — no rule expression, no other case, no workflow, no Go code, no docs.

New series, byte-identical to the mctl-gitops#1110 case
`denials below the absolute floor stay silent despite a high share`:

```yaml
      - series: 'mctl_agent_jobs_total{status="processing"}'
        values: '0 0 1 1 2 2 3 3 4 4 5 5 6 6 6 6 6 6 6 6 6 6 6 6 6 6 6 6 6 6 6'
      - series: 'mctl_agent_policy_denials_total{reason="unknown"}'
        values: '0 0 0 0 0 1 1 1 1 1 2 2 2 2 2 3 3 3 3 3 3 3 3 3 3 3 3 3 3 3 3'
```

Why this works on both range semantics: the rise happens between `t=1m` and
`t=15m`, strictly inside the window under either edge convention. Six claims
against three denials gives a share of exactly `0.50` (well above `0.20`) on
both versions. The extrapolated denial count is `3.0` under Prometheus 2.x (the
range covers the full 30m, no extrapolation) and about `3.10` under Prometheus
3.x (29m of samples extrapolated to a 30m range), both comfortably below the
`> 4` floor and comfortably above `-1`. So the first clause is true, the floor
clause is the only thing holding the alert down, and removing the floor fires
the alert — which is precisely the mutation-killing property the comment
claims. Both counters also stay flat for the last 15m, which keeps the case
readable as "a burst that has since stopped" rather than a knife-edge input.

The comment is rewritten to say four things: which clause suppresses the alert,
the concrete share and count the input produces, that a flat-after-one-step
series is the trap to avoid because a range selector's left edge is closed in
Prometheus 2.x and open from 3.0 onward (making both rates `0` and the share
`NaN`), and that the inputs are kept identical to the mctl-gitops case for
mirror fidelity. It stops asserting a property the old input only accidentally
had.

The header of `mctl-telegram.rules_test.yaml` (lines 6-9) still speaks only of
"these two cases", written when the file had two. Fixing that sentence to refer
to the pairing principle generally is a one-line, zero-risk clarity improvement
and is included as an optional task.

## Alternatives

**Keep the flat series and pin the toolchain forever.** Under promtool 2.52.0
the existing case does catch the mutation, so a comment saying "do not bump
`PROM_VERSION`" would technically preserve the coverage. Dropped: it converts a
test into a version trap, contradicts the mirror-fidelity requirement with
mctl-gitops#1110, and leaves the deployed suite's environment (Prometheus 3.x
semantics) uncovered. It also makes the correctness of a test depend on a line
in a CI workflow file three directories away.

**Change the eval time or the interval instead of the values.** Evaluating at
`31m`, or using `interval: 2m`, would pull the `0 -> 1` step strictly inside the
window under either convention and is a smaller diff. Dropped: the share stays
`1/1 = 100%` and the extrapolated count stays near `1`, so the case remains a
degenerate one-denial input that reads as a corner case rather than a
believable near-idle window; and it would diverge from mctl-gitops#1110, which
the issue explicitly asks us to mirror.

**Add a `promql_expr_test` asserting the floor sub-expression's value
directly.** Asserting that `sum by (reason) (increase(...[30m]))` equals about
`3.1` would pin the arithmetic with no ambiguity. Dropped as the primary fix:
it tests the sub-expression, not the alert, so it would still pass if the `and`
clause were deleted from the rule. It is worth keeping as an optional
belt-and-braces addition, listed in tasks, but it does not replace an
`alert_rule_test` that asserts silence.

**Bump `PROM_VERSION` in `.github/workflows/build.yml` as part of this change.**
Measured: the full suite is green under 3.5.0 with the rule intact, so a bump
would not break anything today. Dropped from scope: #590 declares rule and
workflow changes out of scope, a toolchain bump deserves its own PR and its own
review of every case's behaviour under the new range semantics, and the series
fix is version-robust with or without it. Recorded as an open question and a
follow-up.

## Platform impact

- **Migrations:** none. No schema, no data, no config.
- **Deployment:** none. `deploy/alerts/mctl-telegram.rules.yaml` is a
  non-deployed mirror per its own header; the test file is CI-only. Nothing
  ArgoCD reconciles is touched. No alert behaviour in the cluster changes.
- **Backward compatibility:** unaffected. No Go code, no public surface, no
  metric names, no runbook anchors. `deploy/alerts/runbook_links_test.go` and
  `docs/runbook_test.go` read `*.rules.yaml` and `docs/runbook.md`, neither of
  which changes, so `go test ./deploy/alerts/... ./docs/...` is unaffected.
- **Resource impact:** none. The suite gains no cases; one case's 62 sample
  values change.
- **Risk: the replacement is itself vacuous.** Mitigated by making the mutation
  run a required, stated step of the PR — run `> 4` to `> -1` and paste the
  promtool output — rather than a claim in a comment. It has already been run
  on both 2.52.0 and 3.5.0 during investigation and fails on both.
- **Risk: the mirror drifts from mctl-gitops#1110.** Mitigated by copying the
  series verbatim and naming the gitops case in the comment, so a future
  three-way diff is mechanical.
- **Risk: a future editor reintroduces a flat series.** Mitigated by the
  rewritten comment recording the trap and the range-selector edge-semantics
  change, which is the part of the issue's "definition of done" that outlives
  this specific case.
- **Risk: the PR body repeats the issue's unconditional "it passes with the
  floor removed" claim, which is false on the pinned CI toolchain.** Mitigated
  by stating both measurements explicitly in the PR body; a reviewer who runs
  the mutation on 2.52.0 and sees a failure must not conclude the fix is
  pointless.
