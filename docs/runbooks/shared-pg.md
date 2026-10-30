# shared-pg runbook

`shared-pg` is the shared CloudNativePG cluster in namespace `platform-db`:
two instances (primary plus hot standby), WAL and `prefer-standby` backups to
R2. It holds the databases of mctl-api (including the lifecycle store),
Temporal, Backstage, Argo Workflows, Forgejo, ZITADEL, Grafana and tenant
applications. Alerts are in
`platform-gitops/infra-components/observability/vm-rules/shared-pg-alerts.yaml`
and `backup-alerts.yaml`. Recovery: [restore.md](restore.md).

Safety rules:

- Never delete a PVC or pod by hand to "fix" a role.
- A planned roll goes through the `restartedAt` annotation.
- Silence `alertname=~"SharedPg.*"` during planned maintenance.

## SharedPgNoPrimary

**Meaning.** shared-pg has zero or more than one primary.

**First checks.** `kubectl -n platform-db get cluster shared-pg -o yaml` (status.currentPrimary, phase); pod logs in Loki; `kubectl cnpg status shared-pg -n platform-db` if installed.

**Safe actions.** Wait for CNPG failover. Never delete PVCs or pods by hand. For two primaries, stop and escalate. If the data is lost, see restore.md.

## SharedPgInstanceMissing

**Meaning.** Fewer than 2 shared-pg pods are up.

**First checks.** `kubectl -n platform-db get pods -l cnpg.io/cluster=shared-pg`; node status; pending PVCs.

**Safe actions.** Let CNPG recreate the pod; fix node or scheduling problems. Do not delete the PVC.

## SharedPgInstanceDown

**Meaning.** The exporter on one pod cannot reach PostgreSQL.

**First checks.** Pod logs and `kubectl describe pod`.

**Safe actions.** Wait for the liveness restart; escalate if it persists.

## SharedPgReplicationLagHigh

**Meaning.** A replica lags the primary by over 300s.

**First checks.** Query `cnpg_pg_replication_lag`; check the replica's logs and I/O; long-running transactions on the primary.

**Safe actions.** Wait if it falls; otherwise let CNPG rebuild the replica. Do not touch the primary.

## SharedPgStandbyNotStreaming

**Meaning.** The primary has no streaming standby.

**First checks.** Replica pod status and logs; `pg_stat_replication` on the primary.

**Safe actions.** Fix the replica pod; CNPG reattaches it. Do not delete PVCs.

## SharedPgWALArchivingFailing

**Meaning.** The last WAL archive on the primary failed after the last success. WAL piles up on the volume.

**First checks.** Primary pod logs (barman-cloud-wal-archive), `cnpg-backup-r2` credentials, R2 reachability, volume usage.

**Safe actions.** Fix the credentials or connectivity. Do not delete WAL files by hand.

## SharedPgWALArchivingStale

**Meaning.** No WAL archived for over 2h on the primary (archive_timeout is 15min).

**First checks.** Same as SharedPgWALArchivingFailing; also check the primary is writing at all.

**Safe actions.** Fix the cause; see restore.md if PITR coverage is lost.

## SharedPgConnectionsHigh

**Meaning.** A pod uses over 80% of max_connections (200).

**First checks.** `sum by (pod) (cnpg_backends_total)`; `pg_stat_activity` by role.

**Safe actions.** Find the leaking client; check the per-role connectionLimit in cluster.yaml. Restart the offending client, not the database.

## SharedPgRoleConnectionsHigh

**Meaning.** One of mctl-api, temporal or backstage holds over 80% of its role `connectionLimit` in `infra-components/data/cnpg/shared/cluster.yaml`. At the limit that role's new connections fail with "too many connections for role" while shared-pg still has free slots.

**First checks.** `sum by (usename) (cnpg_backends_total{namespace="platform-db"})`; `pg_stat_activity` grouped by `usename, application_name, client_addr` to find the pod. Is a rolling update running (three mctl-api pods)?

**Safe actions.** Restart the pod holding the excess, not the database. mctl-api's budget is `DB_POOL_MAX_CONNS` (default 8) per database URL per pod; temporal's is `maxConns` in `bootstrap/templates/data/temporal.yaml`. Raise a `connectionLimit` only together with the threshold in this rule.

## SharedPgVolumeFillingUp

**Meaning.** A shared-pg PVC is over 80% used.

**First checks.** `kubelet_volume_stats_used_bytes`; check for WAL buildup (archiving alerts) and large tables.

**Safe actions.** Raise `storage.size` in cluster.yaml (hcloud-volumes expands online).

## SharedPgVolumeAlmostFull

**Meaning.** A shared-pg PVC is over 90% used; PostgreSQL stops when it is full.

**First checks.** As for SharedPgVolumeFillingUp.

**Safe actions.** Raise `storage.size` in cluster.yaml now.

## SharedPgInstanceMetricsIncomplete

**Meaning.** A reachable instance exports `cnpg_collector_up` but not `max_connections` (`cnpg_pg_settings_setting`) or `cnpg_pg_replication_in_recovery`. SharedPgConnectionsHigh, SharedPgNoPrimary and the primary-joined rules cannot see that pod while this lasts.

**First checks.** The pod's `/metrics` on port `metrics`; a CNPG operator upgrade that renamed a default query; a custom `monitoring.customQueriesConfigMap` that replaced the defaults.

**Safe actions.** Restore the metric. Until then, check connections and role on that pod directly.

## SharedPgMetricsAbsent

**Meaning.** No cnpg_collector_up series; all other SharedPg alerts are blind. SharedPgNoPrimary deliberately stays quiet here: with no in_recovery series the role is unknown, not "zero primaries".

**First checks.** VMPodScrape/shared-pg, vmagent targets, pod port `metrics`.

**Safe actions.** Restore the scrape; check the cluster directly meanwhile.

## SharedPgBackupStale

**Meaning.** The newest backup in the R2 catalog, as the Barman Cloud Plugin reports it, is older than 26h (daily at 02:00 UTC).

**First checks.** `kubectl -n platform-db get backup`; ScheduledBackup shared-pg-daily (`method: plugin`); the `plugin-barman-cloud` sidecar log on the standby; ObjectStore `shared-pg-r2` and its `cnpg-backup-r2` credentials.

**Safe actions.** Fix the cause and take an on-demand Backup. See restore.md.

## SharedPgBackupFailed

**Meaning.** The last failed backup is newer than the last successful one.

**First checks.** `kubectl -n platform-db describe backup` for the failed one.

**Safe actions.** Fix the cause and take an on-demand Backup.

## SharedPgBackupMetricAbsent

**Meaning.** No instance reports a non-zero `barman_cloud_cloudnative_pg_io_last_available_backup_timestamp`: the plugin sidecar is not exporting it, or it sees no backup in the R2 catalog. Stale and Failed are blind while this lasts. The in-tree `cnpg_collector_last_available_backup_timestamp` still exists but reads 0 or a frozen value since the plugin switch (#2084); it is not a backup signal.

**First checks.** The `plugin-barman-cloud` init (native sidecar) container on each instance and its log; `kubectl -n platform-db get objectstore shared-pg-r2`; the Cluster's `spec.plugins` and `status.pluginStatus`; a plugin upgrade that renamed the metrics.

**Safe actions.** Fix the sidecar or the object-store access; if the plugin renamed its metrics, migrate the rules in `backup-alerts.yaml` and the CNPG dashboard together.

## Why some rules read only the primary

On a healthy cluster the standby reports `seconds_since_last_archival` in the
tens of thousands and growing, `streaming_replicas = 0` and
`last_available_backup_timestamp = 0`. These values only mean something on the
primary, so SharedPgStandbyNotStreaming and the WAL rules are joined on
`cnpg_pg_replication_in_recovery == 0`, and the backup rules use
`max by (namespace)`. Do not simplify the joins away; the rules would fire
permanently.
