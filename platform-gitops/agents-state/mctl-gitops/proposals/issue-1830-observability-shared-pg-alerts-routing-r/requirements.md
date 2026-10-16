# shared-pg alerts, Alertmanager routing, runbook and CNPG dashboard (#1811 tasks 2-6)

## Context

#1811 asked for observability of the shared CloudNativePG cluster `shared-pg`
(namespace `platform-db`), which holds the databases of mctl-api (including
the lifecycle store), Temporal, Backstage, Argo Workflows, Forgejo, ZITADEL,
Grafana and the tenant applications. Its accepted proposal
(`platform-gitops/agents-state/mctl-gitops/proposals/issue-1811-observability-enable-metrics-and-alerts/`)
has six tasks. Only task 1, the `VMPodScrape/shared-pg` scrape, shipped (#1817,
merged as `bf9ccb94`, live-verified on #1811). The DevLoop for #1811 completed
when #1817 merged, so tasks 2-6 and tests T1-T3/T5 were never built. Today
`cnpg_*` series are collected, but no alert uses them, nothing routes them to a
human, there is no runbook and no dashboard.

This proposal implements tasks 2-6 as designed in #1811, with one hard
correction from the #1811 live check: on the healthy cluster the replica
(`shared-pg-1`) reports `cnpg_pg_stat_archiver_seconds_since_last_archival`
around 71390 and growing, `cnpg_collector_last_available_backup_timestamp = 0`
and `cnpg_pg_replication_streaming_replicas = 0`. These values only mean
something on the primary. Any per-pod archiver, backup or streaming rule would
fire permanently. So these rules are evaluated on the primary only, or
aggregated across instances, and the unit-test healthy fixtures contain a
replica with exactly these values.

## User stories

- AS a platform operator I WANT a Telegram page when shared-pg has no primary,
  loses an instance, stops replicating or archiving WAL, misses its nightly
  backup, nears `max_connections` or fills its volume SO THAT I can act before
  the control plane and tenants lose their database.
- AS an on-call engineer I WANT each SharedPg alert to link to its own runbook
  section SO THAT I know the first diagnostic steps and which actions are safe.
- AS a reviewer I WANT promtool unit tests that seed a healthy two-instance
  cluster with the real replica values SO THAT a rule that would fire forever
  on the replica is caught in CI, not in production.
- AS an operator I WANT a CloudNativePG dashboard in Grafana SO THAT I can see
  primary/standby status, lag, archiving, backups, connections and storage.

## Acceptance criteria (EARS)

Rules (`infra-components/observability/vm-rules/shared-pg-alerts.yaml`,
`VMRule/mctl-shared-pg-alerts`, group `mctl.shared-pg`). In the criteria below
`S` means the selector `namespace="platform-db", pod=~"shared-pg-[0-9]+"`:

- WHILE shared-pg has exactly one instance with `cnpg_pg_replication_in_recovery == 0`
  THE SYSTEM SHALL NOT fire `SharedPgNoPrimary`. IF zero or more than one
  instance reports itself as primary (including no series at all) for 5m THEN
  THE SYSTEM SHALL fire it with severity `critical`.
- IF fewer than 2 shared-pg `up` series equal 1 for 10m THEN THE SYSTEM SHALL
  fire `SharedPgInstanceMissing` (warning). IF an instance's `cnpg_collector_up`
  is 0 for 5m THEN THE SYSTEM SHALL fire `SharedPgInstanceDown` (warning).
- IF any instance's `cnpg_pg_replication_lag` exceeds 300s for 10m THEN THE
  SYSTEM SHALL fire `SharedPgReplicationLagHigh` (warning).
- IF the **primary** reports `cnpg_pg_replication_streaming_replicas < 1` for
  10m THEN THE SYSTEM SHALL fire `SharedPgStandbyNotStreaming` (warning). The
  replica's own value of 0 SHALL NOT fire it.
- IF on the **primary** `cnpg_pg_stat_archiver_last_failed_time` is newer than
  `cnpg_pg_stat_archiver_last_archived_time` for 15m THEN THE SYSTEM SHALL fire
  `SharedPgWALArchivingFailing` (critical). IF the primary's
  `cnpg_pg_stat_archiver_seconds_since_last_archival` exceeds 7200 for 10m THEN
  THE SYSTEM SHALL fire `SharedPgWALArchivingStale` (warning).
- WHILE a replica reports `cnpg_pg_stat_archiver_seconds_since_last_archival`
  of any size, or any `last_failed_time` / `last_archived_time` pair, THE
  SYSTEM SHALL NOT fire either WAL archiving alert on that replica's values.
  Both rules are joined `on(namespace, pod)` with
  `cnpg_pg_replication_in_recovery == 0`.
- IF an instance's backends exceed 80% of its `max_connections` setting for
  10m THEN THE SYSTEM SHALL fire `SharedPgConnectionsHigh` (warning).
- IF a shared-pg data PVC is over 80% used for 15m THEN THE SYSTEM SHALL fire
  `SharedPgVolumeFillingUp` (warning). IF it is over 90% used for 5m THEN THE
  SYSTEM SHALL fire `SharedPgVolumeAlmostFull` (critical).
- IF no `cnpg_collector_up{S}` series exists for 15m THEN THE SYSTEM SHALL fire
  `SharedPgMetricsAbsent` (warning).

Backup rules (`vm-rules/backup-alerts.yaml`, group `mctl.backups`):

- IF `time() - max by (namespace) (cnpg_collector_last_available_backup_timestamp{S})`
  exceeds 26h (93600s) for 15m THEN THE SYSTEM SHALL fire `SharedPgBackupStale`
  (warning). This includes the case where every instance reports 0.
- IF `max by (namespace)` of `cnpg_collector_last_failed_backup_timestamp{S}`
  is greater than `max by (namespace)` of the last available backup timestamp
  for 15m THEN THE SYSTEM SHALL fire `SharedPgBackupFailed` (warning).
- IF `cnpg_collector_last_available_backup_timestamp{S}` is absent for 1h THEN
  THE SYSTEM SHALL fire `SharedPgBackupMetricAbsent` (warning).
- WHILE the primary holds a fresh backup timestamp and the replica holds 0, THE
  SYSTEM SHALL NOT fire any SharedPgBackup alert.

Every rule, in both files:

- THE SYSTEM SHALL carry the labels `severity` and `service: shared-pg`, and a
  description ending in
  `Runbook: https://github.com/mctlhq/mctl-gitops/blob/main/docs/runbooks/shared-pg.md#<alertname-lowercased>`
  that resolves to an existing heading in `docs/runbooks/shared-pg.md`.

Routing (`bootstrap/templates/observability/monitoring.yaml`):

- WHEN any `SharedPg.*` alert fires, of any severity, THE SYSTEM SHALL deliver
  it to the `telegram` receiver exactly once AND to the `mctl-agent` receiver.
- WHEN `python3 scripts/check-alertmanager-routes.py --selftest` and the real
  run execute THE SYSTEM SHALL pass, with new CASES for a critical and a
  warning SharedPg alert, and for a SharedPg backup alert, each resolving to
  `telegram, mctl-agent`.

Tests and CI:

- WHEN `scripts/check-vm-rules.sh` runs THE SYSTEM SHALL pass `promtool check rules`
  and `promtool test rules`. The tests SHALL include healthy fixtures with a
  primary (`shared-pg-2`) and a replica (`shared-pg-1`) using the values from
  the #1811 live check (replica: in_recovery 1, streaming_replicas 0,
  seconds_since_last_archival 71390 and growing, last_available_backup_timestamp 0,
  last_failed_backup_timestamp 0). Every new alert SHALL be asserted silent on
  them, at an eval time long enough that the replica's values would cross every
  threshold a per-pod rule would use.
- IF a rule is rewritten per pod (the primary join or the `max by (namespace)`
  removed) THEN at least one healthy-fixture test SHALL fail.

Dashboard:

- WHEN Grafana's dashboard sidecar scans the cluster THE SYSTEM SHALL provision
  the upstream CloudNativePG dashboard from a ConfigMap labelled
  `grafana_dashboard: "1"`. The dashboard SHALL be vendored from
  `cloudnative-pg/grafana-dashboards` at a commit SHA recorded in the file
  header, and SHALL default to namespace `platform-db` and cluster `shared-pg`.

Live:

- WHEN the change is synced on the healthy cluster THE SYSTEM SHALL show every
  SharedPg rule loaded in vmalert and in state `inactive`.

## Out of scope

- The scrape itself (task 1, shipped in #1817). This proposal does not change
  `VMPodScrape/shared-pg` or the `Cluster/shared-pg` spec.
- Scraping the CNPG operator or the PgBouncer `Pooler`. Dashboard panels that
  need operator metrics may stay empty.
- Any change to shared-pg capacity (`max_connections`, storage size,
  `instances`) or to its backup configuration.
- Migrating to the barman-cloud plugin, even though the in-tree backup metrics
  are deprecated upstream.
- A generic CI check that every `Runbook:` anchor in vm-rules resolves. This
  proposal verifies its own anchors (test T4). No rule in the repo uses anchors
  today, and a repo-wide checker is a separate change.
- Injecting real faults into shared-pg. T5 is an optional synthetic delivery test.

## Open questions

- Thresholds (300s lag, 2h archive gap, 26h backup age, 80% connections,
  80/90% volume) are the #1811 defaults. Neither issue sets them. They are kept
  unchanged.
- Severities: `SharedPgNoPrimary`, `SharedPgWALArchivingFailing` and
  `SharedPgVolumeAlmostFull` are `critical` and the rest are `warning`, as in
  #1811. All of them page Telegram anyway, so severity only changes the label.
- The WAL rules use the primary join (`and on(namespace, pod) cnpg_pg_replication_in_recovery == 0`)
  rather than `min` across instances, which the issue also allows. `min` would
  hide a stale primary for up to 2h after a switchover, while the old primary's
  value is still the smaller one. The trade-off is that during a no-primary
  window the WAL rules evaluate to nothing, which is acceptable because
  `SharedPgNoPrimary` covers that window. The reviewer may prefer `min`.
- The live check does not show which PVC names exist. `cluster.yaml` has no
  `walStorage`, so the volume rules match `persistentvolumeclaim=~"shared-pg-[0-9]+"`.
  The implementer confirms the names with
  `kubelet_volume_stats_capacity_bytes{namespace="platform-db"}` before merging.
- The upstream dashboard commit to pin is left to the implementer, who records
  it in the ConfigMap header. It must work with Grafana 12.4.2.
