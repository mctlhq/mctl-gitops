# Design: issue-2245-spike-would-victorialogs-beat-the-curren

## Current state

**Log backend.** `platform-gitops/bootstrap/templates/observability/loki.yaml`
defines the ArgoCD Application `loki-stack` (namespace `monitoring`, chart
`loki-stack` 2.10.2 from `grafana.github.io/helm-charts`):

- Loki image pinned to `grafana/loki:2.9.17`, a single pod (single binary),
  `persistence.enabled: false`; `/data` is emptyDir.
- Resources: requests 100m / 1Gi, limits 200m / 2048Mi (comment: 7d peak
  working set 704Mi, steady CPU ~16m).
- Storage: `schema_config` tsdb + s3, schema v12, 24h index period; chunks and
  index in R2 bucket `loki` (credentials via `loki-minio-credentials`, from
  `infra-components/observability/secrets/loki-minio-externalsecret.yaml`).
  The bucket has a 60-day backstop lifecycle rule set in the dashboard.
- Limits: `ingestion_rate_mb: 4`, burst 8, `retention_period: 336h`, and a
  `retention_stream` keeping `{namespace="vault", container="vault"}` 720h
  (Vault audit log, SOC 2 #1659); `max_look_back_period: 720h`.
- Compactor enforces retention; `ingester.wal.flush_on_shutdown: true`
  because the WAL is on emptyDir.
- `auth_enabled` is not set in the values (chart default applies).

**Collector.** The same Application runs Promtail as a DaemonSet (requests
50m / 160Mi, limits 150m / 256Mi, three workers). One client:
`http://loki-stack:3100/loki/api/v1/push`. Its `snippets.pipelineStages`
carry `cri: {}` plus metrics stages producing counters
(`seerrsense_*`, `lifecycle_shadow_*`, `lifecycle_claim_abandoned_total`,
`vault_audit_entries_total`, `vault_audit_failures_total`) scraped by
`promtail-podscrape.yaml` (VMPodScrape, prefix `promtail_custom_` stripped)
and used by `infra-components/observability/vm-rules/*.yaml`. These counters
are produced by Promtail, not by Loki, so they are independent of the
storage backend. Labels: chart defaults plus `team` (from
`mctl.ai/team`) and `component` via `extraRelabelConfigs`.

**Consumers of Loki.**
- mctl-api: `LOKI_URL: "http://loki-stack.monitoring.svc.cluster.local:3100"`
  in `bootstrap/templates/mctl-platform/mctl-api.yaml` (backs
  `mctl_get_service_logs`; LogQL).
- Grafana: `bootstrap/templates/observability/loki-datasource.yaml`
  (uid `P8E80F9AEF21F6940`, `derivedFields` `trace_id=` -> Tempo).
- `wft-create-tenant.yaml` / `wft-delete-tenant-safe.yaml` name `loki-stack`
  in their protected-Application lists.

**Metrics stack.** `monitoring.yaml` deploys `victoria-metrics-k8s-stack`
0.72.5 (VMSingle, vmagent with `selectAllByDefault`), so VictoriaMetrics
operator CRDs (VMServiceScrape, VMPodScrape, VMRule) already exist and every
resource figure in this spike can come from series already collected
(`container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`,
kubelet volume stats).

**Precedent.** The trace-backend spike: `docs/adr/0001-agent-execution-trace-backend.md`
and frozen `docs/adr/0001-rubric.yaml` (enforced by
`tests/test_adr_rubric_frozen.py`), sandbox `observability-eval`
(`bootstrap/templates/observability/eval-namespace.yaml`,
`eval-candidates.yaml`, gated by `otelCollector.eval.enabled`), teardown guard
`scripts/validate-eval-teardown-date.py` (14-day window, run in
`.github/workflows/validate-manifests.yml`), procedure
`docs/runbooks/tracing-bake-off.md` (closed 2026-10-22, Tempo adopted).
That sandbox's NetworkPolicies and candidate shape are trace/OTLP-specific
and keyed under `otelCollector`, so it is not reusable as-is for logs.

**Cluster.** `infrastructure/k3s-preview/kube.tf`: cluster `mctl-preprod`,
one cx33 control plane, three cx43 workers.

**Related.** `agents-state/mctl-gitops/proposals/issue-2211-.../requirements.md`
(proposed): OTTL pilot on the traces pipeline; notes that logs go
Promtail -> Loki and do not pass through the collector. This spike does not
touch the collector.

Deployed state checked:
- `mctl_list_services(team=admins)`: complete=true, 8 catalogue services
  (mctl-web, mctl-docs, mctl-support, umami, mctl-agents-worker*, mctl-design).
  mctl-api and loki-stack are bootstrap Applications, not tenant services, so
  they are not listed here; their config was read from the clone only.
- `mctl_get_service_logs(admins, mctl-web, 1h)`: 3 lines returned, labels
  `app, container, filename, instance, job, namespace, node_name, pod,
  stream`, no `team` label on that stream. This confirms Loki is live and
  serving mctl-api queries, and that tenant scoping in practice is the
  `namespace` label.
- `mctl_get_service_logs(admins, mctl-api, 15m)`: count 0 (mctl-api does not
  run in `admins` under that app name; not evidence of anything about
  mctl-api).
- `mctl_list_tenants`: refused, requires admin. Tenant list taken from
  `$MCTL_GITOPS_ROOT/tenants/`: admins, commerce-proof, erpact, karabu, labs,
  mctl, namax66.
- Not observed: actual Loki ingestion rate, R2 `loki` bucket size, Loki and
  Promtail live resource usage, live `auth_enabled` value. No read-only tool
  in this run exposes them; they are the live round's first measurements.

## Proposed solution

Two halves, as with #903/#1280. **This proposal's implementer delivers only
the offline half**; the live round is a separate owner-gated change that flips
one flag and follows the runbook.

### Offline half (this change)

1. **ADR and frozen rubric.** `docs/adr/0002-log-backend.md` (Status:
   Proposed) states the question, the issue's boundary, candidates
   (`loki-current` = the running loki-stack, `victorialogs` = single-node),
   the decision rule and a weight table. `docs/adr/0002-rubric.yaml` holds
   the same dimensions with every score null. Proposed weights (sum 100):

   | key | dimension | weight |
   |---|---|---|
   | ingest_resources | CPU/memory of backend + shipper at the same ingest rate | 15 |
   | storage_cost | bytes stored per ingested GB, cost per retained month (R2 vs PVC) | 15 |
   | query_latency | p50/p95 of a fixed query set (see below) at 1h/24h/7d ranges | 15 |
   | retention | 14d default + 30d Vault audit stream expressible and enforced | 10 |
   | tenant_isolation | per-tenant scoping available and how mctl-api would enforce it | 10 |
   | ha_recovery | behaviour on pod kill and node drain; data loss window; restore path | 15 |
   | consumer_compat | mctl-api LogQL, Grafana datasource, derived fields, alerting | 10 |
   | migration_cost | engineering + dual-run effort, query rewrite (LogQL -> LogsQL) | 10 |

   Decision rule: recommend a change only if VictoriaLogs' weighted score
   exceeds Loki's by at least 0.5 (on a 1-5 cell scale), **no** dimension is
   "not measured", and retention plus consumer_compat are each >= 3. Anything
   else is "keep Loki" with the evidence recorded. This encodes the issue's
   "not from ingestion numbers alone".

2. **Frozen-rubric test.** `tests/test_adr0002_rubric_frozen.py`, modelled on
   `tests/test_adr_rubric_frozen.py`: scores null until the ADR records a
   verdict; weights in YAML equal the ADR table; once scored, each cell is a
   cited score or a cited "not measured".

3. **Gated sandbox templates**, all wrapped in
   `{{- if .Values.logsEval.enabled }}`:
   - `bootstrap/templates/observability/logs-eval-namespace.yaml`: namespace
     `logs-eval` with `mctl.ai/teardown-after`, ResourceQuota (e.g. 500m/1Gi
     requests, 1 CPU/2Gi limits, at most 1 PVC, total 20Gi), LimitRange,
     default-deny, allow-intra-namespace, ingress from `monitoring` pods
     `app.kubernetes.io/name: promtail` (push port), vmagent (metrics),
     Grafana (query); no egress beyond DNS.
   - `bootstrap/templates/observability/logs-eval-candidate.yaml`: one
     Application `logs-eval-victorialogs` from `logsEval.candidate`
     ({enabled, repoURL, chart, targetRevision, values}); rendered only when
     both flags are on. selfHeal off so an operator can scale it to 0 for the
     outage test (same reasoning as `eval-candidates.yaml`). Retention set to
     14d in values.
   - `infra-components/observability/logs-eval/servicescrape.yaml`
     (VMServiceScrape) synced by that Application as a second source, the
     chart's own ServiceMonitor disabled (double-scrape lesson, #1159).
   - A Grafana datasource ConfigMap `victorialogs-eval` (plugin type to be
     verified in the live round) rendered only while the sandbox is open.
   - **Dual-write** in `loki.yaml`: `promtail.config.clients` becomes the
     existing Loki client followed, only when `logsEval.enabled`, by a second
     client pointing at VictoriaLogs' Loki-compatible push endpoint with
     bounded `backoff_config` (small `max_retries`, short `max_period`) and
     `external_labels: {}`. With the flag off the rendered list is exactly
     today's single entry. Using Promtail as the single shipper means both
     backends see an identical stream and shipper cost is counted once; the
     shipper's marginal cost of the second client is itself measured.

4. **Values.** A new top-level `logsEval:` block in
   `platform-gitops/bootstrap/values.yaml` with `enabled: false`,
   `teardownAfter: ""`, quota numbers and `candidate` with empty pins and
   `enabled: false`, comments pointing at ADR 0002.

5. **Teardown guard.** Generalise `scripts/validate-eval-teardown-date.py` to
   check a list of (enabled-path, teardown-path) pairs, adding
   `logsEval.enabled` / `logsEval.teardownAfter`, with selftest cases for the
   new key. No new CI job needed; it already runs in `validate-manifests.yml`.

6. **Runbook.** `docs/runbooks/log-backend-bake-off.md`: procedure for the
   live round (below), capacity check, kill switch, teardown.

### Live round (separate, owner-gated; specified here, not implemented)

- Fill the candidate pins from upstream `index.yaml` (date recorded), set
  `logsEval.enabled: true`, `teardownAfter` <= 14 days.
- Soak at least 7 days of real dual-written traffic (includes weekly
  mctl-agents runs and Argo bursts).
- Measure from VictoriaMetrics: CPU/memory of Loki pod vs VictoriaLogs pod,
  Promtail delta, bytes ingested (`promtail_sent_bytes_total` per client
  host), Loki R2 bytes added over the window vs VictoriaLogs PVC
  `kubelet_volume_stats_used_bytes`, monetised at R2 vs Hetzner volume price.
- Query set (scripted, run against both, p50/p95 over N runs): the exact
  query mctl-api issues for `mctl_get_service_logs`; a `{namespace="labs"}`
  substring search over 24h; a `trace_id=<hex>` lookup over 7d; a Vault
  audit range read over 7d; a count-over-time per namespace over 24h.
- Retention: confirm whether a 30d Vault audit stream and 14d default can
  coexist in one VictoriaLogs instance; if not, score the workaround cost.
- Tenant isolation: document Loki's live `auth_enabled` and how mctl-api
  scopes by namespace today vs what VictoriaLogs tenancy would offer.
- HA/recovery: kill the VictoriaLogs pod and drain its node mid-ingest;
  compare lost-line counts and recovery time with Loki's documented
  emptyDir-WAL + `flush_on_shutdown` behaviour; note that Loki's data
  survives node loss in R2 while a single-node VictoriaLogs on a PVC does
  not without a backup path.
- Fill the rubric, record the verdict, close the sandbox.

## Alternatives

- **Reuse the existing `observability-eval` sandbox and `otelCollector.eval`
  keys.** Dropped: the namespace, NetworkPolicies (OTLP ports, collector
  egress) and candidate fields (`otlpEndpoint`) are trace-specific and the
  ADR 0001 round is closed; overloading them would couple two unrelated
  decisions and their teardown windows.
- **Synthetic load (vendor benchmark harness or a log generator) instead of
  dual-writing real traffic.** Dropped as the primary method: the issue
  requires the current MCTL workload. A replay can be added only for a
  burst-capacity check, scored separately.
- **Separate shipper for VictoriaLogs (vlagent/Vector DaemonSet).** Dropped:
  a second DaemonSet on three workers adds node cost and a different
  collection path, so differences could come from the shipper, not the
  backend. Kept as a note if the bounded Promtail second client proves to
  back-pressure Loki delivery.
- **Desk study from published benchmarks.** Dropped: explicitly ruled out by
  the issue's boundary.

## Platform impact

- **Default render unchanged.** With `logsEval.enabled: false` no new
  objects render and Promtail's config is byte-identical; a render-diff test
  (T3) proves it.
- **Resources while open.** One VictoriaLogs pod capped by the quota
  (<= 1 CPU / 2Gi limits) and one PVC <= 20Gi, on the existing three cx43
  workers; runbook requires a headroom check from VictoriaMetrics before
  opening. Promtail's second client adds CPU/memory per node, measured.
- **Risk: candidate outage back-pressures Promtail and delays Loki,
  including the Vault audit log.** Mitigation: bounded retries on the
  candidate client, Loki client first, an alert on Loki ingestion rate
  dropping while the sandbox is open, and the kill switch (flip
  `logsEval.enabled` false; ArgoCD prunes and Promtail returns to one
  client).
- **Risk: sandbox becomes permanent.** Mitigation: teardown guard turns main
  red after the date.
- **Risk: log data copied to a second store.** VictoriaLogs holds the same
  data as Loki, including Vault audit (HMAC'd) lines, inside the cluster on
  a namespace with default-deny; PVC deleted at teardown. Noted in the ADR
  for the SOC 2 record.
- **No migration** in this proposal; mctl-api, Grafana and VMRules keep
  pointing at Loki.
