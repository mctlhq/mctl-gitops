# Tasks: issue-1593-alert-on-scheduled-dispatch-failures-and

- [ ] 1. Read the live metric names. Port-forward `admins-mctl-agents-worker:8080`
  and grep `/metrics` for `workflow_completed`, `workflow_failed` and
  `scheduled_dispatch_alert_undelivered`. Confirm the prefix, any `_total`
  suffix, and the label set (`workflow_type`, `task_queue`, `namespace`, `repo`,
  `workflow_file`). Also confirm that the deployed mctl-agents version includes
  #561. — DoD: scraped lines quoted in the PR description; the names used in
  tasks 2-4 match them exactly.
- [ ] 2. Add group `mctl-agents.scheduled-dispatch` to
  `platform-gitops/infra-components/observability/vm-rules/mctl-agents-worker-alerts.yaml`
  (depends on 1), with `MctlAgentsScheduledDispatchAlertUndelivered`,
  `MctlAgentsScheduledDispatchFailed` and `MctlAgentsScheduledDispatchMissed` as
  specified in design.md. Labels are `severity: warning` and `namespace: admins`.
  Rule 3 carries a comment that states the increase/new-series/absent/gate
  semantics. Update the file header to mention the new group and its routing. —
  DoD: existing groups are byte-identical; `promtool check rules` passes through
  `scripts/check-vm-rules.sh`.
- [ ] 3. Add the Telegram route `alertname =~ "MctlAgentsScheduledDispatch.*"` in
  `platform-gitops/bootstrap/templates/observability/monitoring.yaml`, directly
  after the `MctlAgentsImplement.*` route, with a rationale comment (depends on
  2). — DoD: `helm template` of the bootstrap chart renders the route, and no
  other route changes.
- [ ] 4. Add promtool tests to
  `vm-rules/tests/mctl-agents-worker-alerts_test.yaml` covering T1-T9 below
  (depends on 2). — DoD: `scripts/check-vm-rules.sh` passes locally and in
  `validate-manifests.yml`.
- [ ] 5. After merge and ArgoCD sync, check in vmalert that the three rules are
  loaded and that `MctlAgentsScheduledDispatchMissed` is inactive, given that
  the 2026-10-04 run completed. — DoD: vmalert UI or API shows the group with
  state inactive.

## Tests
- [ ] T1. Undelivered: a series born at 1 with `repo="mctlhq/portfolio"` and
  `workflow_file="weekly-refresh.yml"` fires, with both labels on the alert.
- [ ] T2. Undelivered: a series that goes from 1 to 2 later (increase arm) fires.
- [ ] T3. Undelivered: a series flat at 1 for more than 2h (converged) is quiet.
- [ ] T4. Failed: a `temporal_workflow_failed{workflow_type="ScheduledDispatchWorkflow",task_queue="mctl-dev-loop"}`
  series born at 1 fires, and the same series flat for more than 2h is quiet.
- [ ] T5. Failed: an increase on a different `workflow_type` (for example
  `DevLoopWorkflow`) is quiet.
- [ ] T6. Missed: worker gate series present for 9d, and the completed counter
  flat with no increase and no new series in the last 8d, fires after `for: 1h`.
- [ ] T7. Missed: the completed counter increases on day 5 of the window, so the
  rule is quiet.
- [ ] T8. Missed (restart): the old series stops, and a new series with a
  different `instance` appears at 1 within the window, so the rule is quiet.
- [ ] T9. Missed (unknown): no worker gate series and no completed series (a
  scrape gap or worker down) stays quiet.

## Rollback
Revert the PR. That removes the new VMRule group, the tests and the Telegram
route together, and ArgoCD reconciles both the VMRule and the Alertmanager
config back. For a noisy single rule while a fix is prepared, add an
Alertmanager silence on `alertname=MctlAgentsScheduledDispatchMissed` instead of
reverting.
