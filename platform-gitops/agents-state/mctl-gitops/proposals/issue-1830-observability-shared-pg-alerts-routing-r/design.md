# Design: issue-1830-observability-shared-pg-alerts-routing-r

## Current state

- **Scrape (done).** `platform-gitops/infra-components/data/cnpg/shared/vmpodscrape.yaml`
  (`VMPodScrape/shared-pg`, selector `cnpg.io/cluster: shared-pg` +
  `cnpg.io/podRole: instance`, port `metrics`, 30s) shipped in #1817. In
  `cluster.yaml`, `enablePodMonitor: false` now has the comment "scraped via
  vmpodscrape.yaml", and `instances: 2` is set at line 21. The cluster has
  `archive_timeout: "15min"`, `max_connections: "200"`, `storage.size: 40Gi`,
  no `walStorage`, and backups with `target: prefer-standby`.
  `scheduled-backup.yaml` runs `shared-pg-daily` at 02:00 UTC.
- **Rules.** `infra-components/observability/vm-rules/*.yaml` holds 21 VMRule
  files, none of which mention `cnpg_` or `SharedPg` (grep). Backup freshness
  rules live in `backup-alerts.yaml`, group `mctl.backups`, `interval: 60s`
  (VaultBackup*, VictoriaMetricsBackup*, ForgejoBackup*, ForgejoRestoreDrill*).
  Their tests are in `vm-rules/tests/backup-alerts_test.yaml`, which documents
  that promtool's clock starts at unix 0, so past timestamps are written as
  negative or small values. Volume rules use `kubelet_volume_stats_*`
  (`forgejo-alerts.yaml:67`). Existing rules link to runbooks without anchors
  (`.../docs/runbooks/restore.md`).
- **CI.** `scripts/check-vm-rules.sh` has a kind guard (VMRule only), extracts
  `.spec` into `tests/generated/`, runs `promtool check rules` and every
  `tests/*_test.yaml`, then runs `scripts/check-alertmanager-routes.py`.
  `--selftest` exercises both checks. The route script renders the bootstrap
  chart, runs `amtool check-config`, tests the fixed `CASES` list (lines 86-162),
  and routes every vm-rules alert by its static labels. It fails if any alert
  pages Telegram twice, or if a critical alert pages it zero times.
- **Routing.** `bootstrap/templates/observability/monitoring.yaml`, lines
  510-946. The tree is an allowlist. The established pattern for alerts whose
  remedy or reporting path depends on mctl-agent or mctl-api is in two parts:
  a `receiver: telegram, continue: true` prefix route (`MctlApi.*` at line 835,
  `PlatformWebEndpoint.*` at line 847), plus the same prefix in the mctl-agent
  catch-all regex (line 934). Under that comes the `severity = "critical"`
  telegram route (line 895), whose `alertname !~` list must exclude every
  alert already paged by an earlier `continue: true` telegram route. The
  matcher-less `receiver: mctl-agent` must stay the last child.
- **Runbooks.** `docs/runbooks/` has no `shared-pg.md`. `restore.md` exists and
  is the recovery reference.
- **Dashboards.** `infra-components/observability/grafana-dashboards/*-configmap.yaml`
  are ConfigMaps in `monitoring` labelled `grafana_dashboard: "1"`, synced by
  the monitoring Application (source path at `monitoring.yaml:1076`, app-level
  `ServerSideApply=true` at line 1171, so a large JSON is not limited by the
  last-applied annotation). Every Prometheus panel uses the datasource variable
  pattern `"uid": "$datasource"` (or `${datasource}` in the patched upstream
  `k8s-views-global`). None of the existing dashboard UIDs is a CNPG one.
- **Live values (#1811 task-1 verification, comment by mashkovd, 2026-10-11 ~19:10Z):**
  current primary `shared-pg-2`, replica `shared-pg-1`.

  | metric | shared-pg-1 (replica) | shared-pg-2 (primary) |
  |---|---|---|
  | `cnpg_collector_up`, `up` | 1 | 1 |
  | `cnpg_pg_replication_in_recovery` | 1 | 0 |
  | `cnpg_pg_replication_lag` | 0 | 0 |
  | `cnpg_pg_replication_streaming_replicas` | **0** | 1 |
  | `cnpg_pg_stat_archiver_seconds_since_last_archival` | **71390, growing** | 506 |
  | `last_archived_time - last_failed_time` | positive | positive |
  | `sum(cnpg_backends_total)` | 1 | 88 |
  | `cnpg_pg_settings_setting{name="max_connections"}` | 200 | 200 |
  | `cnpg_collector_last_available_backup_timestamp` | **0** | 1791684184 |
  | `cnpg_collector_last_failed_backup_timestamp` | 0 | 1787796061 |

  Every metric name that #1811's design uses is present, and the backup
  metrics are populated on the primary, so the kube-state-metrics fallback
  from #1811 is not needed.

Deployed state checked:
- `diff -rq` of the clone against `$MCTL_GITOPS_ROOT` for
  `infra-components/data/cnpg/shared`, `infra-components/observability/vm-rules`,
  `infra-components/observability/grafana-dashboards` and
  `bootstrap/templates/observability/monitoring.yaml` showed the trees are
  identical. The deployed source has `vmpodscrape.yaml` and no SharedPg rule,
  route or dashboard.
- `mctl_list_incidents(service=shared-pg)` returned 0 active incidents. This is
  consistent with no shared-pg alerting existing and says nothing about health.
- `gh issue view 1811 --comments` returned the live metric table above. I did
  not observe VictoriaMetrics or the cluster directly: this run has no cluster
  access, and the mctl MCP tools do not cover `platform-db` infrastructure. So
  the PVC names (`shared-pg-1`, `shared-pg-2`) and the exact label set on the
  `cnpg_*` series (beyond `namespace` and `pod`) were not observed. Both are
  listed under Open questions in requirements.md and gated in task 1's DoD.

## Proposed solution

The design is #1811's tasks 2-6, unchanged except for the replica-safety
corrections and the test fixtures they require. One PR (rules, tests, routing,
runbook, dashboard) works because every part is additive. The dashboard may
ship as a separate PR if its review is slow.

### 1. `vm-rules/shared-pg-alerts.yaml`

`VMRule/mctl-shared-pg-alerts`, namespace `monitoring`, labels
`app.kubernetes.io/part-of: mctl-platform`, `app.kubernetes.io/component: shared-pg`.
Group `mctl.shared-pg`, `interval: 60s`. The header comment explains the
replica caveat and points to the #1811 live check. Here `S` =
`namespace="platform-db", pod=~"shared-pg-[0-9]+"`, and `PRIMARY` =
`on(namespace, pod) cnpg_pg_replication_in_recovery{S} == 0`.

| Alert | Expression | for | sev | Replica-safe because |
|---|---|---|---|---|
| SharedPgNoPrimary | `(sum(cnpg_pg_replication_in_recovery{S} == bool 0) or vector(0)) != 1` | 5m | critical | counts primaries cluster-wide |
| SharedPgInstanceMissing | `(count(up{S} == 1) or vector(0)) < 2` (comment: mirrors `instances: 2`) | 10m | warning | cluster-wide |
| SharedPgInstanceDown | `cnpg_collector_up{S} == 0` | 5m | warning | replica reports 1 |
| SharedPgReplicationLagHigh | `max by (namespace, pod) (cnpg_pg_replication_lag{S}) > 300` | 10m | warning | replica reports real lag (0 healthy) |
| SharedPgStandbyNotStreaming | `cnpg_pg_replication_streaming_replicas{S} < 1 and PRIMARY` | 10m | warning | **replica's 0 is masked by the join** |
| SharedPgWALArchivingFailing | `cnpg_pg_stat_archiver_last_failed_time{S} > cnpg_pg_stat_archiver_last_archived_time{S} and PRIMARY` | 15m | critical | **join** |
| SharedPgWALArchivingStale | `cnpg_pg_stat_archiver_seconds_since_last_archival{S} > 7200 and PRIMARY` | 10m | warning | **join; replica's 71390 is masked** |
| SharedPgConnectionsHigh | `sum by (namespace, pod) (cnpg_backends_total{S}) / on(namespace, pod) max by (namespace, pod) (cnpg_pg_settings_setting{S, name="max_connections"}) > 0.8` | 10m | warning | per-pod ratio, replica 1/200 |
| SharedPgVolumeFillingUp | `kubelet_volume_stats_used_bytes{namespace="platform-db", persistentvolumeclaim=~"shared-pg-[0-9]+"} / kubelet_volume_stats_capacity_bytes{...} > 0.8` | 15m | warning | per-PVC, both meaningful |
| SharedPgVolumeAlmostFull | same ratio `> 0.9` | 5m | critical | same |
| SharedPgMetricsAbsent | `absent(cnpg_collector_up{S})` | 15m | warning | n/a |

Comparison operators bind tighter than `and`, so `a > b and on(...) c == 0`
parses as intended. The implementer still adds parentheses for readability.
The primary join is chosen over `min` across instances (see Alternatives).
During a no-primary window the joined rules return nothing, and
`SharedPgNoPrimary` covers that window. Every rule has `labels: {severity, service: shared-pg}`
and a description ending in
`Runbook: https://github.com/mctlhq/mctl-gitops/blob/main/docs/runbooks/shared-pg.md#<anchor>`,
where `<anchor>` is the lowercased alertname (e.g. `#sharedpgnoprimary`).
`cluster.yaml`'s `instances: 2` gets a cross-reference comment pointing to
SharedPgInstanceMissing. This is a comment-only change and does not alter the
rendered `Cluster`.

All expressions stay inside the PromQL subset, so that promtool (PromQL) and
vmalert (MetricsQL) agree.

### 2. Backup rules in `vm-rules/backup-alerts.yaml`

These go in group `mctl.backups`, after the Forgejo rules. A comment explains
the `max by (namespace)`: the replica reports 0, and the backup is a property
of the cluster, not of a pod.

| Alert | Expression | for | sev |
|---|---|---|---|
| SharedPgBackupStale | `time() - max by (namespace) (cnpg_collector_last_available_backup_timestamp{S}) > 93600` | 15m | warning |
| SharedPgBackupFailed | `max by (namespace) (cnpg_collector_last_failed_backup_timestamp{S}) > max by (namespace) (cnpg_collector_last_available_backup_timestamp{S})` | 15m | warning |
| SharedPgBackupMetricAbsent | `absent(cnpg_collector_last_available_backup_timestamp{S})` | 1h | warning |

`max` is safe in the stale direction too. If every instance reports 0, the
max is 0 and the rule fires. Live, the primary's failed timestamp (2026-08-27)
is older than its available one (2026-10-11), so `SharedPgBackupFailed` is
quiet.

### 3. Unit tests: fixtures that would catch a per-pod rule

- **`vm-rules/tests/shared-pg-alerts_test.yaml` (new).** One shared healthy
  fixture, copied into each healthy test, with both pods carrying the live
  values. The replica `shared-pg-1` has `in_recovery 1`,
  `streaming_replicas 0`, `lag 0`, `collector_up 1`, `up 1`, and
  `seconds_since_last_archival '71390+60x120'` (growing 60s per 1m step).
  Its `last_archived_time` is later than its `last_failed_time`, it has
  backends 1 and `max_connections` 200. The primary `shared-pg-2` has
  `in_recovery 0`, `streaming_replicas 1`, `seconds_since 506` (flat), archived
  later than failed, backends 88 of 200, and volumes at 50%. Every new alert
  gets `exp_alerts: []` at 30m and at 2h. Because the replica's archiver value
  starts at 71390 (well over 7200), a per-pod `SharedPgWALArchivingStale`
  fails this test at the first eval. A per-pod `SharedPgStandbyNotStreaming`
  fails it on the replica's 0.
- **Adversarial replica case.** Same healthy fixture, but the replica's
  `last_failed_time` is later than its `last_archived_time`. The WAL rules
  must stay quiet, which proves they read only the primary.
- **Firing cases**, one per alert, each asserting that nothing fires before
  `for` elapses and that the alert fires after it:
  - NoPrimary, with both pods in recovery, with two primaries, and with no
    series.
  - InstanceMissing (one `up` series), InstanceDown (`collector_up 0`) and
    MetricsAbsent (no collector series).
  - ReplicationLagHigh: replica lag 600.
  - StandbyNotStreaming: primary streaming 0.
  - WALArchivingFailing: primary failed later than archived.
  - WALArchivingStale: primary seconds_since 8000, with the replica also present.
  - ConnectionsHigh: primary 170/200.
  - VolumeFillingUp (85%) and VolumeAlmostFull (95%).
- **`vm-rules/tests/backup-alerts_test.yaml` (extended).** promtool time
  starts at 0, so a replica value of 0 only looks stale after 26h of test
  time. The healthy SharedPg backup test therefore uses `interval: 10m` and
  evaluates at `27h15m`. The primary `last_available` is `90000` constant (a
  backup taken at 25h test-time) and `last_failed` is `3600`. The replica has
  `last_available 0` and `last_failed 0`. At 27h15m, `time() - max` = 8100 and
  the alert is quiet, while a per-pod rule would have seen the replica's 0
  exceed 93600 from 26h and fired by 26h15m. Firing cases:
  - Primary `-10000`, which is stale at 27h.
  - Both pods 0, which is stale at 27h, so "timestamp 0 fires".
  - Primary failed later than available, which fires SharedPgBackupFailed.
  - No series, which leaves SharedPgBackupMetricAbsent not firing at 50m and
    firing at 75m.

### 4. Routing in `monitoring.yaml`

A new route goes after the `PlatformWebEndpoint.*` route (line 847) and before
the `ArgoLocalWorkdir...` route and the severity block:

```yaml
                  # shared-pg (vm-rules/shared-pg-alerts.yaml + SharedPgBackup*
                  # in backup-alerts.yaml, #1811/#1830): the same circularity as
                  # MctlApi.* one layer further down — mctl-api, through which
                  # mctl-agent files its incidents, keeps its state in shared-pg,
                  # so an agent-only route reports a database outage to a
                  # component that needs that database. Two-part shape:
                  # continue: true here, AND SharedPg.* in the mctl-agent
                  # catch-all below, AND SharedPg.* in the critical route's
                  # exclusion (NoPrimary, WALArchivingFailing, VolumeAlmostFull
                  # are critical and would otherwise page twice).
                  - receiver: telegram
                    continue: true
                    matchers:
                      - alertname =~ "SharedPg.*"
```

Then:
- Append `|SharedPg.*` to the `alertname !~` matcher of the `severity = "critical"`
  route (line 899), and add "shared-pg" to the list in its explanatory comment.
- Append `|SharedPg.*` to the mctl-agent catch-all regex (line 934).

The resulting path for a critical SharedPg alert is the SharedPg route
(telegram, continue), then a skip of the critical route (excluded), then the
catch-all (mctl-agent, stop). That gives `telegram, mctl-agent`. A warning
alert takes the same path. No earlier stopping route matches `SharedPg.*`.

New `CASES` in `scripts/check-alertmanager-routes.py`, placed after the
`MctlApiDown` case:
- `("critical shared-pg alert pages once and keeps its ticket", {"alertname": "SharedPgNoPrimary", "severity": "critical"}, ["telegram", "mctl-agent"])`
- `("warning shared-pg alert pages", {"alertname": "SharedPgReplicationLagHigh", "severity": "warning"}, ["telegram", "mctl-agent"])`
- `("shared-pg backup alert pages", {"alertname": "SharedPgBackupStale", "severity": "warning"}, ["telegram", "mctl-agent"])`

Check 3 in the script also routes every new rule through its static labels, so
it catches any double page. The selftest's `drop_dedupe` mutation then also
produces SharedPg double pages, which strengthens it at no cost.

### 5. `docs/runbooks/shared-pg.md`

The runbook opens with an intro covering the topology (2 instances, primary
plus hot standby, `prefer-standby` backups to R2), which databases depend on
shared-pg, and safety rules. The safety rules are:
- Never delete a PVC or pod by hand to "fix" a role.
- A planned roll goes through the `restartedAt` annotation.
- Silence `alertname=~"SharedPg.*"` during planned maintenance.

Then comes one `## <AlertName>` heading per alert (14 headings), each covering
meaning, the first checks, and safe actions. The first checks are:
- `kubectl -n platform-db get cluster shared-pg -o yaml` status fields,
  `kubectl cnpg status shared-pg -n platform-db` if the plugin is installed,
  pod logs in Loki, and the VM query behind the rule.

The safe actions are:
- WAL / backup alerts: check the `cnpg-backup-r2` credentials and R2
  reachability.
- Volume alerts: raise `storage.size` in `cluster.yaml`, which `hcloud-volumes`
  expands online.
- Connections: check the per-role `connectionLimit` in `cluster.yaml`.
- Recovery: link to `restore.md`.

A "Why some rules read only the primary" section records the replica caveat,
so that a future editor does not "simplify" the joins away.

### 6. CNPG dashboard

New file `infra-components/observability/grafana-dashboards/cnpg-dashboard-configmap.yaml`
contains `ConfigMap/mctl-cnpg-dashboard` in `monitoring`, labelled
`grafana_dashboard: "1"`, with key `cnpg.json` holding the upstream
`cloudnative-pg/grafana-dashboards` cluster dashboard JSON. The header records
the upstream repo, file path, commit SHA and the list of local edits. The
edits are deliberately minimal:
- Replace the `DS_PROMETHEUS` input with a `datasource` template variable
  (type `datasource`, query `prometheus`), and point panels at `"$datasource"`.
- Drop `__inputs` and `__requires`.
- Default the `namespace` and `cluster` variables to `platform-db` /
  `shared-pg`.
- Keep the upstream `uid` unless it clashes. It does not clash with the UIDs
  present today.

Panels that need operator metrics may stay empty, as noted in the header.

## Alternatives

1. **`min` across instances for the WAL rules.** This is allowed by the issue
   and needs no join. It was dropped because after a switchover the old
   primary's `seconds_since_last_archival` is small for a while and would mask
   a stale new primary for up to the 2h threshold. It also does not generalise
   to `last_failed > last_archived`. The join reads exactly the instance that
   archives.
2. **Per-pod rules with a `pod="shared-pg-2"` filter.** This is simplest, but
   CNPG moves the primary on every switchover (`primaryUpdateMethod: switchover`),
   so the filter would be wrong after the next roll. Dropped.
3. **Recording rules for "primary pod" (`shared_pg:primary:info`).** A cleaner
   join target, but it adds a recording rule plus its own absence semantics,
   and only three rules use it. The inline join is enough and is testable
   directly. Dropped for now.
4. **Upstream CNPG `PrometheusRule` verbatim.** It has generic labels, no
   runbook links and no tests, and it predates the replica-aware patterns
   needed here. Used as a reference only (same as #1811).

## Platform impact

- **Database:** none. No change to `Cluster/shared-pg` beyond one comment line
  (comments are not rendered, so ArgoCD sees no diff). No pod roll and no
  switchover.
- **VictoriaMetrics / vmalert:** 14 additional rules at 60s over a few dozen
  series. This is negligible.
- **Grafana:** one more ConfigMap. Its size (upstream JSON, about 100-250 KB)
  is under the 1 MiB ConfigMap limit, and the app uses ServerSideApply.
- **Alert volume:** on the healthy cluster all 14 rules are inactive (asserted
  in tests and checked live). Planned rolls cause a primary change that lasts
  seconds, which `for: 5m/10m` absorbs. Planned maintenance warrants a silence.
- **Backward compatibility:** additive. Existing routes are unchanged except
  that two regexes are extended, and the route checker enforces no double
  paging.
- **Risks and mitigations:**
  - A label mismatch in the `on(namespace, pod)` join (for example `pod`
    missing on one series) makes a rule silently never fire. Mitigation: the
    firing tests use the same label set as the live series. The implementer
    confirms the label set in vmsingle before merging, and the T6 live check
    queries each joined expression and expects one primary series.
  - Wrong PVC names silence the volume rules. Mitigation: confirm with a live
    query (task 1 DoD).
  - The in-tree backup metrics are deprecated upstream. On an operator upgrade
    that removes them, `SharedPgBackupMetricAbsent` fires, which is the
    intended prompt to migrate.
