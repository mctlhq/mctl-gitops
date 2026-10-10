# Tracing bake-off sandbox — operator runbook (issue #903 / #1280)

**This runbook is the procedure `mctlhq/mctl-gitops#1280` executes.**
`mctlhq/mctl-gitops#1355` landed the offline half (a `ResourceQuota` /
`LimitRange`, a pinned candidate catalogue, a collector exporter fan-out
derived from the enabled candidates, a redaction regression test and a
CI-enforced teardown window). The pull request that adds this revision opens
the sandbox for **one candidate, Grafana Tempo**, and is the live half's
first step.

Every control below is named by its exact key under `otelCollector.eval` in
`platform-gitops/bootstrap/values.yaml`.

## 0. Scope of this round (owner decision, 2026-10-10)

- **One candidate: Tempo.** Monolithic (single binary), one replica, the
  community chart `tempo` `2.4.0` from
  `https://grafana-community.github.io/helm-charts` (appVersion `2.10.8`,
  checked against that repository's `index.yaml` on 2026-10-10). Langfuse,
  SigNoz, Phoenix and Traceway are **not deployed** in this round; their
  rubric cells stay null. See the ADR's "Bake-off scope amendment" for what
  that means for the verdict.
- **No new nodes.** Tempo fits into the three existing cx43 workers (see
  "Capacity" below).
- **Storage: object storage, not a volume.** Blocks go to the Cloudflare R2
  bucket `tempo-traces` through a bucket-scoped token; the WAL lives on a
  2Gi `emptyDir`. The namespace quota allows **zero** PVCs.
- **Synthetic first, real producers later.** The collector fan-out to Tempo
  is on as merged, but no workload emits OTLP spans to the collector today
  (verified 2026-10-10: no `otelcol_receiver_*` series in VictoriaMetrics
  over 30 days, no pod with an `OTEL_*ENDPOINT` env, no base-service release
  with `otel.enabled`). Until a producer is instrumented, the only spans
  that reach Tempo are the ones an operator submits through the
  `otel-trace-fixture` workflow. Instrumenting a real producer is a
  separate change and a separate gate (step 4).
- **What this round does not decide.** A permanent tracing backend, and
  turning tracing on across production workloads, are each a separate owner
  gate after the ADR's verdict. Nothing in this sandbox is permanent.

## 1. What is deployed

| Piece | Where |
|---|---|
| Namespace, quota, limits, base NetworkPolicies | `bootstrap/templates/observability/eval-namespace.yaml` (rendered while `otelCollector.eval.enabled`) |
| Tempo Application (chart + raw manifests) | `bootstrap/templates/observability/eval-candidates.yaml`, entry `tempo` in `otelCollector.eval.candidates` |
| Object-storage credentials | `infra-components/observability/eval/tempo/externalsecret.yaml` — ExternalSecret `tempo-r2` from Vault KV `platform/r2-tempo` through the `vault-backend` ClusterSecretStore |
| Tempo-specific NetworkPolicies | `infra-components/observability/eval/tempo/networkpolicy.yaml` — Grafana/vmagent to `:3200`, egress `:443` to Cloudflare's published IPv4 ranges |
| Scrape | `infra-components/observability/eval/tempo/servicescrape.yaml` — VMServiceScrape, `job="tempo"`; the chart's ServiceMonitor is off |
| Collector fan-out | exporter `otlp/eval-tempo` → `tempo.observability-eval.svc.cluster.local:4317`, next to `debug` |
| Grafana datasource | `bootstrap/templates/observability/tempo-datasource.yaml` — "Tempo (eval)", uid `tempo-eval` |
| Alerts | `infra-components/observability/vm-rules/tempo-eval-alerts.yaml` (unit tests in `vm-rules/tests/`), routed to Telegram only by the `TempoEval.*` route in `monitoring.yaml` |

Tempo reads its bucket, endpoint and keys from the `tempo-r2` Secret as
environment variables (`-config.expand-env=true`); the values file carries
only `${TEMPO_S3_*}` placeholders, and
`tests/test_otel_collector_backends_render.py` fails if a literal appears
there.

Settings that matter for the measurement:

- retention `336h` (14 days) through the compactor's `block_retention`;
- `ingester.max_block_duration: 5m`, so a block reaches the bucket within
  minutes of the spans in it, which bounds what a pod loss can take;
- memory limit `1Gi`, request `512Mi`, `GOMEMLIMIT=800MiB`, and the chart's
  default 1GiB memory ballast turned off (it would count as live heap
  against `GOMEMLIMIT`);
- CPU request `100m`, limit `1`.

## 2. Capacity

Measured read-only on 2026-10-10 (`kubectl describe nodes`, and
VictoriaMetrics for actual use: current value and the 7-day maximum for
memory, current and 7-day p95 for CPU). Allocatable per worker: 7700m CPU,
about 14.66GiB memory. The control-plane node is tainted `NoSchedule` and
is not a candidate.

| Node | Requests CPU / mem now | Limits CPU / mem now | Memory used now / 7d max | CPU used now / 7d p95 |
|---|---|---|---|---|
| ftx | 3255m (42%) / 8902Mi (59%) | 18200m / 17238Mi (114%) | 6.07 / 7.02 GiB | 1.25 / 1.35 cores |
| hnn | 2865m (37%) / 8359Mi (55%) | 16400m / 16960Mi (112%) | 6.63 / 7.92 GiB | 3.01 / 2.72 cores |
| xgf | 3110m (40%) / 8995Mi (59%) | 18200m / 20256Mi (134%) | 5.77 / 10.73 GiB | 1.30 / 1.66 cores |

Tempo adds **100m / 512Mi** of requests and **1 CPU / 1Gi** of limits to
whichever worker it lands on: at most +1.3 points of CPU requests and +3.5
points of memory requests on any of the three, and about +7 points of memory
limits (limits are already overcommitted on every worker, as before).
Expected actual use at the declared synthetic volume is roughly 200–400MiB
and well under 0.1 core. The WAL `emptyDir` is capped at 2Gi of node disk;
each worker has about 116–122GiB free.

The namespace quota is sized for this one pod plus headroom for a rollout:
`requests.cpu: "1"`, `requests.memory: "1536Mi"`, `limits.cpu: "2"`,
`limits.memory: "2Gi"`, `pods: "4"`, `persistentvolumeclaims: "0"`,
`requests.storage: "0"`.

## 3. Preconditions (before merging the PR that opens the sandbox)

- **Credentials exist.** Vault KV `secret/platform/r2-tempo` has the four
  properties `access-key`, `secret-key`, `endpoint` and `bucket`, and the
  token behind them is scoped to the `tempo-traces` bucket. The
  `external-secrets` Vault role already reads `secret/data/platform/*`, so
  no Vault policy change is needed.
- **The bucket exists** with its 30-day lifecycle rule. That rule is the
  backstop; Tempo's own 14-day retention is the primary bound.
- **The rubric is still frozen.** `python3 tests/test_adr_rubric_frozen.py`
  passes. If it fails, something scored a cell before the soak was
  declared — stop.
- **GenAI usage counters survive redaction.**
  `tests/test_otel_collector_redaction_e2e.py` passes (#1332).

## 4. Rollout — gated, in this order

1. **Merge.** The PR sets `otelCollector.eval.enabled: true`,
   `teardownAfter` at most 14 days out (`scripts/validate-eval-teardown-date.py`
   enforces it in CI), and the `tempo` candidate `enabled: true`.
2. **Argo CD sync.** The bootstrap Application renders the namespace and the
   `otel-eval-tempo` Application; the ExternalSecret syncs first
   (`sync-wave: -1`). Check:

   ```bash
   kubectl -n observability-eval get externalsecret tempo-r2      # SecretSynced=True
   kubectl -n observability-eval get pods                         # tempo-0 Running, Ready
   kubectl -n observability-eval get resourcequota observability-eval-quota
   ```

   The collector rolls with the new exporter. Until Tempo is Ready the
   exporter retries and `TempoEvalCollectorExportFailures` may fire once;
   that is expected during this step only.
3. **Synthetic span proof — collector → Tempo → Grafana.** Submit the
   fixture workflow once and follow the spans end to end:

   ```bash
   argo submit -n argo-workflows --from clusterworkflowtemplate/otel-trace-fixture
   ```

   - In VictoriaMetrics: `otelcol_exporter_sent_spans{exporter="otlp/eval-tempo"}`
     increases and `otelcol_exporter_send_failed_spans{exporter="otlp/eval-tempo"}`
     does not.
   - In Grafana → Explore → "Tempo (eval)": search for the fixture's
     service names and open one trace; the parent/child tree must be
     complete.
   - Within about 10 minutes, `tempo_ingester_blocks_flushed_total` (job
     `tempo`) is above zero and `tempo_ingester_failed_flushes_total` is
     flat: blocks reached the bucket.
   - Record the timestamp of this proof on #1280. It is the start of the
     soak window (step 5).
4. **Real producers — later, separately.** No producer is instrumented
   today. Pointing a real workload at the collector (`mctlhq/mctl-agent#38`,
   `mctlhq/mctl-agents#195`, or `otel.enabled` on a base-service release)
   is its own change with its own review, and must be recorded on #1280 as
   an amendment to the declared volume **before** it lands, never after.

## 5. Declare the soak — before any measurement

The declaration lives in the ADR ("Bake-off scope amendment") and is fixed
before the first measurement:

- **Window:** from the synthetic proof in step 4.3 until 2026-10-23 23:59
  UTC, one day before the `teardownAfter` date.
- **Volume:** synthetic only. The `otel-trace-fixture` workflow with its
  default parameters (10 executions of `devloop-trace.json`, 2 traces and 24
  spans each, so about 240 spans per submission), submitted once for the
  proof and then at most once a day — under 5,000 spans for the whole
  window. Real producer traffic: none.

A soak whose length or volume is chosen after looking at the data is not a
measurement. A change to either is a recorded amendment with a reason,
never a silent extension.

## 6. Measurement sources, per rubric cell

| Dimension | Weight | Source |
|---|---|---|
| `trace_reconstruction` | 25 | "Tempo (eval)" in Grafana against the fixture traces submitted through `otel-trace-fixture` — parent/child tree, async/queue/Temporal/Argo visibility, search, error navigation. |
| `ai_agent_observability` | 25 | `gen_ai.usage.*` counters on the fixture spans and what Grafana's Tempo views can group by (model/tool/session). If the redaction e2e check fails, record a `0`-with-reason cell. |
| `data_ownership_portability` | 20 | Tempo's licence (recorded in `docs/adr/0001-rubric.yaml`'s `stage_a`), plus a live check that the blocks in the bucket are readable Parquet and that OTLP ingestion needed no producer-side change. |
| `operations` | 15 | `otelcol_exporter_*{exporter="otlp/eval-tempo"}` and the `tempo_*` / `tempodb_*` series (job `tempo`) in VictoriaMetrics; the `TempoEval*` alerts that fired; `container_memory_rss` against the 1Gi limit; the quota's `status.used`. |
| `security_privacy` | 10 | `tests/test_otel_collector_redaction.py` (what is redacted before Tempo ever sees it) plus a look at what Tempo stores for the poisoned fixture `devloop-trace-redaction.json`. |
| `evals_quality_loop` | 5 | Whether a score can be attached to an execution. Tempo has no native mechanism; record that with evidence rather than leaving the cell blank. |

Only Tempo's column is filled in this round.

## 7. Accepted risks (bake-off only)

These are accepted **for the bake-off only**. A permanent deployment would
have to revisit each of them.

- **WAL loss on pod deletion or reschedule.** The WAL is on an `emptyDir`.
  It survives a container restart (including an OOM kill) and is replayed,
  but a pod deletion, eviction or move to another node discards it, and
  with it every span not yet flushed to the bucket — at most the last block
  window (about five minutes) plus anything still queued for upload.
- **An object-storage outage longer than the WAL can hold loses spans.**
  While R2 is unreachable, completed blocks wait in the 2Gi `emptyDir` and
  are retried. If the outage lasts until the `emptyDir` reaches its size
  limit, the kubelet evicts the pod and the WAL is lost. At the declared
  synthetic volume this takes far longer than any plausible outage, but it
  is not impossible. `TempoEvalFlushFailures` and
  `TempoEvalObjectStorageErrors` fire long before that point.
- **One replica.** Any Tempo restart is a short ingest gap; the collector
  retries and then drops (`TempoEvalCollectorDroppedSpans`). This is part of
  what the operations dimension measures, not something to hide.
- **Retention is not observable inside the window.** Tempo deletes blocks
  older than 14 days, and the sandbox closes at most 14 days after it
  opens, so the compactor's retention pass is unlikely to delete anything
  before teardown. The bucket's 30-day lifecycle rule bounds storage either
  way.
- **The Grafana datasource outlives teardown.** Grafana keeps a provisioned
  datasource in its database after the ConfigMap disappears; teardown
  removes it explicitly (step 9).

## 8. Score and promote

Fill Tempo's null cells in `docs/adr/0001-rubric.yaml`, apply
`decision_rule`, pick exactly one of the seven `permitted_verdicts`, and
write the ADR's Decision section. `tests/test_adr_rubric_frozen.py` stops
enforcing the freeze once scores are non-null — that is expected.

## 9. Teardown — one commit, then the bucket

Do **not** revert the PR that opened the sandbox: reverting templates while
Argo CD still holds the live candidate Application orphans it. In **one
commit**:

1. `otelCollector.eval.enabled: false`.
2. `otelCollector.eval.candidates[].enabled: false` for `tempo`.
3. `otelCollector.eval.teardownAfter: ""`.
4. If Tempo is **not** the selected backend, also delete
   `infra-components/observability/vm-rules/tempo-eval-alerts.yaml`, its
   test file, and the `TempoEval.*` route in
   `bootstrap/templates/observability/monitoring.yaml`. (The rules are
   silent with the sandbox gone, so leaving them for a follow-up is safe,
   but they should not outlive the decision.)

Because the bootstrap Application syncs with `prune: true` and the candidate
Application carries `resources-finalizer.argocd.argoproj.io` and
`syncPolicy.automated.prune: true`, this one commit cascades: the Tempo
Application and its workload, Secret, NetworkPolicies and VMServiceScrape go
first, then the quota, the limits, the base NetworkPolicies and the
`observability-eval` Namespace. The collector's `otlp/eval-tempo` exporter
and the datasource ConfigMap disappear from the render in the same commit.

Then, outside git:

- **Remove the "Tempo (eval)" datasource from Grafana** (Connections → Data
  sources, or `DELETE /api/datasources/uid/tempo-eval`).
- **If Tempo is not selected, empty the `tempo-traces` bucket** (and revoke
  its token and the Vault entry once nothing reads it). Waiting for the
  30-day lifecycle rule is acceptable only if the owner says so on #1280.
- If Tempo **is** selected, its permanent home (namespace, storage,
  retention, replicas, real producers) is a new change under a separate
  owner gate; nothing in this sandbox is promoted in place.

## 10. Verify nothing is left running

```bash
kubectl get ns observability-eval                      # expect: NotFound
kubectl -n argocd get applications | grep otel-eval    # expect: no output

# The collector's traces pipeline back to debug only
helm template test platform-gitops/bootstrap -f platform-gitops/bootstrap/values.yaml \
  | grep -c 'otlp/eval-'                               # expect: 0

# No Tempo (eval) datasource left in the render
helm template test platform-gitops/bootstrap -f platform-gitops/bootstrap/values.yaml \
  | grep -c 'tempo-eval-grafana-datasource'            # expect: 0
```

Plus, by hand: Grafana lists no "Tempo (eval)" datasource, and (if Tempo was
not selected) the `tempo-traces` bucket is empty. Do not consider the spike
closed until every check is clean.
