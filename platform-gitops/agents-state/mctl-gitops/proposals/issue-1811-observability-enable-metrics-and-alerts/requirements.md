# Observability for shared-pg (CNPG): metrics, alerts, dashboard

## Context

The shared CloudNativePG cluster `shared-pg` (namespace `platform-db`, defined in
`platform-gitops/infra-components/data/cnpg/shared/cluster.yaml`) holds the
databases of mctl-api (including the lifecycle store), Temporal, Backstage, Argo
Workflows, Forgejo, ZITADEL, Grafana and nine tenant applications. Its
`spec.monitoring.enablePodMonitor` is `false` with the stale comment "enable when
Prometheus is added". The platform has run a VictoriaMetrics stack
(`victoria-metrics-k8s-stack` 0.72.5, `bootstrap/templates/observability/monitoring.yaml`)
for some time, but nothing scrapes the CNPG exporter on port 9187, so no
`cnpg_*` series exist and no alert covers a lost primary, a broken standby,
failing WAL archiving, a stale backup, connection exhaustion or a filling volume.

The issue asks for (1) scraping of the CNPG metrics endpoint in the way the
VictoriaMetrics stack discovers targets, without rolling the database pods,
(2) alerts for instance down / no primary, replication lag, WAL archiving,
backup age, connections and disk usage, routed like other platform alerts with
runbook links, and (3) a Grafana dashboard. A shared-pg outage takes down
mctl-api, through which mctl-agent files its incidents, so the alert path must
not depend on the agent alone.

## User stories

- AS a platform operator I WANT `cnpg_*` metrics for every shared-pg instance in
  VictoriaMetrics SO THAT I can see primary/standby health, lag, archiving,
  backups and connections.
- AS a platform operator I WANT to be paged on Telegram when shared-pg has no
  primary, an instance is missing, replication or WAL archiving breaks, the
  nightly backup is stale, connections near `max_connections` or the data volume
  fills SO THAT I can act before tenants and the control plane lose their
  database.
- AS an on-call engineer I WANT each alert to link to a runbook section SO THAT
  I know the first diagnostic steps without reverse-engineering the rule.
- AS a reviewer I WANT every rule covered by a promtool unit test in CI SO THAT
  a rule that can never fire, or fires on a healthy cluster, is caught before
  merge.
- AS a tenant owner I WANT the rollout to cause no switchover or restart of
  shared-pg SO THAT my application sees no interruption.

## Acceptance criteria (EARS)

- WHEN the change is synced THE SYSTEM SHALL scrape port `metrics` (9187) of
  every pod labelled `cnpg.io/cluster=shared-pg, cnpg.io/podRole=instance` in
  `platform-db` through a native `VMPodScrape`, so that `cnpg_collector_up` has
  one series per instance (currently `shared-pg-1` and `shared-pg-2`).
- WHILE the change is rolled out THE SYSTEM SHALL leave the `shared-pg`
  `Cluster` spec and its `kubectl.kubernetes.io/restartedAt` annotation
  unchanged, so that no instance is restarted and no switchover occurs.
- WHILE `spec.monitoring.enablePodMonitor` stays `false` THE SYSTEM SHALL have
  exactly one scrape configuration for the shared-pg exporter (no
  operator-generated `PodMonitor` converted alongside the `VMPodScrape`).
- IF no shared-pg instance reports itself as primary (or none is scraped), or
  more than one does, for 5 minutes THEN THE SYSTEM SHALL fire
  `SharedPgNoPrimary` (severity critical).
- IF fewer than the declared number of instances (2) are scraped up for 10
  minutes, or an instance's `cnpg_collector_up` is 0 for 5 minutes, THEN THE
  SYSTEM SHALL fire `SharedPgInstanceMissing` / `SharedPgInstanceDown`
  (severity warning).
- IF no `cnpg_collector_up` series exists for shared-pg for 15 minutes THEN THE
  SYSTEM SHALL fire `SharedPgMetricsAbsent` (severity warning), because every
  other shared-pg rule is blind while it lasts.
- IF a standby's `cnpg_pg_replication_lag` exceeds 300 seconds for 10 minutes, or
  the primary reports zero streaming replicas for 10 minutes, THEN THE SYSTEM
  SHALL fire `SharedPgReplicationLagHigh` / `SharedPgStandbyNotStreaming`
  (severity warning).
- IF the primary's last WAL archive failure is newer than its last successful
  archive for 15 minutes, or no WAL segment has been archived for 2 hours, THEN
  THE SYSTEM SHALL fire `SharedPgWALArchivingFailing` (critical) /
  `SharedPgWALArchivingStale` (warning).
- IF the newest available shared-pg base backup is older than 26 hours, or the
  last failed backup is newer than the last successful one, THEN THE SYSTEM
  SHALL fire `SharedPgBackupStale` / `SharedPgBackupFailed` (severity warning),
  and IF the backup timestamp series is absent for 1 hour THEN THE SYSTEM SHALL
  fire `SharedPgBackupMetricAbsent`.
- IF backends on an instance exceed 80% of `max_connections` for 10 minutes THEN
  THE SYSTEM SHALL fire `SharedPgConnectionsHigh` (severity warning).
- IF a shared-pg data PVC is over 80% used for 15 minutes THEN THE SYSTEM SHALL
  fire `SharedPgVolumeFillingUp` (warning), and over 90% for 5 minutes
  `SharedPgVolumeAlmostFull` (critical).
- WHEN any `SharedPg.*` alert fires THE SYSTEM SHALL deliver it to the Telegram
  receiver exactly once AND to the mctl-agent receiver, and each alert SHALL
  carry a `Runbook:` link to `docs/runbooks/shared-pg.md`.
- WHEN `scripts/check-vm-rules.sh` runs in `validate-manifests.yml` THE SYSTEM
  SHALL execute promtool unit tests in which every new alert fires on a seeded
  fault and every new alert is silent on a seeded healthy two-instance cluster.
- WHEN Grafana starts THE SYSTEM SHALL provision a CloudNativePG dashboard
  (vendored upstream JSON) from a ConfigMap labelled `grafana_dashboard: "1"`
  that renders shared-pg data from the VictoriaMetrics datasource.

## Out of scope

- Scraping the CNPG operator (`cnpg-system`) or the PgBouncer `Pooler`
  (`shared-pg-pooler-rw`) metrics endpoints; panels of the upstream dashboard
  that depend on operator metrics may stay empty.
- Changing any `shared-pg` capacity setting (`max_connections`, storage size,
  role `connectionLimit`s) or the backup configuration.
- Per-database / per-tenant alerting, custom CNPG monitoring queries
  (`spec.monitoring.customQueriesConfigMap`), and query-level performance
  metrics (`pg_stat_statements`).
- Migrating backups to the barman-cloud plugin (CNPG 1.26+), even though the
  in-tree backup metrics used here are deprecated upstream.
- Monitoring other Postgres instances (tenant erpact MariaDB, Temporal's own
  metrics).

## Open questions

- Backup metrics: the design relies on `cnpg_collector_last_available_backup_timestamp`
  and `cnpg_collector_last_failed_backup_timestamp` from the in-tree barman
  integration of CNPG 1.25 (chart `cloudnative-pg` 0.23.0). Whether they are
  populated on the instance(s) that serve them could not be observed from this
  run; task 1's live check must confirm it before the backup rules merge, else
  the fallback is an alert on the `Backup` objects' status via
  kube-state-metrics custom resource state.
- Thresholds (300 s lag, 2 h archive gap, 26 h backup age, 80% connections,
  80/90% disk) are proposed defaults; the issue gives none.
- Whether `SharedPgNoPrimary` and `SharedPgWALArchivingFailing` should be
  `critical` (they are here, because they mean writes are down or PITR is
  broken) is a judgement call for the reviewer.
- The upstream dashboard version to vendor (pinned commit of
  `cloudnative-pg/grafana-dashboards`) is left to the implementer; it must be
  compatible with Grafana 12.4.2.
