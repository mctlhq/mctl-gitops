# Tasks: issue-1830-observability-shared-pg-alerts-routing-r

- [ ] 1. Pre-flight against the live scrape (no repo change). In vmsingle,
  confirm three things:
  - The label set on `cnpg_pg_replication_in_recovery`,
    `cnpg_pg_replication_streaming_replicas`, `cnpg_pg_stat_archiver_*` and
    `cnpg_collector_*` includes `namespace` and `pod`.
  - `kubelet_volume_stats_capacity_bytes{namespace="platform-db"}` shows the
    shared-pg PVC names (expected `shared-pg-1`, `shared-pg-2`).
  - Each primary-joined expression from design.md returns exactly one series
    (`shared-pg-2`) with the threshold removed.

  DoD: the results are pasted into the PR description, and any name or label
  that differs is reflected in tasks 2-3 before review.
- [ ] 2. (depends on 1) Add `platform-gitops/infra-components/observability/vm-rules/shared-pg-alerts.yaml`.
  It defines `VMRule/mctl-shared-pg-alerts` in group `mctl.shared-pg` with the
  11 alerts and expressions in the design.md table. The WAL and StandbyNotStreaming
  rules are joined `on(namespace, pod)` with `cnpg_pg_replication_in_recovery == 0`.
  Each alert has `severity`, `service: shared-pg` and a
  `Runbook: .../docs/runbooks/shared-pg.md#<alertname-lowercased>` link. The
  header comment explains the replica caveat. Add a comment-only cross-reference
  next to `instances: 2` in `infra-components/data/cnpg/shared/cluster.yaml`.
  DoD: `promtool check rules` passes on the generated file, and `git diff`
  of `cluster.yaml` is one comment line.
- [ ] 3. (depends on 1) Add SharedPgBackupStale, SharedPgBackupFailed and
  SharedPgBackupMetricAbsent to `vm-rules/backup-alerts.yaml` group
  `mctl.backups`, using `max by (namespace)` across instances, with a comment
  on why. DoD: `promtool check rules` passes.
- [ ] 4. (depends on 2, 3) Routing in `platform-gitops/bootstrap/templates/observability/monitoring.yaml`:
  - Add the commented `receiver: telegram, continue: true` route for
    `alertname =~ "SharedPg.*"` after the `PlatformWebEndpoint.*` route.
  - Append `|SharedPg.*` to the `alertname !~` exclusion of the
    `severity = "critical"` route, and update its comment.
  - Append `|SharedPg.*` to the mctl-agent catch-all regex.

  Add the three CASES from design.md to `scripts/check-alertmanager-routes.py`.
  DoD: `python3 scripts/check-alertmanager-routes.py --selftest` and the real
  run pass. Every SharedPg alert resolves to `telegram, mctl-agent`, with
  telegram exactly once, and the matcher-less mctl-agent route is still last.
- [ ] 5. (depends on 2, 3) Write `docs/runbooks/shared-pg.md`. It has an intro
  covering topology, dependants and safety rules. It has one `## SharedPg...`
  heading per alert (14 headings: 11 from task 2, 3 from task 3), each covering
  meaning, first checks and safe actions, and it links to `restore.md`. It also
  has a "Why some rules read only the primary" section. DoD: every `Runbook:`
  URL in the two rule files resolves to a heading (T4).
- [ ] 6. Add `platform-gitops/infra-components/observability/grafana-dashboards/cnpg-dashboard-configmap.yaml`
  (`ConfigMap/mctl-cnpg-dashboard`, namespace `monitoring`, label
  `grafana_dashboard: "1"`). It vendors the upstream
  `cloudnative-pg/grafana-dashboards` cluster dashboard JSON, and the header
  records the commit SHA and local edits. The datasource becomes the
  `$datasource` variable, and the defaults are `platform-db` / `shared-pg`.
  DoD: kubeconform passes in `validate-manifests.yml`, and the dashboard UID
  does not clash with an existing one (grep). After sync the dashboard appears
  in Grafana with status, replication, WAL and connection panels populated for
  shared-pg.

## Tests

- [ ] T1. New `vm-rules/tests/shared-pg-alerts_test.yaml`:
  - **Healthy fixture.** Replica `shared-pg-1` has in_recovery 1,
    streaming_replicas 0, lag 0, collector_up 1, up 1, seconds_since_last_archival
    `'71390+60x120'`, archived later than failed, backends 1 and
    max_connections 200. Primary `shared-pg-2` has in_recovery 0,
    streaming_replicas 1, seconds_since 506, archived later than failed,
    backends 88 of 200, and both PVCs at 50%. All 11 alerts must have
    `exp_alerts: []` at 30m and 2h.
  - **Adversarial replica case.** As healthy, but the replica's last_failed is
    later than its last_archived. Both WAL rules stay quiet.
  - **One firing case per alert**, as listed in design.md section 3, each
    checking "not firing before `for`" and "firing after".

  Removing the primary join from any joined rule must make the healthy test
  fail. Verify this once locally and note it in the PR.
- [ ] T2. Extend `vm-rules/tests/backup-alerts_test.yaml`:
  - **Healthy case** at `interval: 10m`, eval `27h15m`. The primary has
    last_available `90000` and last_failed `3600`. The replica has
    last_available `0` and last_failed `0`. All three SharedPgBackup alerts are
    quiet.
  - **Firing cases.** Primary at `-10000` fires Stale at 27h. Both pods at `0`
    fire Stale at 27h. Primary failed later than available fires Failed. No
    series leaves MetricAbsent quiet at 50m and firing at 75m.

  Replacing `max by (namespace)` with a per-pod expression must make the
  healthy case fail. Verify this once locally.
- [ ] T3. `scripts/check-vm-rules.sh` and `scripts/check-vm-rules.sh --selftest`
  pass. These include the route checker with the new CASES. They are run in
  CI by `validate-manifests.yml`.
- [ ] T4. Runbook anchors. For each `Runbook:` URL with `shared-pg.md#` in the
  two rule files, a matching `## ` heading must exist. Lowercase the heading to
  get the anchor. Check this with a grep loop in the PR and paste the output.
- [ ] T5. Optional live end-to-end check. Apply a temporary VMRule copy of
  SharedPgConnectionsHigh named `SharedPgConnectionsHighDeliveryTest`, with
  threshold 0.01 and `for: 1m`. Confirm one Telegram message and an mctl-agent
  incident, then delete the rule. No fault is injected into shared-pg.
- [ ] T6. Live after sync. vmalert lists all 14 SharedPg rules as loaded and
  `inactive`, with no evaluation errors. The Alertmanager status page shows the
  new route.

## Rollback

All changes are additive and live in one PR (or two, if the dashboard is split
out). Reverting the PR removes the rules, routes, runbook and dashboard
ConfigMap, and ArgoCD prunes the VMRule and ConfigMap. Nothing touches the
`Cluster/shared-pg` spec or the scrape, so no rollback can roll the database
or stop metric collection. If a rule is noisy before a fix lands, silence
`alertname=~"SharedPg.*"` (or the single alertname) in Alertmanager instead of
reverting.
