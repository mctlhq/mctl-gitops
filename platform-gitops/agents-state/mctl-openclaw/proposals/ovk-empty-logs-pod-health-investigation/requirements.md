# Investigate ovk's second consecutive week of empty logs and low pod utilization

## Context
`ovk` (the high-SLA production tenant) has now shown 0 log lines in the 6h
window for a second straight week, with only 1/5 pods in use and ~17%
memory utilization — the same low-utilization snapshot as last week — while
`mctl_list_incidents` reports 0 active incidents for `ovk`. This is a gap
between signal and alerting worth closing: per `context/architecture.md`,
"restarts are painful" for `ovk` and we must not propose restarts without
clear justification, so this proposal is diagnostic/investigative only.

**Note on overlap:** a related proposal, `ovk-s3-sync-canary-and-pod-health-investigation`,
already exists and covers substantially the same underlying question (silent
canary / possible pod-down state in `ovk`), based on an earlier pass's
1h-window s3-sync/ArgoCD-drift signals. Today's finding is best read as a
second data point confirming the same unresolved anomaly persists into a
second week, not a new independent issue. Execution should check that
sibling proposal's status first; if it already produced a finding, this
proposal's job is to confirm whether that finding still holds two weeks
later, not to re-run the whole investigation from scratch.

## User stories
- AS an on-call operator I WANT to know whether the `ovk` openclaw pod is
  actually degraded/quiet or genuinely at risk SO THAT I can decide whether
  customer-facing channels are at risk.
- AS the service owner I WANT to confirm whether the detection gap identified
  in the sibling investigation is still open after a second week of the same
  signal SO THAT it gets escalated if still unresolved.
- AS the on-call operator I WANT a documented, read-only investigation
  outcome SO THAT this class of signal can be triaged quickly without
  guessing.

## Acceptance criteria (EARS)
- WHEN this investigation starts THE SYSTEM SHALL first check the status and
  findings of the sibling proposal `ovk-s3-sync-canary-and-pod-health-investigation`
  and SHALL reuse its findings rather than re-investigating from scratch if
  they are still current.
- WHEN pod status is checked THE SYSTEM SHALL confirm the actual
  running/ready/restart-count state for `ovk`/openclaw via
  Kubernetes/ArgoCD state, independent of the mctl log/metrics signals
  already gathered.
- WHEN the s3-sync canary is checked THE SYSTEM SHALL inspect its CronWorkflow
  execution history for `ovk` to determine whether it ran and produced no
  output, versus not running at all.
- IF the pod is confirmed down, degraded, or the restore-state probe is
  failing THEN THE SYSTEM SHALL document the finding and escalate as a new
  incident, without independently restarting or otherwise mutating the `ovk`
  deployment as part of this investigation.
- IF the pod and canary are confirmed healthy and the empty logs / low
  utilization are explained by benign causes (e.g. traffic drop,
  log-retention window) THEN THE SYSTEM SHALL record the explanation and
  close both this and the sibling investigation with no further action.
- WHILE the investigation is in progress THE SYSTEM SHALL treat all actions
  as read-only (log/metric/manifest inspection only) and SHALL NOT modify
  the s3-sync canary schedule, the restore-state probe timeout, or any `ovk`
  resource beyond diagnostic inspection.
- WHEN the investigation concludes THE SYSTEM SHALL produce a written
  finding (root cause, evidence, whether alerting should have fired, and
  whether the signal has now persisted long enough to warrant a dedicated
  alerting-gap fix proposal).

## Out of scope
- Any code or config change to the s3-sync canary, restore-state probe, or
  `ovk` deployment itself — diagnostic only.
- Restarting the `ovk` pod.
- The upstream/GHSA upgrade assessment (tracked separately in
  `openclaw-upstream-upgrade-assessment` and `ghsa-batch-2026-09-11-upgrade-assessment`).
- The `labs` memory quota trend (tracked separately in
  `labs-memory-quota-trend-review`).
- `labs`'s own empty-logs signal (present for a third consecutive week but
  explicitly deprioritized by the analyst in favor of `ovk`'s higher-SLA
  status).
