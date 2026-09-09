# Quota, policy-denial and job-cost alerts for the communication agent (mirror rules + runbook)

## Context

Issue #583 registered four communication-agent metrics
(`mctl_agent_policy_denials_total`, `mctl_agent_job_cost_usd_total`,
`mctl_agent_claude_result_errors_total`, `mctl_agent_credential_domain` in
`internal/metrics/metrics.go`) but no alert consumes them. Issue #587 asks for
three alerts on top of them: quota exhaustion of the worker's dedicated Claude
credential, an abnormal policy-denial *share*, and cost per job above a
threshold. Today the `mctl-telegram-agent` group in
`deploy/alerts/mctl-telegram.rules.yaml` holds exactly two rules
(`MctlAgentDeadLetter`, `MctlAgentActionsExecutingStuck`), both pointing at the
single `#communication-agent-operations` runbook anchor.

The work is deliberately confined to *this* repository. The file
`deploy/alerts/mctl-telegram.rules.yaml` states in its own header that nothing
applies it — the live rules are in `mctlhq/mctl-gitops` under
`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-ops.yaml`
— and it is kept only because `deploy/alerts/runbook_links_test.go` reads the
`runbook_url` of every alert in it and fails when the `<a id="..."></a>` anchor
does not exist in `docs/runbook.md`. Three alerts once shipped with dangling
anchors and nothing caught it. So the value delivered here is: reviewed
expressions with justified thresholds, runbook sections that actually exist,
and promtool unit tests that prove each expression can both fire and stay
silent. The operator applies the matching gitops change separately.

## User stories

- AS the on-call operator I WANT an alert when the agent-worker's dedicated
  Claude credential hits its own usage limit SO THAT I can tell a quota stop
  from a generic job failure — the exact distinction the C1 report
  (`docs/reports/communication-agent-c1.md`) could not make.
- AS the on-call operator I WANT an alert on the *share* of agent actions that
  policy denies, broken out by denial reason SO THAT a guarded account's
  ordinary denials stay quiet while a new or runaway denial reason pages me.
- AS the operator funding the agent I WANT an alert when spend per completed
  job crosses a threshold SO THAT a retry storm or a looping model shows up as
  money, not just as logs, given that `AGENT_MAX_BUDGET_USD`
  (`internal/agentworker/claudeinvoker.go`, applied only when `> 0`) caps one
  job in the CLI and aggregates nothing.
- AS an on-call engineer following a firing alert's `runbook_url` I WANT to
  land on a section written for that alert SO THAT the link is worth
  following.
- AS a reviewer of a future expression change I WANT a firing case and a
  must-stay-silent case per alert SO THAT a permanently-quiet expression
  cannot pass CI, as the old `changes(mctl_bridge_active_daemons[10m]) > 20`
  did.

## Acceptance criteria (EARS)

- WHEN `mctl_agent_claude_result_errors_total{class="usage_limit"}` increases
  over the alert's evaluation window THE SYSTEM SHALL raise
  `MctlAgentClaudeUsageLimit` in the `mctl-telegram-agent` group of
  `deploy/alerts/mctl-telegram.rules.yaml`.
- WHILE only `mctl_agent_claude_result_errors_total{class="other"}` is
  increasing THE SYSTEM SHALL keep `MctlAgentClaudeUsageLimit` silent, so the
  `class` selector is proven to be load-bearing rather than the family merely
  being empty.
- WHEN the denials attributed to a single `reason` label exceed the configured
  share of claimed agent jobs AND the absolute denial count in the window
  clears the minimum-volume floor THE SYSTEM SHALL raise
  `MctlAgentPolicyDenialRateHigh` carrying that `reason` label.
- WHILE a guarded account denies a small, steady share of replies (the normal
  operating condition described in the "Communication Agent operations"
  runbook section) THE SYSTEM SHALL keep `MctlAgentPolicyDenialRateHigh`
  silent.
- IF a single denial arrives in a window with almost no agent traffic THEN THE
  SYSTEM SHALL keep `MctlAgentPolicyDenialRateHigh` silent, because a share
  computed from a one-job denominator is not evidence.
- WHEN `sum(increase(mctl_agent_job_cost_usd_total[1h]))` divided by the
  chosen job denominator exceeds the threshold AND total spend in the window
  clears the minimum-spend floor THE SYSTEM SHALL raise
  `MctlAgentJobCostHigh`.
- WHILE spend per job stays at or below the threshold THE SYSTEM SHALL keep
  `MctlAgentJobCostHigh` silent.
- WHERE a rule divides one metric by another THE SYSTEM SHALL aggregate both
  sides with `sum(...)` so that no instance/pod label survives, because
  `mctl_agent_job_cost_usd_total` is emitted by the agent-worker process
  (`cmd/agent-worker/main.go`) while `mctl_agent_jobs_total` is emitted by the
  server process (`internal/agent/queue/queue.go`) and a label-matched
  division could never produce a sample.
- WHILE any rule names a metric THE SYSTEM SHALL use only names registered in
  `internal/metrics/metrics.go`, and in particular SHALL use
  `mctl_agent_jobs_total{status="completed"}` — `db.JobCompleted` in
  `internal/db/agent_jobs.go` — never the `status="succeeded"` spelling used
  in the issue text, which matches no series that the code can ever emit.
- WHEN each new alert is added THE SYSTEM SHALL carry a `runbook_url` whose
  fragment has a matching explicit `<a id="..."></a>` in `docs/runbook.md`, so
  that `go test ./deploy/alerts/...` passes.
- WHEN each threshold is written THE SYSTEM SHALL carry a comment above the
  rule deriving that number from something observable in the repository, and
  IF no such observation exists THEN THE SYSTEM SHALL say so in the comment
  and take the conservative (less noisy) side rather than state an invented
  figure.
- WHEN the promtool suite runs
  (`promtool test rules deploy/alerts/mctl-telegram.rules_test.yaml`, driven by
  the `promtool-check` job in `.github/workflows/build.yml`) THE SYSTEM SHALL
  contain, for each of the three new alerts, one case that fires and one case
  that must stay silent.
- WHILE writing expected annotations in the promtool file THE SYSTEM SHALL
  reproduce the trailing newline a `>` folded scalar leaves in `description`,
  as the existing `MctlBridgeDaemonsFlapping` case documents.
- IF a `mctl_*` name is added to `docs/runbook.md` THEN THE SYSTEM SHALL keep
  `TestRunbookMetricNamesRegistered` (`docs/runbook_test.go`) green without
  editing `internal/metrics/metrics.go`.
- WHILE describing this change anywhere in the PR, commits, rules comments or
  runbook prose THE SYSTEM SHALL NOT claim the rules take effect in the
  cluster, and SHALL state that the deployed copy lives in `mctl-gitops`.

## Out of scope

- The `mctl-gitops` copy of the rules
  (`platform-gitops/infra-components/observability/vm-rules/mctl-telegram-ops.yaml`)
  and the `vm-rules/tests/` cases beside it. The operator applies those; no PR
  is opened against `mctl-gitops` from this work.
- Scrape configuration for the agent-worker `/metrics` endpoint
  (`AGENT_HEALTH_ADDR`, `AGENT_METRICS_ALLOW_CIDR`).
- Dashboards, including `deploy/grafana/mctl-telegram-beta.json`.
- Any change to `internal/metrics/metrics.go` or to the emitting code paths in
  `internal/agentworker/`, `internal/agentapi/`, `internal/agent/executor/`.
- Recording rules and SLO definitions in `docs/slo.md`.
- Using `mctl_agent_credential_domain` as an alerting join. It is listed in the
  issue's metric table but no alert here needs it; see Open questions.

## Open questions

- **No measured cost-per-job baseline exists in this repository.** Grep for
  `total_cost_usd`/`cost_usd` finds only the plumbing
  (`internal/agentworker/claudeinvoker.go`, `docs/agent-worker.md`), never an
  observed figure, and `AGENT_MAX_BUDGET_USD` is set in gitops, not here. The
  threshold is therefore taken on the conservative (high) side and the rule
  comment says plainly that it is unmeasured and must be re-derived from the
  first week of real data. Proceeding rather than blocking.
- **No baseline denial share either.** The agent runs guarded (observe mode,
  worker replicas usually 0 between test windows, per the runbook's
  containment controls), so the "normal" share is not observable yet. Same
  treatment: conservative threshold plus a minimum-volume floor, stated in the
  comment.
- **Denominator for the denial share.** No metric counts *allowed* policy
  evaluations — `CountPolicyDenial` is only called on `policy.Deny`
  (`internal/agentapi/actions.go`, `internal/agent/executor/executor.go`), so a
  true denial *rate* is not computable. `mctl_agent_jobs_total{status="processing"}`
  (incremented once per claim in `Queue.Claim`) is the closest available
  normalizer for "opportunities to be denied" and is emitted by the same
  process. The design records this as an approximation, not an exact base
  rate.
- **Whether the ratio may legitimately exceed 1.** It may: `actions.go`
  deliberately counts denials from each evaluation, including redeliveries of
  the same job, so a worker hammering a paused account inflates the numerator
  above the claim count. That is the anomaly signal, not a bug; the runbook
  says so.
- **Whether to also list the three new anchors in
  `docs/runbook_test.go`'s `TestRunbookAnchorsPresent` fixed list.** Redundant
  with `runbook_links_test.go`, which derives the same check from the rules.
  Default: do not, to keep the diff minimal. Reviewer may overrule.
