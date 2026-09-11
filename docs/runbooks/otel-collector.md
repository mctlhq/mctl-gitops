# otel-collector — traces gateway (phase 1)

**otel-collector accepts OTLP traces cluster-wide and exports them nowhere
useful yet.** It is a gateway-mode OpenTelemetry Collector Deployment in
`monitoring`, deployed 2026-09 (issue #902) ahead of the two producers that
will actually emit spans (`mctlhq/mctl-agent#38`, `mctlhq/mctl-agents#195`).
Today it enriches, redacts and logs every span it receives to its own stdout
(collected by the existing promtail -> Loki pipeline); it does not yet send
anything to a trace backend, because no backend has been chosen. Swapping one
in is a single values edit, covered below.

Source: `platform-gitops/bootstrap/templates/observability/otel-collector.yaml`
(the Application, chart values, and collector config) plus
`platform-gitops/infra-components/observability/otel-collector/` (NetworkPolicy,
VMServiceScrape) and `platform-gitops/infra-components/observability/vm-rules/otel-collector-alerts.yaml`
(alerts).

## Endpoints

**Send traces to `otel-collector.monitoring.svc.cluster.local`, in-cluster
only.** There is no Ingress, no NodePort, and no Traefik route — 4317/4318 are
not reachable from outside the cluster, by design (this is a platform-internal
pipeline, same trust tier as VMSingle and Loki).

| Protocol  | Port | Path            |
|-----------|------|-----------------|
| OTLP gRPC | 4317 | n/a             |
| OTLP HTTP | 4318 | `/v1/traces`    |
| Metrics   | 8888 | `/metrics` (scraped by the VMServiceScrape below, not by a producer) |
| Health    | 13133| `/` (liveness/readiness only, not producer-facing) |

`base-service` has an optional, **default-off** block for services on this
chart:

```yaml
otel:
  enabled: false   # set true to opt in
  endpoint: http://otel-collector.monitoring.svc.cluster.local:4318
```

Setting `otel.enabled: true` on a service's `values.yaml` renders
`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`,
`OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES` into that Deployment's
container env, alongside whatever `env:` the service already sets (`env:`
wins on conflict — override any of the four explicitly if needed). No service
has opted in as of this writing; every `platform-gitops/services/*/*/values.yaml`
renders byte-identical to before this change until one does.

The endpoint is a chart default rather than a per-service `env:` string
written by automation on purpose:
`platform-gitops/services/labs/mctl-telegram/values.yaml` documents that
`mctl_deploy_service`'s yq rewrite has been observed stripping colon-bearing
`env` values, which is exactly the shape of an OTLP URL.

## Namespace identity: `mctl.team` / `mctl.component`

The `k8s_attributes` processor (chart name `k8sattributes`; the chart rewrites
it — see "Chart quirks" below) reads pod labels `mctl.ai/team` and
`mctl.ai/component` and attaches them to every span as `mctl.team` /
`mctl.component`. This is the **same pair promtail already relabels** for logs
(`bootstrap/templates/observability/loki.yaml:203-217`), so a trace and a log
line from the same pod carry matching tenant identity with no mapping table.
A pod with neither label simply gets neither span attribute — nothing fails.

It also attaches `k8s.namespace.name`, `k8s.pod.name`, `k8s.node.name` and
`k8s.deployment.name` from the Kubernetes API (RBAC: get/list/watch on pods,
namespaces, replicasets — no secrets, no write verbs).

`k8s.cluster.name` (`otelCollector.clusterName`, currently `mctl-preprod`) and
`deployment.environment` (`otelCollector.environment`, currently `preprod`) in
`platform-gitops/bootstrap/values.yaml` are added with **`action: insert`, not
`upsert`** — if a producer already set either attribute, the producer's value
survives. Do not change this to `upsert`; it would silently overwrite
execution-specific values that #38/#195 are expected to set.

## Redaction — what's blocked and how to extend it

The `redaction` processor runs with `allow_all_keys: true` plus two block
lists, so a span attribute is dropped/masked only if it (or its value) matches
something below — everything else passes through unchanged.

**`blocked_key_patterns`** (attribute *names*, case-insensitive where noted):

- `(?i).*(authorization|cookie|api[-_]?key|token|secret|password|credential).*`
- `(?i)^vault\..*`
- `(?i)^gen_ai\.(prompt|completion).*`
- `(?i).*\.messages$`
- `(?i)^mcp\.tool\.(arguments|result)$`
- `^db\.statement$`
- `^http\.(request|response)\.header\..*`

**`blocked_values`** (credential *shapes*, catches a secret sitting under an
innocuous key name): `ghp_[A-Za-z0-9]{36}`, `gh[pousr]_[A-Za-z0-9]{20,}`,
`sk-[A-Za-z0-9]{20,}`, `hvs\.[A-Za-z0-9]{20,}`,
`eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.`.

**When #38 / #195 land and add new attributes**, check each new attribute
name against `blocked_key_patterns` above. If it carries anything sensitive
(a new kind of credential, a raw prompt/completion field, tool arguments) and
none of the existing patterns cover it, add a pattern — this is a config-only
change to the `helm.values` block in `otel-collector.yaml`, no image rebuild.
Prefer a pattern over adding one more exact key: the whole point of key
*patterns* rather than an exact key list is that the two issues above have not
shipped yet, so nobody has invented the next sensitive attribute name yet
either.

`summary` is deliberately left unset on the `redaction` processor, so the
collector does not itself log which keys it redacted (that log line would
become a new place secrets could leak).

## Opting a service in

Set `otel.enabled: true` in the service's `values.yaml`. The chart then renders
`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`,
`OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES`; anything the service
already sets under `env` wins and the default is not rendered at all, so the
list never carries a duplicate name.

This works the same on both workload kinds. `base-service` renders a Deployment
or -- when `blueGreen.enabled` is true -- a Rollout, never both, and the two
templates share one `base-service.env` partial precisely so the opt-in cannot
work on one path and silently do nothing on the other.
`tests/test_base_service_otel_env.py` renders both and compares them.

## Volume control

`filter/health` drops server spans whose `url.path` or `http.target` is
`/healthz` or `/readyz` — the two paths every `base-service` deployment probes
(`helm-charts/base-service/values.yaml:136-143`). This is pure noise
reduction; it costs nothing and removes the single largest source of
uninteresting spans once producers are live.

## Batching, retry and the queue — what each setting buys

- **`memory_limiter`** (`limit_percentage: 75`, `spike_limit_percentage: 20`,
  `check_interval: 1s`) runs first in the pipeline. Past the soft limit the
  receiver returns a retryable error instead of the pod being OOM-killed —
  this is backpressure, not data loss prevention. `OtelCollectorRefusedSpans`
  fires when it engages.
- **`batch`** (`send_batch_size: 512`, `send_batch_max_size: 1024`,
  `timeout: 5s`) runs last, after redaction — batches are formed from spans
  that have already been through every check above.
- **`otlp/backend`'s `sending_queue`** (`num_consumers: 4`, `queue_size: 5000`)
  and **`retry_on_failure`** (`initial_interval: 5s`, `max_interval: 30s`,
  `max_elapsed_time: 300s`) only exist once `otelCollector.backendEndpoint` is
  set — see below. They absorb a transient backend outage; once the queue
  fills, new batches are **dropped**, not blocked, so a stuck backend cannot
  back-pressure the receiver. `OtelCollectorQueueNearFull` and
  `OtelCollectorExportFailures` watch this.

## Swapping the backend (one key, no code change)

1. Edit `otelCollector.backendEndpoint` in
   `platform-gitops/bootstrap/values.yaml` to the new OTLP endpoint (a plain
   values edit — goes through the normal PR + `validate-manifests.yml` +
   `claude-review.yml` path like any other template/values change in this
   repo).
2. Merge and let ArgoCD sync `otel-collector` (automated, `selfHeal: true`).
3. The `otlp/backend` exporter and its queue/retry settings appear in the
   traces pipeline automatically; the `debug` exporter stays enabled
   alongside it, so both continue to be a source of truth while confirming
   the new backend receives spans.
4. No producer restarts, no image rebuild, no change in `mctl-agent` or
   `mctl-agents` — producers only ever address
   `otel-collector.monitoring.svc.cluster.local`.

Setting it back to `""` is the cheapest rollback: the collector keeps running
with just the `debug` exporter and nothing downstream is written. See the
proposal's `tasks.md` "Rollback" section for the two deeper levels (remove the
NetworkPolicy; full `git revert`).

## Verification commands

```bash
# Application health
kubectl -n argocd get application otel-collector

# Replica count and RBAC (expect 2/2 Ready; ClusterRole has no secrets/write verbs)
kubectl -n monitoring get deploy otel-collector
kubectl get clusterrole otel-collector -o yaml

# Send a trace from inside the cluster (any pod in an allowed namespace --
# see NetworkPolicy below), then check the counter increased:
#   otelcol_receiver_accepted_spans (gRPC and HTTP both land here)
#   otelcol_receiver_refused_spans  (memory_limiter backpressure)
#   otelcol_exporter_send_failed_spans / otelcol_exporter_queue_size /
#     otelcol_exporter_queue_capacity (once a backend is configured)
# Query these in Grafana against the vmagent-scraped otel-collector job.

# Confirm the scrape pool has exactly one target (no double-scrape, #1159):
#   count by (pod) (otelcol_receiver_accepted_spans)  -- expect one series per pod

# Confirm redaction and enrichment on a real span: with the debug exporter
# enabled, read otel-collector's own stdout via Loki
#   {namespace="monitoring"} | filtered to the otel-collector pod
# and check k8s.namespace.name / k8s.pod.name / k8s.deployment.name /
# k8s.node.name / mctl.team / mctl.component / k8s.cluster.name /
# deployment.environment are present, and that authorization/cookie/token/
# etc. attributes are absent or masked.
```

## NetworkPolicy

`allow-otel-collector-ingress` in `monitoring` allows 4317/4318 from
namespaces `admins`, `mctl-api`, `argo-workflows`, `temporal`, `monitoring`,
and any namespace labelled `mctl.me/tenant` — everything else is refused. The
`podSelector` matches the collector's own pods only, never `{}`: `monitoring`
carries **no namespace-wide NetworkPolicy today**
(`infra-components/observability/blackbox/blackbox-exporter.yaml:19-26`), and
a `podSelector: {}` policy here would silently turn the whole namespace into
an allowlist, cutting off Grafana, VMSingle, vmagent and Loki. If a
NetworkPolicy change here ever needs debugging, check those four are still
Healthy first.

## Accepted residuals

- **No trace backend selected.** The `debug` exporter (stdout -> Loki) is the
  only sink until `otelCollector.backendEndpoint` is set. This is phase 1 by
  design — the pipeline is provable without committing to a vendor first.
- **No sampling.** Every span that reaches the collector is exported (or
  dropped only by `filter/health` or the memory limiter). Revisit if span
  volume from #38/#195 makes this expensive once a real backend is billed by
  volume.
- **In-memory queue, lost on restart.** `sending_queue` has no persistent
  storage backing it; a collector restart while the queue is non-empty drops
  whatever was queued. Acceptable for phase 1 given there is no backend yet to
  lose anything from.
- **No mTLS on the receiver.** OTLP gRPC/HTTP accept plaintext from anything
  the NetworkPolicy above allows. Consistent with the rest of `monitoring`
  (Grafana, VMSingle, Loki all rely on network-level trust, not per-connection
  auth).
- **`monitoring` still has no namespace-wide NetworkPolicy.** This proposal
  adds one policy scoped to the collector's own pods; it does not close that
  wider gap for the rest of the namespace.
