# Alert on scheduled dispatch failures and silent misses

## Context
mctl-agents (1.65.0, mctl-agents#559/#560) now dispatches weekly GitHub
workflows from a Temporal schedule. The first target is portfolio's
`weekly-refresh.yml` on Sundays at 10:01 UTC. The run executes
`ScheduledDispatchWorkflow` on the control queue `mctl-dev-loop`. A dispatch
that fails today leaves two signals. The first is a `scheduled-dispatch-failed`
issue in the target repo, which needs a working GitHub App token. The second,
added by mctl-agents#561 (proposal implemented, PR mctl-agents#566), is a worker
log line plus a counter `scheduled_dispatch_alert_undelivered{repo,workflow_file}`
for the case where that issue cannot be filed. No rule in
`platform-gitops/infra-components/observability/vm-rules/` alerts on either
signal. Nothing detects a schedule that never fired, for example because it was
deleted, paused, or never created after a bad deploy.

This proposal adds one VMRule group with three alerts to
`mctl-agents-worker-alerts.yaml`, promtool unit tests, and an explicit
human (Telegram) route in `bootstrap/templates/observability/monitoring.yaml`.
That closes the gap from the original defect: a weekly job silently did not run
and nobody heard.

## User stories
- AS a platform operator I WANT a Telegram alert when a scheduled dispatch
  failed AND its GitHub alert issue could not be filed SO THAT a failure with no
  other channel still reaches a person.
- AS a platform operator I WANT a Telegram alert when a `ScheduledDispatchWorkflow`
  execution fails SO THAT a backstop exists even when the GitHub issue path works
  but nobody watches the target repo.
- AS a platform operator I WANT a Telegram alert when no `ScheduledDispatchWorkflow`
  completed in about 8 days SO THAT a schedule that was deleted, paused or never
  created is noticed within one weekly period.
- AS a reviewer I WANT each rule proven by promtool tests to fire on a broken
  series and stay quiet on a healthy one SO THAT the alerts are known to work.

## Acceptance criteria (EARS)
- WHEN `scheduled_dispatch_alert_undelivered` (exact exported name confirmed on
  a live worker) increases for any `repo`/`workflow_file`, including the first
  increment that creates the series, THE SYSTEM SHALL fire
  `MctlAgentsScheduledDispatchAlertUndelivered` with the `repo` and
  `workflow_file` labels kept.
- WHEN the SDK workflow-failed counter for `workflow_type="ScheduledDispatchWorkflow"`
  increases, including the first increment that creates the series, THE SYSTEM
  SHALL fire `MctlAgentsScheduledDispatchFailed` with severity `warning`.
- IF the worker's own metrics were observed during the last 8 days AND no
  `ScheduledDispatchWorkflow` completion was observed in that window (no
  increase in any completed-counter series, and no completed-counter series that
  first appeared in the window) THEN THE SYSTEM SHALL fire
  `MctlAgentsScheduledDispatchMissed`.
- WHEN the worker restarts after a successful run, so the completed counter
  comes back as a new series at value 1, THE SYSTEM SHALL count that as a
  completion and SHALL NOT fire `MctlAgentsScheduledDispatchMissed`.
- WHILE the worker's metrics are absent (scrape gap, worker down), THE SYSTEM
  SHALL NOT fire `MctlAgentsScheduledDispatchMissed`. That state is unknown,
  and `MctlAgentsWorkerMetricsMissing` already covers it.
- THE SYSTEM SHALL route every `MctlAgentsScheduledDispatch.*` alert to the
  `telegram` receiver through an explicit alertname matcher in
  `platform-gitops/bootstrap/templates/observability/monitoring.yaml`, and not
  to the root `mctl-agent` receiver.
- THE SYSTEM SHALL include, for each of the three rules, at least one promtool
  test where the rule fires on a broken series and one where it stays quiet on
  a healthy series. These tests run through `scripts/check-vm-rules.sh` in
  `validate-manifests.yml`.
- THE SYSTEM SHALL leave the ADR-008 rules (`mctl-agents.queue-saturation`),
  the admission rules (`mctl-agents.implementation-admission`) and their routing
  unchanged.
- THE SYSTEM SHALL use metric names and labels in the rules that match what a
  live `admins-mctl-agents-worker` serves on `:8080/metrics`, and the PR SHALL
  quote the scraped lines.

## Out of scope
- Changes to mctl-agents code: the counter, workflow and schedule (#559/#560/#561).
- Re-routing the four ADR-008 rules that carry `mctl_agent_self="true"`.
- Alerting on the `scheduled_dispatch_alert_undelivered` log line through Loki.
  The counter is the single source.
- A separate silent-miss rule for each target. There is only one target today
  (see Open questions).
- Checking that the dispatched GitHub workflow itself succeeded in the target repo.

## Open questions
- Exact exported names. The Temporal Core exporter may prefix custom metrics
  with `temporal_`, and it may or may not add a `_total` suffix to counters. The
  issue requires reading the names off a live worker, and this run had no
  cluster access. The design uses the expected names
  `temporal_workflow_completed`, `temporal_workflow_failed` and
  `temporal_scheduled_dispatch_alert_undelivered`. The implementer must confirm
  or correct all three before writing tests.
- Rule 1 depends on mctl-agents#561 (PR #566) being released and deployed to
  `admins-mctl-agents-worker`. Until that happens the series does not exist and
  the rule cannot fire. That is acceptable, but the PR should state the deployed
  version.
- Per-target silent miss. The silent-miss rule aggregates across every
  `ScheduledDispatchWorkflow`, because the SDK completed counter carries
  `workflow_type` and not the target `repo`. With more than one weekly target,
  one healthy target would hide a missing one. This is acceptable for one
  target. A per-target signal needs a new labelled counter in mctl-agents.
- First-deploy window. If the rule ships before the first Sunday run has been
  recorded, the silent-miss arm can fire. It needs both worker metrics present
  for 8 days and no completion seen in that time. The first run was due
  2026-10-04 10:01 UTC, so this is expected to be moot by merge time.
