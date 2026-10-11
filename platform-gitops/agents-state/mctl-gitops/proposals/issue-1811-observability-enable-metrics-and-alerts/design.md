# Design: issue-1811-observability-enable-metrics-and-alerts

## Current state

- `platform-gitops/infra-components/data/cnpg/shared/cluster.yaml` defines
  `Cluster/shared-pg` (CNPG, `instances: 2`, `primaryUpdateMethod: switchover`,
  `storage.size: 40Gi` on `hcloud-volumes`, `max_connections: "200"`,
  `archive_timeout: "15min"`, barman backups to R2 with `retentionPolicy: "14d"`,
  `target: prefer-standby`). It ends with
  `monitoring.enablePodMonitor: false  # enable when Prometheus is added`.
  The `kubectl.kubernetes.io/restartedAt` annotation is the only reviewed way
  pods are rolled; `bootstrap/templates/data/shared-pg.yaml` exempts just that
  annotation from `ignoreDifferences` and syncs with `ApplyOutOfSyncOnly=true`.
- `scheduled-backup.yaml` runs `ScheduledBackup/shared-pg-daily` at 02:00 UTC.
- `networkpolicy.yaml` (`allow-shared-pg-ingress`) already admits TCP 9187
  ("CNPG exports Postgres metrics on 9187") from the `monitoring` namespace,
  so no network change is needed for scraping.
- The operator is chart `cloudnative-pg` 0.23.0
  (`bootstrap/templates/data/cloudnative-pg.yaml`), i.e. CNPG 1.25.x.
- Metrics stack: `bootstrap/templates/observability/monitoring.yaml` deploys
  `victoria-metrics-k8s-stack` 0.72.5. `vmagent.spec.selectAllByDefault: true`
  and `vmalert.spec.selectAllByDefault: true`, so VM operator objects in any
  namespace are picked up. Grafana discovers dashboards through the sidecar
  (`label: grafana_dashboard`, `labelValue: "1"`, `searchNamespace: ALL`).
- Scrape convention: every recent scrape is a native VM kind, not a
  `monitoring.coreos.com` object, because the operator's auto-conversion shows
  up as ArgoCD drift — see the header comments of
  `argo-workflows/config/servicemonitor.yaml`,
  `infra-components/data/valkey/vmservicescrape.yaml` and
  `infra-components/data/forgejo/vmservicescrape.yaml`. Scrape objects live
  next to the component they scrape. `scripts/check-vm-rules.sh` rejects any
  non-VMRule object under `vm-rules/` (the #1159 double-scrape incident).
- Alert rules: `infra-components/observability/vm-rules/*.yaml` (VMRule,
  namespace `monitoring`), synced by the monitoring Application
  (`monitoring.yaml` source path `.../vm-rules`). Unit tests live in
  `vm-rules/tests/<file>_test.yaml` and read `generated/<file>.yaml`, produced
  by `scripts/check-vm-rules.sh` (promtool `check rules` + `test rules`), run
  by `.github/workflows/validate-manifests.yml` ("Check and unit-test alerting
  rules"). Backup freshness rules are grouped in `vm-rules/backup-alerts.yaml`
  (group `mctl.backups`; e.g. `ForgejoBackupStale`), as the header of
  `forgejo-alerts.yaml` states. `forgejo-alerts.yaml` already uses
  `kubelet_volume_stats_*` for PVC fill, so those series exist.
- Routing: the Alertmanager tree in `monitoring.yaml` is an allowlist. Alerts
  whose remedy or reporting path involves mctl-agent/mctl-api use a
  `receiver: telegram, continue: true` prefix route plus an entry in the
  mctl-agent catch-all (pattern `MctlApi.*`, `PlatformWebEndpoint.*`). The
  `severity = "critical"` telegram route excludes, by alertname, every alert
  already paged by an earlier `continue: true` telegram route.
  `scripts/check-alertmanager-routes.py` (invoked by `check-vm-rules.sh`)
  fails CI if any vm-rules alert would reach Telegram twice or a critical one
  not at all.
- Runbooks: `docs/runbooks/` has `forgejo.md`, `restore.md`, `zitadel.md`, ...;
  none for shared-pg. Alerts link with
  `Runbook: https://github.com/mctlhq/mctl-gitops/blob/main/docs/runbooks/<x>.md`.
- No rule anywhere under `vm-rules/` references `cnpg_` or `platform-db`
  (grep). The only shared-pg signals today are indirect (ForgejoDown, ZITADEL
  probes, mctl-api readiness).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/infra-components/data/cnpg/shared/cluster.yaml` — identical
  to the clone (`diff -q`): `enablePodMonitor: false` is what is deployed from
  git. The directory lists no scrape object.
- `mctl_list_incidents(service=shared-pg)` — 0 active incidents; consistent with
  no shared-pg alerting existing, says nothing about health.
- Not observed: whether `cnpg_*` series are absent in VictoriaMetrics, the live
  pod/PVC names in `platform-db`, the current primary, and whether the backup
  timestamp metrics are populated. The read-only mctl MCP tools cover
  catalogue services, not `platform-db` infrastructure, and this run has no
  cluster access. These are recorded under Open questions and turned into a
  live verification step (task 1).

## Proposed solution

### 1. Scrape: a native `VMPodScrape` beside the cluster

New file `infra-components/data/cnpg/shared/vmpodscrape.yaml` (synced by the
existing `shared-pg` Application into `platform-db`):

```yaml
apiVersion: operator.victoriametrics.com/v1beta1
kind: VMPodScrape
metadata:
  name: shared-pg
  namespace: platform-db
  labels:
    app.kubernetes.io/name: shared-pg
spec:
  selector:
    matchLabels:
      cnpg.io/cluster: shared-pg
      cnpg.io/podRole: instance   # excludes the PgBouncer Pooler pods
  podMetricsEndpoints:
    - port: metrics               # 9187, named by the CNPG instance manager
      interval: 30s
      path: /metrics
      scheme: http
```

It selects the same pods with the same port the CNPG-generated `PodMonitor`
would, but as the native kind the repo standardised on. `enablePodMonitor`
stays `false` deliberately: turning it on would create a
`monitoring.coreos.com/v1 PodMonitor` that the VM operator converts into a
second VMPodScrape — the ArgoCD drift the other scrape files avoid, and a
duplicate scrape that would double every `cnpg_*` series (the #1159 failure
shape). Only the comment on that line in `cluster.yaml` changes, pointing at
`vmpodscrape.yaml`; comments are not part of the rendered object, so ArgoCD
sees no diff on the `Cluster` and the operator does nothing. The
`restartedAt` annotation is not touched. Net effect on `platform-db`: one new
object, zero pod changes. NetworkPolicy already admits 9187 from `monitoring`.

### 2. Alerts: `vm-rules/shared-pg-alerts.yaml` + backup rules in `backup-alerts.yaml`

New `VMRule/mctl-shared-pg-alerts` (namespace `monitoring`, labels
`app.kubernetes.io/part-of: mctl-platform`, `app.kubernetes.io/component: shared-pg`),
group `mctl.shared-pg`, `interval: 60s`. All selectors are scoped
`namespace="platform-db", pod=~"shared-pg-[0-9]+"` so that a future second
CNPG cluster does not trip shared-pg alerts. Every rule has labels
`severity`, `service: shared-pg` and a description ending in
`Runbook: https://github.com/mctlhq/mctl-gitops/blob/main/docs/runbooks/shared-pg.md#<anchor>`.

| Alert | Expression (abridged; S = shared-pg selector) | for | severity |
|---|---|---|---|
| SharedPgNoPrimary | `(sum(cnpg_pg_replication_in_recovery{S} == bool 0) or vector(0)) != 1` — zero primaries (incl. nothing scraped) or split brain | 5m | critical |
| SharedPgInstanceMissing | `(count(up{S} == 1) or vector(0)) < 2` — 2 mirrors `spec.instances`; comment says to change both together | 10m | warning |
| SharedPgInstanceDown | `cnpg_collector_up{S} == 0` — exporter up, Postgres not answering | 5m | warning |
| SharedPgReplicationLagHigh | `max by (pod) (cnpg_pg_replication_lag{S}) > 300` (CNPG reports 0 when receive == replay, so idle is quiet) | 10m | warning |
| SharedPgStandbyNotStreaming | `(cnpg_pg_replication_streaming_replicas{S} and on(pod) cnpg_pg_replication_in_recovery{S} == 0) < 1` | 10m | warning |
| SharedPgWALArchivingFailing | `(cnpg_pg_stat_archiver_last_failed_time{S} > cnpg_pg_stat_archiver_last_archived_time{S}) and on(pod) cnpg_pg_replication_in_recovery{S} == 0` | 15m | critical |
| SharedPgWALArchivingStale | `cnpg_pg_stat_archiver_seconds_since_last_archival{S} > 7200 and on(pod) cnpg_pg_replication_in_recovery{S} == 0` (archive_timeout is 15min; Temporal keeps WAL flowing) | 10m | warning |
| SharedPgConnectionsHigh | `sum by (pod) (cnpg_backends_total{S}) / on(pod) max by (pod) (cnpg_pg_settings_setting{S,name="max_connections"}) > 0.8` | 10m | warning |
| SharedPgVolumeFillingUp | `kubelet_volume_stats_used_bytes{namespace="platform-db",persistentvolumeclaim=~"shared-pg-[0-9]+"} / kubelet_volume_stats_capacity_bytes{...} > 0.8` | 15m | warning |
| SharedPgVolumeAlmostFull | same ratio `> 0.9` | 5m | critical |
| SharedPgMetricsAbsent | `absent(cnpg_collector_up{S})` — the scrape itself broke, every rule above is blind | 15m | warning |

Backup rules go into the existing `vm-rules/backup-alerts.yaml`, group
`mctl.backups`, following the file-placement convention there:

| Alert | Expression | for | severity |
|---|---|---|---|
| SharedPgBackupStale | `time() - max(cnpg_collector_last_available_backup_timestamp{S}) > 26 * 3600` (daily at 02:00; a value of 0 = never, which also fires) | 15m | warning |
| SharedPgBackupFailed | `max(cnpg_collector_last_failed_backup_timestamp{S}) > max(cnpg_collector_last_available_backup_timestamp{S})` | 15m | warning |
| SharedPgBackupMetricAbsent | `absent(cnpg_collector_last_available_backup_timestamp{S})` | 1h | warning |

Metric names are those of CNPG 1.25's default monitoring queries
(`cnpg_collector_*`, `cnpg_pg_replication_*`, `cnpg_pg_stat_archiver_*`,
`cnpg_backends_total`, `cnpg_pg_settings_setting`). Task 1 verifies each name
against the live scrape before tasks 2-3 merge; a rule against a non-existent
name is caught by `SharedPgMetricsAbsent` only for the collector, so the check
is not optional.

The upstream `KubePersistentVolumeFillingUp` default rule stays as is; the
shared-pg volume rules fire earlier (80/90% rather than 97% / predicted-full)
and go to Telegram, because a full volume stops every database at once.

### 3. Routing in `monitoring.yaml`

The circularity argument used for `MctlApi.*` applies one layer further down:
mctl-agent files incidents through mctl-api, which stores state in shared-pg.
So, using the established two-part shape:

1. A new route before the severity block:
   `receiver: telegram, continue: true, matchers: [alertname =~ "SharedPg.*"]`
   with a comment citing the circularity.
2. `SharedPg.*` appended to the `alertname !~` exclusion of the
   `severity = "critical"` telegram route, so the critical ones
   (`SharedPgNoPrimary`, `SharedPgWALArchivingFailing`,
   `SharedPgVolumeAlmostFull`) page once, not twice.
3. `SharedPg.*` appended to the mctl-agent catch-all regex, as done for
   `MctlApi.*`, so the agent keeps its ticket.
4. A `CASES` entry in `scripts/check-alertmanager-routes.py`:
   `{alertname: SharedPgNoPrimary, severity: critical}` -> `telegram, mctl-agent`
   (telegram once) and `{alertname: SharedPgReplicationLagHigh, severity: warning}`
   -> `telegram, mctl-agent`. The script's check 3 also covers every new rule
   automatically through its static labels.

### 4. Dashboard

New `infra-components/observability/grafana-dashboards/cnpg-dashboard-configmap.yaml`:
`ConfigMap/cnpg-dashboard` in `monitoring`, label `grafana_dashboard: "1"`,
containing the upstream CloudNativePG dashboard JSON from
`cloudnative-pg/grafana-dashboards` pinned to a commit recorded in the header
comment. Adaptations only: the datasource input is replaced by the
`$datasource` variable pattern the other dashboards use
(`{"type": "prometheus", "uid": "$datasource"}`), and the namespace/cluster
variables default to `platform-db` / `shared-pg`. Panels backed by operator
metrics remain empty (operator scrape is out of scope).

### 5. Runbook

New `docs/runbooks/shared-pg.md` with one section per alert (anchors matching
the annotations): what it means, the first `kubectl cnpg status shared-pg -n platform-db`
/ log checks, and the safe actions (e.g. never delete a PVC; WAL archiving
failure -> check `cnpg-backup-r2` credentials and R2; volume -> raise
`storage.size`, which `hcloud-volumes` expands online; connections -> per-role
`connectionLimit` in `cluster.yaml`). It links to `docs/runbooks/restore.md`
for recovery.

## Alternatives

1. **Flip `enablePodMonitor: true`.** Smallest diff and literally what the
   comment says, but it creates a `monitoring.coreos.com` `PodMonitor` owned by
   the operator that the VM operator converts — the drift every other scrape in
   the repo avoids — and if anyone later adds a native scrape we get #1159's
   doubled series. It also ties scrape settings (interval, relabelling) to the
   CNPG CRD. Dropped.
2. **A `VMServiceScrape` against a Service.** CNPG creates no Service exposing
   9187 (`shared-pg-rw/ro/r` expose 5432 only), so this would need an extra
   headless Service plus endpoints that always follow the pods. A pod scrape
   is the direct fit. Dropped.
3. **Use the upstream CNPG `PrometheusRule` from the cloudnative-pg chart /
   docs verbatim.** Generic rules keyed on `namespace`/`cluster` variables,
   no runbook links, no promtool tests, and routing would still be
   hand-written. Used as a reference for the expressions only.
4. **Put the scrape object under `vm-rules/`** to keep all observability in one
   Application. Explicitly rejected by `scripts/check-vm-rules.sh`'s kind guard.

## Platform impact

- **Database pods:** no change to the `Cluster` spec or `restartedAt`; the
  `shared-pg` Application applies one new `VMPodScrape`. No switchover, no
  restart. Verified in task 1 by comparing pod UIDs / `restartCount` before and
  after sync.
- **Load on Postgres:** the CNPG exporter runs its default queries on each
  scrape; at 30 s against two instances this is negligible, but it does open
  one short-lived local connection per scrape (outside role limits, via the
  instance manager's local socket).
- **VictoriaMetrics:** a few hundred series per instance (`cnpg_backends_total`
  is per datname/usename/state; ~25 roles x ~25 databases worst case). Within
  vmagent's current 500m / 512Mi limits.
- **Alert noise:** the planned 2026-10 style rolls (standby restart then
  switchover) cause a short `in_recovery` transition; `for: 5m`/`10m` keeps
  `SharedPgNoPrimary` and `SharedPgInstanceMissing` quiet through a normal
  switchover (seconds). A planned maintenance still warrants a silence.
- **Backward compatibility:** additive. Existing routes keep their receivers;
  the route checker enforces no double-paging.
- **Risks:** (a) metric names differ in the deployed CNPG version -> rules
  silently never fire. Mitigation: task 1 gate plus `SharedPgMetricsAbsent` /
  `SharedPgBackupMetricAbsent`. (b) Backup timestamp metrics deprecated in
  newer CNPG -> on a future operator upgrade `SharedPgBackupMetricAbsent`
  fires, which is the intended signal to migrate the rule. (c) The hardcoded
  `2` in `SharedPgInstanceMissing` drifts from `spec.instances`; mitigated by
  cross-referencing comments in both files.
