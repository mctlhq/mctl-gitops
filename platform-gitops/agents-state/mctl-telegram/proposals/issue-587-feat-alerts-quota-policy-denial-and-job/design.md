# Design: issue-587-feat-alerts-quota-policy-denial-and-job

## Current state

**The rules file is a mirror, not a deployment.**
`deploy/alerts/mctl-telegram.rules.yaml` opens with `STATUS: NON-DEPLOYED
REFERENCE. Nothing applies this file.` and names the live location:
`mctlhq/mctl-gitops`, `platform-gitops/infra-components/observability/vm-rules/`,
with the communication-agent family in `mctl-telegram-ops.yaml`. The header
states three consequences, one of which governs this change directly: "Adding
an alert here deploys nothing. Add it to mctl-gitops, and add it here too only
if you want the runbook anchor checked."

**Why the mirror is kept.** `deploy/alerts/runbook_links_test.go`
(`TestRunbookURLsResolve`) globs `*.rules.yaml`, extracts every
`runbook_url: "..."` with `runbookURLRe`, and for each in-repo target checks the
fragment against `anchorRe = <a id="([^"]+)"></a>` in the target document. Only
the explicit anchor form counts — a heading rename cannot silently satisfy it.
Three alerts once shipped dangling: `MctlBridgeDaemonsFlapping`,
`MctlTelegramLoginSlow`, `MctlTelegramLoginSendCodeStalls`.

**The group being extended.** `spec.groups[].name: mctl-telegram-agent` holds
two rules today:

- `MctlAgentDeadLetter` — `increase(mctl_agent_dead_letter_total[15m]) > 0`,
  `for: 0m`, `severity: warning`
- `MctlAgentActionsExecutingStuck` — `mctl_agent_actions_executing_stuck > 0`,
  `for: 5m`, `severity: critical`

Both point at `docs/runbook.md#communication-agent-operations`. Every rule in
the file uses `service: mctl-telegram` and a `>` folded `description`.

**The metrics available (all registered in `internal/metrics/metrics.go`,
added by #583).**

| Metric | Emitting process | Notes read in the code |
|---|---|---|
| `mctl_agent_policy_denials_total{reason,surface}` | server (`cmd/server`) | Incremented only on `policy.Deny` at three call sites: `internal/agentapi/actions.go:253` (`propose_reply`), `:565` (owner-facing, split per tool), `internal/agent/executor/executor.go:294,579` (`executor_send`, `executor_recover`). Bounded 18 x 6 = 108 series. |
| `mctl_agent_job_cost_usd_total{result}` | agent-worker (`cmd/agent-worker`) | `ClaudeInvoker.recordCost` runs at `claudeinvoker.go:197`, *before* `countResultError` at `:199`, so a job that fails afterwards still reports its spend. Negative values are dropped rather than panicking `Counter.Add`. |
| `mctl_agent_claude_result_errors_total{class}` | agent-worker | `countResultError` classifies `usage_limit` via `errors.Is(err, ErrClaudeUsageLimit)`; the sentinel is set in `CheckResult` when `isUsageLimitSubtype` matches one of `usageLimitSubtypes` = `usage_limit, rate_limit, quota, credit_balance, insufficient_credits` (`internal/agentworker/worker.go`). |
| `mctl_agent_credential_domain{domain_id}` | agent-worker | Info gauge set once at startup, `cmd/agent-worker/main.go:98`. |
| `mctl_agent_jobs_total{status}` | server | `Queue.count` in `internal/agent/queue/queue.go`. |

**A correction the issue text forces.** The issue's illustrative denominator is
`mctl_agent_jobs_total{status="succeeded"}`. There is no such label value.
`internal/db/agent_jobs.go` defines exactly `pending`, `processing`,
`completed`, `failed`, `dead_letter`, `ignored`, and `Queue.Complete` passes
that status straight through to the counter. A rule written with `succeeded`
selects nothing; with a numerator present it evaluates to `+Inf` and fires
constantly, or evaluates to nothing and is permanently silent — either way, the
class of defect the file's header and test suite exist to prevent. This design
uses `status="completed"`.

**Process split matters for every ratio.** Cost is scraped from agent-worker
pods, jobs from server pods. Their `job`/`instance`/`pod` labels differ, so any
division must `sum()` both sides to strip labels. Denials and jobs are both
server-side, so that ratio is intra-process and safe.

**Worker shape, relevant to thresholds.** `Worker.Loop`
(`internal/agentworker/worker.go`) polls `PollEvents(ctx, 1)` and runs jobs one
at a time — "Sequential (not concurrent) processing is a deliberate
simplification". A usage-limit stop therefore blocks the whole worker, not one
of N parallel slots.

**Tests already in place.** `deploy/alerts/mctl-telegram.rules_test.yaml` has
two cases for `MctlBridgeDaemonsFlapping` and a header stating the standard:
"The point of these two cases is the pair, not either alone." The
`promtool-check` job in `.github/workflows/build.yml` does
`yq '.spec' deploy/alerts/mctl-telegram.rules.yaml > /tmp/rules.yaml`, then
`promtool check rules /tmp/rules.yaml`, then
`promtool test rules deploy/alerts/mctl-telegram.rules_test.yaml` (whose
`rule_files:` points at `/tmp/rules.yaml`). `docs/runbook_test.go` adds
`TestRunbookMetricNamesRegistered`, which regexes `mctl_[a-z_]+` out of
`runbook.md` and fails on any name absent from `internal/metrics/metrics.go`.

## Proposed solution

Three files change: the mirror rules, the runbook, the promtool tests. Nothing
under `internal/` is touched.

### 1. `deploy/alerts/mctl-telegram.rules.yaml` — three rules in `mctl-telegram-agent`

A short comment is added at the top of the group (not a new header section)
recording that these three rules are mirror-only and that the deployed copy is
the operator's separate `mctl-telegram-ops.yaml` change — keeping the file
honest under the header's own "adding an alert here deploys nothing" rule.

**(a) `MctlAgentClaudeUsageLimit`** — severity `warning`, `for: 0m`.

```
sum(increase(mctl_agent_claude_result_errors_total{class="usage_limit"}[15m])) > 0
```

Threshold justification, written into the rule comment: this is not a rate
threshold at all, it is a presence test, and it is grounded rather than
guessed. The worker runs against a dedicated credential domain
(`AGENT_CREDENTIAL_DOMAIN_ID` is *required* by `run()`; the C1 report records
the dedicated OAuth token provisioned specifically so worker spend is isolated
from interactive sessions and `claude-review.yml`). Nothing about normal
operation consumes that pool except the worker, so one usage-limit stop means
the isolated pool is exhausted, and because `Loop` is sequential every
subsequent job hits the same wall until the quota window resets. Any occurrence
is therefore actionable; a nonzero-count threshold would only delay the page.
`> 0` rather than `>= 1` is deliberate and follows the file header's own
recorded lesson about `increase()` extrapolating to a float (an exactly-two
window interpolating to 1.97 and missing `>= 2`). `sum()` collapses replicas so
a two-pod worker Deployment raises one alert, not two.

`15m` matches `MctlAgentDeadLetter` in the same group, so the two
worker-liveness-ish alerts share an evaluation feel.

**(b) `MctlAgentPolicyDenialRateHigh`** — severity `warning`, `for: 0m`
(the 30m window is the smoother, exactly the rationale `MctlToolAvailabilityFastBurn`
already records for its `for: 0m`).

```
(
  sum by (reason) (rate(mctl_agent_policy_denials_total[30m]))
  /
  scalar(sum(rate(mctl_agent_jobs_total{status="processing"}[30m])))
) > 0.20
and
sum by (reason) (increase(mctl_agent_policy_denials_total[30m])) >= 5
```

*Aggregate by `reason`, not `surface`* — the issue asks which and why. `reason`
is the label an operator acts on: `conversation_taken_over` or
`autopilot_paused` denials are the guarded system working as designed, while
`global_kill`, `reply_contains_credentials` or a spike of `unknown` (the
`policy.DenyUnknown` fallback, which by construction means a code path went
unmapped) each imply a different response. Grouping by `reason` puts that word
in the notification and, more importantly, makes each reason clear the
threshold on its own, so a benign steady stream cannot mask a new reason
appearing beside it. `surface` answers "where", which the runbook's diagnostic
query recovers in one PromQL line; it does not change what the operator does
first.

*Denominator.* No metric counts allowed evaluations —`CountPolicyDenial` fires
only on `policy.Deny` — so a true denial rate is not computable from what #583
registered. `mctl_agent_jobs_total{status="processing"}`, incremented once per
claim in `Queue.Claim`, is the closest available proxy for "opportunities to be
denied" and is emitted by the same process as the denials, so the ratio needs
no cross-target label surgery. `scalar()` keeps the `reason` labels on the left
side; `/ on() group_left()` would do the same and is noted as an equivalent.
The ratio can legitimately exceed 1, because `actions.go` counts denials from
*each* evaluation including redeliveries — that inflation is the "worker
hammering a paused account" signal the counter's own comment describes.

*Threshold.* Honest statement in the comment: no production baseline exists.
The agent runs guarded (kill switch, listener flag, autopilot pause, worker
replicas 0 — the four containment controls in the runbook), so no steady-state
denial share has been observed in this repository. `0.20` is chosen on the
conservative side: one denial in five claimed jobs, sustained over half an
hour, for a single reason. The `>= 5` absolute floor exists because a share
computed from a 1-job denominator is arithmetic, not evidence — without it, one
denial during a quiet window reads as 100%.

**(c) `MctlAgentJobCostHigh`** — severity `warning`, `for: 0m`.

```
(
  sum(increase(mctl_agent_job_cost_usd_total[1h]))
  /
  sum(increase(mctl_agent_jobs_total{status="completed"}[1h]))
) > 0.50
and
sum(increase(mctl_agent_job_cost_usd_total[1h])) > 0.50
```

*Denominator, chosen deliberately and explained in the comment as the issue
requires.* The numerator is all spend, both `result="success"` and
`result="error"`, because `recordCost` runs before the `is_error` check. The
denominator is completed jobs (`db.JobCompleted`, the terminal success state
bound to a durable `result_action_id`), so the ratio reads as *dollars per
delivered outcome*. Money burned on failed, retried or dead-lettered jobs
therefore raises the number, which is the intended behaviour: a retry storm
that spends without completing anything is exactly the runaway this alert is
for. Dividing by `status="processing"` (claims) was rejected because it would
*hide* that case — retries increase the denominator and flatten the ratio.
`status="succeeded"` from the issue text is not a real label value; see Current
state.

*Divide-by-zero.* With spend and zero completions the ratio is `+Inf`, which
compares true. That is deliberate and desirable — paying for nothing is worth a
page — but it is guarded by the second clause so a stray fraction of a cent in
an idle hour cannot fire it. The runbook section names the `+Inf` rendering so
an operator seeing it is not confused.

*Threshold.* Stated plainly as unmeasured. No cost figure exists anywhere in
this repository: `grep` for `total_cost_usd`/`cost_usd` finds only
`internal/agentworker/claudeinvoker.go` and `docs/agent-worker.md`, and
`AGENT_MAX_BUDGET_USD` is an operator value set in gitops, unset by default
(`envFloat("AGENT_MAX_BUDGET_USD", 0)`), and applied by the CLI only when
`> 0`. It is a per-job ceiling inside one invocation and aggregates nothing, so
it is not a substitute for this alert and the comment will not call it one.
`$0.50` per completed job is the conservative side: comfortably above a short
tool-driven turn (`jobPrompt()` is one sentence; the model pulls context via
`get_event`/`get_conversation_context` and calls `complete_agent_job` once) and
well below a looping session. The comment records the number as provisional and
tells the next operator to re-derive it from the first week of
`mctl_agent_job_cost_usd_total` and, if `AGENT_MAX_BUDGET_USD` is set, to keep
the threshold below that cap so the alert precedes the CLI's hard stop.

### 2. `docs/runbook.md` — one section per alert

Three new sections in the established shape (`### Symptom`, `### Likely
causes`, `### Diagnostic queries`, `### Mitigation`, `### Escalation`,
`### Postmortem trigger`), each opened by an explicit anchor, plus three
Table-of-contents entries:

- `<a id="mctlagentclaudeusagelimit"></a>`
- `<a id="mctlagentpolicydenialratehigh"></a>`
- `<a id="mctlagentjobcosthigh"></a>`

Anchor form follows the file's convention of the lowercased alert name
(`mctlbridgedaemonsflapping`). They are placed after the
`#communication-agent-operations` section so the agent material stays
contiguous, and the existing "Agent alert response" subsection gains three
one-line entries beside `MctlAgentDeadLetter` and
`MctlAgentActionsExecutingStuck`, cross-linking to the new sections.

Content constraints: every `mctl_*` name written must be registered in
`internal/metrics/metrics.go` or `TestRunbookMetricNamesRegistered` fails; all
five names used (`mctl_agent_claude_result_errors_total`,
`mctl_agent_policy_denials_total`, `mctl_agent_job_cost_usd_total`,
`mctl_agent_jobs_total`, `mctl_agent_credential_domain`) are. Mitigation prose
must not describe any of this as taking effect in the cluster; each section
states that the deployed rule is the `mctl-gitops` copy.

Mitigations, grounded in the containment controls the runbook already
documents: for a usage-limit stop, scale worker replicas to 0 (jobs stay
durable — `Loop` leaves an unfinished claim to the visibility-timeout sweeper)
rather than letting the loop grind against an exhausted pool, and confirm which
pool is affected with `mctl_agent_credential_domain`. For denial-rate, read
`agent_actions.policy_reasons` and decide whether the denial is the system
working (`autopilot_paused`, `conversation_taken_over`) or a defect
(`unknown`, `action_type_unrecognized`). For cost, close the test window with
the four controls before touching credentials.

### 3. `deploy/alerts/mctl-telegram.rules_test.yaml` — six cases

One firing and one must-stay-silent case per alert, matching the file's stated
standard. The silent cases are chosen so each is a real mutation test, not a
tautology:

| Alert | Fires | Stays silent |
|---|---|---|
| `MctlAgentClaudeUsageLimit` | `{class="usage_limit"}` increments across the window | only `{class="other"}` increments — kills a rule that dropped the label selector |
| `MctlAgentPolicyDenialRateHigh` | one `reason` well above the share, count over the floor | a normal low share at real volume, plus a single denial in a near-idle window — kills both a lowered threshold and a dropped floor |
| `MctlAgentJobCostHigh` | spend/completed above threshold | ordinary spend at ordinary completion volume — kills a lowered threshold |

Series are chosen so `increase()`/`rate()` extrapolation lands on exact values
(the existing case's `0+1x20` over `[10m]` yielding exactly `10` is the
precedent), which keeps the `exp_annotations` strings stable. Each expected
`description` reproduces the trailing `\n` that the `>` folded scalar leaves.

## Alternatives

1. **Add the rules to `mctl-gitops` in the same change.** Rejected: explicitly
   a non-goal of the issue, out of this repository, and the operator owns
   `mctl-telegram-ops.yaml`. The header already tells the reader where the
   deployed copy lives; the PR repeats it rather than papering over the split.

2. **Alert on raw denial counts instead of a share.** Rejected for the reason
   the issue gives: a guarded account denying replies is normal, so a count
   threshold is either noisy at low volume or blind at high volume. A share
   with an absolute floor keeps both ends honest.

3. **Aggregate denials by `surface` instead of `reason` (or by both).**
   Dropped. `surface` says which call site consumed the decision, which rarely
   changes the first action; `by (reason, surface)` would spread the same
   denials across up to 108 thin series, each individually below any share
   threshold — the alert would go quiet exactly as volume fragmented. `reason`
   alone keeps the series count at 18 and the label actionable.

4. **Join spend to `mctl_agent_credential_domain` with
   `* on(instance) group_left(domain_id)` so the alert names the exhausted
   pool.** Attractive, dropped for now: it makes the expression depend on
   instance-label agreement between two families on the same target, which is
   fragile to relabelling and awkward to reproduce in promtool input series.
   The runbook's diagnostic query does the join manually instead, which costs
   the operator one paste and costs the alert no reliability.

5. **Divide cost by claimed jobs (`status="processing"`) or by all terminal
   statuses.** Dropped: retries raise the denominator, so the exact failure
   mode worth alerting on — spend without delivered outcomes — would flatten
   toward normal.

6. **A cost *budget* alert (absolute dollars per hour) instead of per job.**
   Dropped as the primary rule because it tracks load as much as waste: a busy
   legitimate hour and a looping model look alike. The per-job ratio isolates
   efficiency. The absolute-spend clause survives as the noise floor, and the
   runbook records the absolute query for operators who want it.

## Platform impact

- **Migrations:** none. No schema, no config, no `internal/` code.
- **Backward compatibility:** additive YAML and Markdown. Existing alerts,
  anchors and the two `MctlBridgeDaemonsFlapping` promtool cases are untouched.
  Nothing in the cluster changes by merging this — the deployed rules are in
  `mctl-gitops`.
- **Resource impact:** none at runtime. CI gains three `promtool` cases with
  1h-window series; evaluation cost is milliseconds. Series cardinality is
  unchanged (no new metrics); the denial rule's `sum by (reason)` produces at
  most 18 series inside the evaluation.
- **Risk: divergence between this mirror and the deployed gitops file.** Real,
  and pre-existing — the header already documents one divergence
  (`MctlTelegramLoginSendCodeStalls`, `>= 2` here vs `> 1` there). Mitigation:
  the group comment names these three as mirror-only pending the operator's
  change, so a future reader is not misled about which side is authoritative.
- **Risk: a threshold that is wrong because it was never measured.** Mitigated
  by taking the conservative side, by the minimum-volume/minimum-spend floors,
  by `severity: warning` (not `page`) on all three, and by rule comments that
  state the number is provisional and name the data that should replace it.
- **Risk: promtool annotation strings drift.** Mitigated by generating the
  expected strings from an actual local `promtool test rules` run rather than
  by hand, and by choosing series that make `increase()` land on exact values.
- **Risk: a new runbook `mctl_*` name breaks `docs` tests.** Mitigated by
  restricting the prose to the five registered names; `go test ./docs/...` is
  in the definition of done.
