# Tempo — permanent trace backend

Owner decision on #1280 (2026-10-22): **ADOPT TEMPO / mctl-native only**
(ADR 0001), deployed as a separate permanent deployment, not the bake-off
sandbox promoted in place. Plan: `docs/plans/tempo-adoption.md`. The
sandbox runbook (`tracing-bake-off.md`) is history.

## 1. Known limitation — partial reads (read this first)

In the soak, fetching all 139 traces by id with a bounded time range
returned **5,092 spans against 6,930** received in the window (ADR 0001,
Decision). The ingest counters agree to the span, so this is a read-path
completeness limit, not loss — but it is **unexplained**.

Until it is explained:

- Do not promise complete trace or span enumeration from Tempo, in docs,
  dashboards, reports or agent output.
- Do not use Tempo for completeness-critical counts (spans per run, "every
  step of run X", SLO ratios). Count ingest with the collector
  (`otelcol_exporter_sent_spans_total{exporter="otlp/backend"}`) or Tempo's
  `tempo_distributor_spans_received_total` instead.
- Reading a trace to understand what happened is fine; a missing span in a
  fetched trace is not evidence the step did not run.

The owner accepted deployment with this limitation; it blocks claims and
uses, not the deployment. Lift this section only with the explanation
recorded on a linked issue.

## 2. What is deployed

| Piece | Where |
|---|---|
| Namespace `tracing` | `bootstrap/templates/observability/tracing.yaml` |
| Application `tracing-tempo` (chart `tempo` 2.4.0, Tempo 2.10.8) | same file; values `tracing.tempo` in `bootstrap/values.yaml` |
| NetworkPolicies, ResourceQuota, LimitRange, ExternalSecret, VMServiceScrape | `infra-components/observability/tracing/tempo/` (the Application's manifestsPath) |
| Collector exporter `otlp/backend` → `tempo.tracing.svc.cluster.local:4317` (plaintext, `backendInsecure`) | `otelCollector.backendEndpoint` |
| Grafana datasource "Tempo", uid `tempo`; Loki `trace_id` link → `tempo` | `tempo-datasource.yaml`, `loki-datasource.yaml` |
| Alerts `Tempo*` → Telegram route | `vm-rules/tempo-alerts.yaml` |

Producers: the three DevLoop workers (`mctl-agents-worker`, `-exec`,
`-implement`) and `admins-mctl-agent`, each with `otel.enabled: true`.
Nothing else exports traces; adding a producer is its own change.

Storage: blocks in the R2 bucket `tempo-traces` (reused from the soak, its
token from Vault `platform/r2-tempo` via ExternalSecret `tempo-r2`),
retention 336 h. Compaction applies the retention; the bucket's 30-day
lifecycle rule is only a backstop.

Why root-app renders only the Namespace and the Application: a root-app
sync that adds `tracing` to project `default` and creates the first
namespaced resource there loops (gitops#1925). Keep namespaced resources in
the manifestsPath.

## 3. Standing accepted risk — WAL on emptyDir

The WAL is an `emptyDir` (2 Gi): `tracing-quota` refuses PVCs because the
default StorageClass is a billed Hetzner volume. A pod restart or
rescheduling loses the spans not yet flushed — at most about one
`max_block_duration` (5 m) of traces. The owner explicitly accepted this as a
standing risk on 2026-10-22. `TempoFlushFailures` and `TempoRestarting`
are the signals that it is being realised.

## 4. Read-path bounds

An unranged trace-by-id over the full window held the soak pod at its CPU
limit with no end. So:

- `query_frontend.api_timeout: 1m`, `max_outstanding_per_tenant: 100`
  (429 past that), `trace_by_id.concurrent_shards: 4`,
  `querier.max_concurrent_queries: 4`;
- always pass `start`/`end` to `/api/traces/<id>`; search is limited to
  168 h per query;
- limits 2 CPU / 2 Gi, `GOMEMLIMIT=1600MiB`. `TempoMemoryNearLimit` means
  resize in `bootstrap/values.yaml`, not restart.

## 5. Alerts

| Alert | Meaning / first check |
|---|---|
| `TempoNotScraped` | VMServiceScrape or NetworkPolicy broken; nothing else can fire |
| `TempoMemoryNearLimit`, `TempoOOMKilled`, `TempoRestarting` | sizing or a heavy reader (§4) |
| `TempoIngestRefused`, `TempoDiscardedSpans` | Tempo rejecting writes; check limits and pod logs |
| `TempoCollectorExportFailures`, `TempoCollectorDroppedSpans` | collector cannot reach Tempo; producers are unaffected |
| `TempoFlushFailures`, `TempoObjectStorageErrors` | R2 writes failing (token, egress policy); WAL risk §3 grows |
| `TempoCompactionOrRetentionErrors` | retention not being applied; bucket grows |

## 6. Verify

```bash
export KUBECONFIG=~/.kube/mctl-preview-config.yaml
kubectl -n argocd get application tracing-tempo   # Synced / Healthy
kubectl -n tracing get pods,externalsecret        # tempo-0 Running, tempo-r2 Ready
```

Grafana lists "Tempo" (uid `tempo`) and no "Tempo (eval)". After the
leftover is gone, the `deleteDatasources` entry in `tempo-datasource.yaml`
can be dropped.

## 7. Rollback

Set `otelCollector.backendEndpoint: ""` first (producers keep exporting to
the collector, which then keeps traces in `debug` only), then
`tracing.enabled: false`. The Application's finalizer prunes the workload;
the bucket is untouched; with no compactor running, only its 30-day
lifecycle rule ages it out.
