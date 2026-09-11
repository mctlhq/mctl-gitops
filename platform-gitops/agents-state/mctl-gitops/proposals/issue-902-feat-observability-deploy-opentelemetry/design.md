# Design: issue-902-feat-observability-deploy-opentelemetry

## Current state

### How observability is deployed

Everything under `platform-gitops/bootstrap/templates/**` is a template of a
single Helm chart (`platform-gitops/bootstrap/Chart.yaml`, name `mctl-apps`)
that ArgoCD renders via `root-app`
(`platform-gitops/bootstrap/templates/bootstrap/root-app.yaml:39-45`,
`path: platform-gitops/bootstrap`, `valueFiles: [values.yaml]`). Dropping a new
YAML file into `bootstrap/templates/observability/` is therefore sufficient to
create a new ArgoCD Application — there is nothing to register anywhere else.
Shared values come from `platform-gitops/bootstrap/values.yaml`
(`spec.source.repoURL`, `spec.source.targetRevision: main`,
`spec.destination.server`, `alertmanager.telegramChatId`).

The separate `applicationset-apps.yaml` in the same tree is a git-directory
generator over `platform-gitops/services/*/*` and only produces **tenant
service** Applications from the `base-service` chart
(`platform-gitops/bootstrap/templates/bootstrap/applicationset-apps.yaml:12-20`,
`:36-51`). It is not involved in infra components.

### The three existing signal paths

- **Metrics.** `monitoring.yaml` installs `victoria-metrics-k8s-stack` 0.72.5
  into namespace `monitoring` (`:11-13`, `:753`). `vmagent` is enabled with
  `selectAllByDefault: true` and remote-writes to
  `http://vmsingle-monitoring-victoria-metrics-k8s-stack.monitoring.svc.cluster.local:8428/api/v1/write`
  (`:278-288`). `VMSingle` retains 28 days on a 25Gi PVC (`:35`, `:60`).
  `vmalert` and `alertmanager` are enabled inline (`:301`, `:410-671`); the
  AlertManager route drops alerts carrying `mctl_agent_self: "true"` so the
  `mctl-agent` webhook receiver does not open tickets against mctl's own
  components (documented at
  `infra-components/observability/vm-rules/mctl-agents-worker-alerts.yaml:22-25`).
- **Logs.** `loki.yaml` installs `loki-stack` 2.10.2 into `monitoring`
  (`:11-13`, `:228`), pinning `grafana/loki:2.9.17` on R2 object storage with
  14-day retention (`:23-25`, `:71-81`). `promtail` rides along as a subchart
  (`:96-97`) and relabels `mctl.ai/team` -> `team` and `mctl.ai/component` ->
  `component` on every pod (`:203-217`).
- **Traces.** Nothing. A repo-wide grep for `opentelemetry|otlp|otel|4317|4318|
  tempo|jaeger|traceway` returns no hits in `platform-gitops/`,
  `infrastructure/`, `docs/`, `scripts/`, `cli/` or `tests/`.
  `ROADMAP.md:149` lists "OpenTelemetry/tracing" as deliberately deferred until
  multi-hop incidents appear.

### How observability side-objects are delivered

`monitoring.yaml` is a **multi-source** Application: source 1 is the upstream
chart with inline `helm.values`, sources 2-6 are git paths in this repo
(`:690-713`) pointing at `infra-components/observability/{grafana-dashboards,
secrets,vm-rules,pushgateway,blackbox}`. A new directory under
`infra-components/` is **not** auto-discovered; it must be named as a `source`
of some Application.

Conventions that constrain any new component here:

- `infra-components/observability/vm-rules/` accepts **only** `kind: VMRule`.
  `scripts/check-vm-rules.sh:85-91` fails the build with
  `non-VMRule object (kind=...) found under vm-rules/` — added after a stray
  `VMPodScrape` there double-scraped the pushgateway (#1159).
- Scrape objects are hand-written `VMServiceScrape`/`VMPodScrape` living beside
  their component, and there must be exactly one per target. The header of
  `infra-components/observability/pushgateway/servicescrape.yaml:1-28` documents
  both failure modes: a selector matching labels the Service does not carry, and
  a port *name* that does not resolve; plus the rule "if this pool ever selects
  zero targets again, fix the Service, do not add a second scrape."
- Grafana picks up dashboards from ConfigMaps labelled `grafana_dashboard: "1"`
  and datasources from ConfigMaps labelled `grafana_datasource: "1"` via its
  k8s-sidecar (`monitoring.yaml:376-399`, example
  `bootstrap/templates/observability/loki-datasource.yaml:1-8`).
- Every infra Application uses `project: default`. The `platform` AppProject
  would reject this outright: its `sourceRepos`
  (`bootstrap/templates/projects/project-platform.yaml:9-14`) lists only this
  repo, `mctl-api` and the Temporal chart repo, and its
  `clusterResourceWhitelist` (`:20-26`) permits only Namespace, ClusterRole and
  ClusterRoleBinding.

### Network posture

- Tenant namespaces are default-deny both directions
  (`helm-charts/tenant/templates/networkpolicy.yaml:16-28`).
  `allow-cluster-egress` (`:63-116`) permits `10.0.0.0/8` minus the node subnets,
  so a ClusterIP in `monitoring` is already reachable from tenant pods whenever
  `tenant.networking.allowClusterEgress` is on. `allow-ingress-from-monitoring`
  (`:223-235`) is the reverse direction, for scraping.
- Preview namespaces use a tighter, name-based egress allowlist
  (`helm-charts/tenant/templates/preview.yaml:204-266`) which **already
  includes `monitoring`** (`:255`).
- `argo-workflows` has an ingress allowlist only
  (`platform-gitops/argo-workflows/config/networkpolicy.yaml:12-21`); its egress
  is unrestricted, so workflow pods can reach `monitoring` today.
- The `monitoring` namespace itself has **no NetworkPolicy at all**, stated
  explicitly at
  `infra-components/observability/blackbox/blackbox-exporter.yaml:19-26`.
- `bootstrap/templates/system/admission-policies.yaml:80-105` is a
  `ValidatingAdmissionPolicy` that restricts NetworkPolicy **names** inside
  tenant namespaces to a fixed nine-entry allowlist. Any new policy in a tenant
  namespace would require editing that list.

### Validation

`.github/workflows/validate-manifests.yml` runs on PR and on push to `main`:
`helm lint` on internal charts and on `bootstrap` (`:55-61`), `helm template` +
`kubeconform -strict` on the bootstrap and argocd charts (`:84-92`),
`scripts/check-vm-rules.sh --selftest` then the real promtool
`check rules` + `test rules` pass (`:187-196`), and a `kubeconform -strict`
sweep over `find platform-gitops/tenants platform-gitops/argo-workflows
platform-gitops/mcp platform-gitops/infra-components` (`:198-219`).
`yamllint.yml` covers all of `platform-gitops/**` with key-duplicates at error.

Consequence: a new file under `bootstrap/templates/observability/` and a new
directory under `infra-components/observability/` are both validated
automatically — but the `infra-components` sweep is `-strict` against the
datreeio CRD catalog, so a custom resource with no published schema fails CI.

## Proposed solution

Deploy a single **gateway-mode OpenTelemetry Collector Deployment** in the
existing `monitoring` namespace, as a new ArgoCD Application rendered by the
bootstrap chart, with config supplied inline as Helm values — the same shape
`monitoring.yaml` and `loki.yaml` already use.

### 1. New Application

`platform-gitops/bootstrap/templates/observability/otel-collector.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: otel-collector
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  sources:
    - repoURL: https://open-telemetry.github.io/opentelemetry-helm-charts
      chart: opentelemetry-collector
      targetRevision: "<exact pinned version>"
      helm:
        values: |
          ...
    - repoURL: {{ .Values.spec.source.repoURL }}
      targetRevision: {{ .Values.spec.source.targetRevision }}
      path: platform-gitops/infra-components/observability/otel-collector
  destination:
    server: {{ .Values.spec.destination.server }}
    namespace: monitoring
  syncPolicy:
    automated: { prune: true, selfHeal: true }
    syncOptions:
      - CreateNamespace=true
      - ApplyOutOfSyncOnly=true
    retry:
      limit: 5
      backoff: { duration: 5s, factor: 2, maxDuration: 3m }
```

The sync shape is copied from `loki.yaml:229-241` (the minimal set), **not**
from `monitoring.yaml:754-786`. `monitoring.yaml`'s
`ServerSideApply` + `RespectIgnoreDifferences` + `ServerSideDiff=false`
combination exists for VictoriaMetrics operator CRDs with incomplete schemas
(`:763-778`); the OTel chart renders only core resources, so inheriting that
combination would import a documented hazard for nothing. In particular no
`ignoreDifferences` block is added, which avoids the array-indexing jq trap
described at `monitoring.yaml:741-748` (#789 / argo-cd#17694).

Chart version is pinned to an exact release, matching every other chart in the
repo (`argo-rollouts` 2.39.0, `external-secrets` 0.10.7, `vault` 0.28.1,
`loki-stack` 2.10.2, `victoria-metrics-k8s-stack` 0.72.5).

### 2. Collector shape

- `mode: deployment`, `replicaCount: 2`, `fullnameOverride: otel-collector` so
  the DNS name is the short, stable
  `otel-collector.monitoring.svc.cluster.local`.
- Image is the **contrib** distribution
  (`otel/opentelemetry-collector-contrib`, command `otelcol-contrib`). This is
  not optional: `k8sattributes`, `redaction` and the OTTL `filter` processor
  are all contrib-only components and the core distribution would fail to start
  with `unknown type` on every one of them.
- `service.type: ClusterIP`, no `ingress`, ports `otlp` 4317 and `otlp-http`
  4318 only, plus a named `metrics` port 8888. `presets.kubernetesAttributes:
  true` so the chart renders the ClusterRole/ClusterRoleBinding the
  `k8sattributes` processor needs (get/list/watch on pods, namespaces,
  replicasets — no secrets).
- Explicit resources: requests `100m` / `192Mi`, limits `500m` / `512Mi` per
  replica. Two replicas so a rolling config change never blackholes the
  endpoint; total added footprint is ~200m / 384Mi requests, small against the
  1400Mi `VMSingle` already requests in the same namespace. `monitoring` is a
  platform namespace and carries no ResourceQuota (those are rendered per-tenant
  by `helm-charts/tenant/templates/resourcequota.yaml`), so nothing needs
  raising.

### 3. Pipeline (traces only)

Receivers: `otlp` with `protocols.grpc` on `0.0.0.0:4317` and `protocols.http`
on `0.0.0.0:4318`, CORS left unconfigured (no browser clients).

Processors, in this order — order is load-bearing:

1. **`memory_limiter`** first. `check_interval: 1s`, `limit_percentage: 75`,
   `spike_limit_percentage: 20`. This is the backpressure mechanism: past the
   soft limit the receiver returns a retryable error instead of the pod being
   OOM-killed. It must precede everything so the refusal happens before work is
   spent on a batch.
2. **`k8sattributes`**. Extracts `k8s.namespace.name`, `k8s.pod.name`,
   `k8s.node.name`, `k8s.deployment.name`, and pod labels `mctl.ai/team` ->
   `mctl.team` and `mctl.ai/component` -> `mctl.component`. Those two labels are
   chosen because they are the same pair promtail already relabels
   (`loki.yaml:203-217`), so a trace and a log line for the same pod carry
   matching tenant identity and can be correlated without a mapping table.
3. **`resource`** with `action: insert` (never `upsert`) for
   `k8s.cluster.name` and `deployment.environment`. Insert semantics are what
   satisfy the issue's "preserve execution-specific attributes rather than
   rewriting them destructively": if `mctl-agents#195` already set a value, the
   producer wins.
4. **`redaction`**. `allow_all_keys: true` with `blocked_key_patterns` covering
   `(?i).*(authorization|cookie|api[-_]?key|token|secret|password|credential).*`,
   `(?i)^vault\..*`, `(?i)^gen_ai\.(prompt|completion).*`,
   `(?i).*\.messages$`, `(?i)^mcp\.tool\.(arguments|result)$`,
   `^db\.statement$`, `^http\.(request|response)\.header\..*`; plus
   `blocked_values` regexes for credential *shapes* that can appear under an
   innocuous key (`ghp_[A-Za-z0-9]{36}`, `gh[pousr]_[A-Za-z0-9]{20,}`,
   `sk-[A-Za-z0-9]{20,}`, `hvs\.[A-Za-z0-9]{20,}`,
   `eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.`). `summary: debug` is left off
   so the collector does not itself record which keys it redacted.
   Key patterns rather than an exact key list is the deliberate choice: #38 and
   #195 have not been written yet, so the block list must catch attribute names
   nobody has invented yet.
5. **`filter/health`** (OTTL) dropping server spans whose
   `url.path`/`http.target` is `/healthz` or `/readyz` — the two paths every
   `base-service` deployment probes (`helm-charts/base-service/values.yaml:136`).
   Pure volume control; costs nothing and removes the single largest source of
   uninteresting spans.
6. **`batch`** last. `send_batch_size: 512`, `send_batch_max_size: 1024`,
   `timeout: 5s`.

Exporters:

- **`debug`** (`verbosity: normal`), always enabled in phase 1. Its stdout is
  already collected by the existing promtail -> Loki pipeline, so "resource
  enrichment is visible in an exported test trace" and "a redaction test
  demonstrates sensitive attributes are removed" are both verifiable in Grafana
  **without** choosing a backend first. This is the mechanism that lets phase 1
  ship a complete, provable pipeline while backend selection stays a separate
  decision.
- **`otlp/backend`**, endpoint supplied from a single bootstrap values key
  (`otelCollector.backendEndpoint`, empty by default). When empty the exporter
  is simply not listed in the traces pipeline, so the collector never tries to
  reach a non-existent host. `sending_queue: {enabled: true, num_consumers: 4,
  queue_size: 5000}` and `retry_on_failure: {enabled: true, initial_interval:
  5s, max_interval: 30s, max_elapsed_time: 300s}` absorb transient backend
  outages; queue-full drops the batch rather than stalling the receiver.

Extensions: `health_check` on `:13133`, wired to the container's liveness and
readiness probes. `pprof` and `zpages` stay off — extra listening surface for
no operational need. `service.telemetry.metrics` on `:8888`.

### 4. Side objects — `infra-components/observability/otel-collector/`

A new directory, referenced as source 2 of the new Application (it cannot go
under `vm-rules/`, which `check-vm-rules.sh:85-91` restricts to `VMRule`):

- `networkpolicy.yaml` — `allow-otel-collector-ingress` in `monitoring`, using
  the allowlist pattern from `bootstrap/templates/core-infra/vault-netpol.yaml:9-20`
  ("selecting all pods with `policyTypes: [Ingress]` makes this an allowlist:
  any source not named below is denied"). Critical difference: the `podSelector`
  matches **the collector's pods only**, not `{}`. A `podSelector: {}` policy
  here would silently turn the whole no-policy `monitoring` namespace into an
  allowlist and cut off Grafana, VMSingle and Loki. Sources allowed: the
  namespaces `admins`, `mctl-api`, `argo-workflows`, `temporal`, `monitoring`,
  plus any namespace labelled `mctl.me/tenant`. Ports 4317 and 4318 only;
  `:8888` and `:13133` are covered by the `monitoring` entry (vmagent scrapes
  from within the namespace) and the kubelet probe path, which NetworkPolicy
  does not gate.
- `servicescrape.yaml` — a `VMServiceScrape` selecting the collector Service by
  label on the **named** port `metrics`, following
  `pushgateway/servicescrape.yaml` and its two documented failure modes. The
  chart's own `serviceMonitor`/`podMonitor` presets are explicitly **disabled**
  in values: `vmagent` runs `selectAllByDefault: true`
  (`monitoring.yaml:287`), so a chart-rendered ServiceMonitor would be picked
  up too and every collector metric would land as two series — the exact #1159
  double-scrape failure.

An alert file `infra-components/observability/vm-rules/otel-collector-alerts.yaml`
(a real `VMRule`, so it does belong in `vm-rules/`) plus its promtool unit test
`vm-rules/tests/otel-collector-alerts_test.yaml`. Alerts:
`OtelCollectorDown`, `OtelCollectorRefusedSpans`
(`otelcol_receiver_refused_spans` — memory limiter backpressure),
`OtelCollectorExportFailures` (`otelcol_exporter_send_failed_spans`),
`OtelCollectorQueueNearFull`
(`otelcol_exporter_queue_size / otelcol_exporter_queue_capacity > 0.8`). Every
rule carries `severity: warning` and `mctl_agent_self: "true"` so the
AlertManager route does not open tickets against mctl's own collector.

### 5. Producer-facing contract

The endpoints are documented, not injected. `base-service` has no global
defaults layer — `applicationset-apps.yaml:45-51` feeds exactly one values file
per service and `deployment.yaml:119-136` renders `env` straight from
`.Values.env`. Rather than change the ApplicationSet (which would affect every
tenant at once), the chart gains an optional, **default-off** block:

```yaml
otel:
  enabled: false
  endpoint: http://otel-collector.monitoring.svc.cluster.local:4318
```

which, when enabled, renders `OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_SERVICE_NAME` and
`OTEL_RESOURCE_ATTRIBUTES` alongside the existing env, with `.Values.env`
winning on conflict. No `services/*/*/values.yaml` is flipped on here. Note
`services/labs/mctl-telegram/values.yaml:52-56` warns that `mctl_deploy_service`'s
yq rewrite has been observed stripping colon-bearing env values, which is
exactly the shape of an OTLP URL — another reason the endpoint is a chart
default rather than a per-service `env` string written by automation.

Finally, `docs/runbooks/otel-collector.md`, in the house style of the existing
runbooks (conclusion-first, bolded rules, dated measured claims, explicit
residuals): the endpoints, the redaction block list and how to extend it, the
batching/retry settings and what they buy, the one-key backend-swap procedure,
verification commands, and the accepted residual that there is no backend yet.

## Alternatives

**A. OpenTelemetry Operator plus `OpenTelemetryCollector` custom resources.**
Dropped. It installs CRDs and a permanently-running controller, and this repo
has an explicit, written preference against that: the admission-control decision
at `bootstrap/templates/system/admission-policies.yaml:7-10` chose a native
`ValidatingAdmissionPolicy` over Kyverno precisely because it "adds no runtime
component to operate, upgrade, or fail closed on." Concretely, the operator's
`OpenTelemetryCollector` CRD has no entry in the datreeio catalog that
`validate-manifests.yml:214-219` validates `-strict` against, so its manifests
would fail CI until an ignore pattern was added. Its main draw — auto
instrumentation injection — is producer-side work owned by #38 and #195.

**B. DaemonSet agent per node, or a two-tier agent + gateway topology.**
Dropped for now. This is a small k3s cluster
(`infrastructure/k3s-preview/`, a handful of workers), and a per-node agent
multiplies the memory footprint in a namespace where `VMSingle` alone requests
1400Mi. A single gateway hop is sufficient for the span volume a Temporal ->
Argo -> agent chain produces. The design keeps this open: adding an agent tier
later needs no producer change, because producers address a Service name either
way. Revisit when node count or span rate grows.

**C. Point producers straight at a trace backend; no collector.**
Dropped. It defeats the issue's central requirement. Redaction would have to be
implemented in every producer (`mctl-agent`, `mctl-agents`, and anything added
later), which is exactly the leak surface the "filtered at the boundary"
requirement exists to eliminate. Changing backends would become a coordinated
release across repos instead of a values edit, and a backend outage would put
retry/queue logic in each application's request path.

**D. A dedicated `otel` or `observability` namespace.**
Dropped. It buys no isolation the collector needs — it sits in the same trust
tier as VMSingle, Loki and Grafana — and it costs real reachability work: the
preview-namespace egress allowlist
(`helm-charts/tenant/templates/preview.yaml:234-266`) names `monitoring`
explicitly and would need a new entry, `vault-netpol.yaml`-style ingress
allowlists elsewhere name `monitoring`, and every tenant that relies on
`allow-cluster-egress` would be unaffected only by luck of the `10.0.0.0/8`
rule. Placing it in `monitoring` means **zero NetworkPolicy edits in tenant
namespaces and therefore zero edits to the
`mctl-tenant-networkpolicy-allowlist` admission policy** — the change with the
highest blast radius in this repo is avoided entirely.

## Platform impact

**Migrations.** None. No existing object is modified except: adding one
`sources` entry is not even required (the new Application owns its own
`infra-components` path), and `base-service` gains one optional default-off
values block. `vmagent`, `VMSingle`, `promtail`, `loki-stack`, `vmalert` and
`alertmanager` configuration is untouched.

**Backward compatibility.** Fully compatible. Nothing consumes traces today, so
there is no behaviour to preserve. Services keep rendering identically until
someone opts in to `otel.enabled: true`.

**Resource impact.** +2 pods in `monitoring`, ~200m CPU / 384Mi memory
requested, ~1Gi / 1 CPU worst-case limits. No PVC, no object storage, no new
external dependency. Trace *storage* cost is deferred with the backend decision.

**Risks and mitigations.**

- *A `podSelector: {}` NetworkPolicy would break the monitoring namespace.*
  `monitoring` has no NetworkPolicy today, so the first one written with an
  empty pod selector converts the whole namespace to an allowlist and severs
  Grafana, VMSingle, vmagent and Loki. Mitigation: the policy selects collector
  pods only, and CI review plus a post-sync check of Grafana/VMSingle health is
  an explicit task.
- *Double-scrape.* `vmagent` has `selectAllByDefault: true`, so a chart-rendered
  ServiceMonitor plus the hand-written VMServiceScrape would duplicate every
  series and double-fire every alert over it (#1159). Mitigation: chart
  `serviceMonitor`/`podMonitor` presets explicitly disabled; the DoD for the
  scrape task is "exactly one target in the collector scrape pool".
- *Self-ticketing alert loop.* Alerts without `mctl_agent_self: "true"` reach
  the `mctl-agent` webhook receiver and open incidents against the platform's
  own collector. Mitigation: the label is on every rule and asserted in the
  promtool `exp_labels` of the unit test.
- *`vm-rules/` kind guard.* Putting the NetworkPolicy or VMServiceScrape under
  `vm-rules/` fails CI by design (`check-vm-rules.sh:85-91`). Mitigation: they
  live in `infra-components/observability/otel-collector/`.
- *Memory-limiter mis-tuning.* Percentages set against a small limit cause the
  collector to refuse spans under normal load, which looks like producer
  failure. Mitigation: `OtelCollectorRefusedSpans` alerts on it, and the runbook
  records the sizing and how to raise it.
- *Redaction gap.* A producer invents a new sensitive attribute name that no
  pattern matches. Mitigation: patterns rather than exact keys, plus
  `blocked_values` on credential shapes so a secret under an innocuous key is
  still masked; plus a documented review step when #38 / #195 add attributes.
- *RBAC breadth.* `k8sattributes` requires a ClusterRole. Mitigation: scoped to
  get/list/watch on pods, namespaces and replicasets; no secrets, no write
  verbs. `claude-review.yml`'s conventions block calls out permissive RBAC as a
  review focus, so this will be examined on the PR.
- *Collector or backend outage becoming an availability incident.* Mitigation is
  layered: 2 replicas, memory limiter instead of OOM, queue + retry instead of
  synchronous failure, queue-full drops rather than blocks — and an explicit
  test that a representative workload stays green while the backend is a black
  hole.
- *Chart version drift.* Mitigation: exact pin, same as every other chart in the
  repo; `argocd-freshness.yml` and the agent pipeline surface upgrades.
