# Tasks: issue-1811-observability-enable-metrics-and-alerts

- [ ] 1. Add `platform-gitops/infra-components/data/cnpg/shared/vmpodscrape.yaml`
  (`VMPodScrape/shared-pg`, namespace `platform-db`, selector
  `cnpg.io/cluster: shared-pg` + `cnpg.io/podRole: instance`, port `metrics`,
  interval 30s, header comment explaining the native kind and why
  `enablePodMonitor` stays false). In `cluster.yaml` change only the comment on
  `enablePodMonitor: false` to point at `vmpodscrape.yaml` and the duplicate-scrape
  reason; do not touch `spec` values or the `restartedAt` annotation. Ship as
  its own PR. — DoD: kubeconform passes in `validate-manifests.yml`; after
  ArgoCD sync the `shared-pg` Application diff showed only the new object;
  shared-pg pod UIDs and `restartCount` are unchanged and no switchover is in
  `kubectl cnpg status shared-pg -n platform-db`; `count by (pod)(cnpg_collector_up{namespace="platform-db"})`
  returns one series per instance; every metric name used by tasks 2-3
  (`cnpg_pg_replication_in_recovery`, `cnpg_pg_replication_lag`,
  `cnpg_pg_replication_streaming_replicas`, `cnpg_pg_stat_archiver_*`,
  `cnpg_backends_total`, `cnpg_pg_settings_setting{name="max_connections"}`,
  `cnpg_collector_last_available_backup_timestamp`,
  `cnpg_collector_last_failed_backup_timestamp`) is confirmed present with a
  sane value, and the result is recorded in the task-2 PR description. If the
  backup metrics are missing or 0 despite R2 backups existing, task 3 switches
  to the fallback named in requirements.md Open questions.
- [ ] 2. (depends on 1) Add `vm-rules/shared-pg-alerts.yaml` (`VMRule/mctl-shared-pg-alerts`,
  group `mctl.shared-pg`) with SharedPgNoPrimary, SharedPgInstanceMissing,
  SharedPgInstanceDown, SharedPgReplicationLagHigh, SharedPgStandbyNotStreaming,
  SharedPgWALArchivingFailing, SharedPgWALArchivingStale, SharedPgConnectionsHigh,
  SharedPgVolumeFillingUp, SharedPgVolumeAlmostFull, SharedPgMetricsAbsent as
  specified in design.md, each with `severity`, `service: shared-pg` and a
  `Runbook:` link. Add a comment next to SharedPgInstanceMissing and next to
  `instances: 2` in `cluster.yaml` cross-referencing each other. — DoD:
  `scripts/check-vm-rules.sh` passes locally (promtool check + test).
- [ ] 3. (depends on 1) Add SharedPgBackupStale, SharedPgBackupFailed,
  SharedPgBackupMetricAbsent to `vm-rules/backup-alerts.yaml` group
  `mctl.backups`. — DoD: `scripts/check-vm-rules.sh` passes.
- [ ] 4. (depends on 2, 3) Routing in `bootstrap/templates/observability/monitoring.yaml`:
  add a commented `receiver: telegram, continue: true` route for
  `alertname =~ "SharedPg.*"` before the severity block; add `SharedPg.*` to the
  `alertname !~` exclusion of the `severity = "critical"` route; add
  `SharedPg.*` to the mctl-agent catch-all regex. Add CASES to
  `scripts/check-alertmanager-routes.py` for a critical and a warning SharedPg
  alert. — DoD: `python3 scripts/check-alertmanager-routes.py --selftest` and the
  real run pass; every SharedPg alert resolves to telegram exactly once plus
  mctl-agent.
- [ ] 5. (depends on 2, 3) Write `docs/runbooks/shared-pg.md` with one section
  per alert whose anchor matches the annotation links. — DoD: every `Runbook:`
  URL in the new rules resolves to an existing heading.
- [ ] 6. (depends on 1) Add `infra-components/observability/grafana-dashboards/cnpg-dashboard-configmap.yaml`
  with the upstream CloudNativePG dashboard JSON pinned to a recorded commit,
  datasource switched to the `$datasource` variable, defaults
  `platform-db`/`shared-pg`, label `grafana_dashboard: "1"`. — DoD: kubeconform
  passes; the dashboard appears in grafana.mctl.ai with populated
  status, replication, WAL/archiving, backups, connections and storage panels;
  no UID clash with an existing dashboard.

## Tests

- [ ] T1. `vm-rules/tests/shared-pg-alerts_test.yaml`: a healthy case (two pods,
  one with `cnpg_pg_replication_in_recovery=0`, lag 0, streaming replicas 1,
  archiver last_archived > last_failed and seconds_since 300, backends 50 of
  200, volume 50%) in which every new alert has `exp_alerts: []` at 30m; plus
  one firing case per alert: both pods in recovery and both pods absent
  (NoPrimary), two primaries (NoPrimary), one `up` series (InstanceMissing),
  `cnpg_collector_up=0` (InstanceDown), lag 600 for 15m, streaming replicas 0,
  last_failed > last_archived for 20m, seconds_since 8000, backends 170/200,
  volume 85% and 95%, no collector series (MetricsAbsent). Each firing case
  also asserts the alert is NOT firing before its `for` elapses.
- [ ] T2. Extend `vm-rules/tests/backup-alerts_test.yaml`: fresh backup is quiet;
  backup 27h old fires SharedPgBackupStale; timestamp 0 fires it; failed newer
  than available fires SharedPgBackupFailed; absent series fires
  SharedPgBackupMetricAbsent after 1h and not before.
- [ ] T3. `scripts/check-alertmanager-routes.py` CASES (task 4) pass in CI.
- [ ] T4. Live, after task 1 sync: shared-pg pods unchanged (UIDs, restartCount),
  `cnpg_*` series present for each instance; after tasks 2-3 sync, vmalert
  shows all SharedPg rules loaded and inactive on the healthy cluster.
- [ ] T5. Live deliberate condition (optional, non-disruptive): temporarily
  apply a test VMRule copy of SharedPgConnectionsHigh with threshold 0.01 and
  `for: 1m` to confirm end-to-end delivery to Telegram and mctl-agent, then
  delete it. No fault is injected into shared-pg itself.

## Rollback

Each task is a separate, additive PR; revert the PR. Reverting task 1 removes
only the `VMPodScrape` (ArgoCD prunes it), which stops collection without
touching the database pods; reverting tasks 2-4 removes rules and routes;
reverting task 6 removes the dashboard ConfigMap. No step changes the
`shared-pg` `Cluster` spec, so no rollback can roll or switch over the
database. If alerts are noisy before a fix lands, silence `alertname=~"SharedPg.*"`
in Alertmanager rather than reverting the scrape.
