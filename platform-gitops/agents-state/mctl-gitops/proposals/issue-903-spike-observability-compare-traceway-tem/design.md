# Design: issue-903-spike-observability-compare-traceway-tem

## Current state

### The producer boundary already exists and is already vendor-neutral

Issue #902 merged on 2026-09-11 (`mctlhq/mctl-gitops#1189`). Everything the
comparison needs on the producer side is in place:

- `platform-gitops/bootstrap/templates/observability/otel-collector.yaml` is an
  ArgoCD `Application` with two sources. The first pulls chart
  `opentelemetry-collector` `0.173.0` from
  `https://open-telemetry.github.io/opentelemetry-helm-charts` with the image
  overridden to `otel/opentelemetry-collector-contrib:0.160.0` and
  `command.name: otelcol-contrib` (mandatory — `k8sattributes`, `redaction`
  and the OTTL `filter` processor do not exist in the core distribution). The
  second source is this repo at
  `platform-gitops/infra-components/observability/otel-collector`. Destination
  namespace `monitoring`, `syncPolicy.automated` with `prune` and `selfHeal`.
- The traces pipeline is
  `otlp -> memory_limiter -> k8sattributes -> resource -> redaction ->
  filter/health -> batch -> [debug, otlp/backend?]`. `logs` and `metrics`
  pipelines are explicitly `null`.
- The single backend switch is
  `platform-gitops/bootstrap/values.yaml:22-25`:

  ```yaml
  otelCollector:
    clusterName: mctl-preprod
    environment: preprod
    backendEndpoint: ""   # "Empty until a trace backend is chosen"
  ```

  The `otlp/backend` exporter and its `sending_queue`
  (`num_consumers: 4`, `queue_size: 5000`) and `retry_on_failure`
  (`5s`/`30s`/`300s`) are wrapped in `{{- if .Values.otelCollector.backendEndpoint }}`
  in both the `exporters:` map and the `service.pipelines.traces.exporters`
  list. With the key empty, the rendered pipeline is `exporters: [debug]`.
- `platform-gitops/helm-charts/base-service/values.yaml:199-201` carries a
  default-off opt-in (`otel.enabled: false`,
  `otel.endpoint: http://otel-collector.monitoring.svc.cluster.local:4318`)
  rendered by `base-service.env` in
  `platform-gitops/helm-charts/base-service/templates/_helpers.tpl:105-150`,
  shared by `templates/deployment.yaml` and `templates/rollout.yaml` and
  covered by `tests/test_base_service_otel_env.py`. No service has opted in.
- `platform-gitops/infra-components/observability/otel-collector/networkpolicy.yaml`
  (`allow-otel-collector-ingress`) allows 4317/4318 from `admins`, `mctl-api`,
  `argo-workflows`, `temporal`, `monitoring` and any namespace labelled
  `mctl.me/tenant`, plus a second rule for vmagent to :8888. Its `podSelector`
  matches the collector's own pods, never `{}` — `monitoring` has no
  namespace-wide NetworkPolicy
  (`infra-components/observability/blackbox/blackbox-exporter.yaml:19-26`) and
  a `{}` selector there would cut off Grafana, VMSingle, vmagent and Loki.
- `platform-gitops/infra-components/observability/vm-rules/otel-collector-alerts.yaml`
  defines `OtelCollectorDown`, `OtelCollectorRefusedSpans`,
  `OtelCollectorExportFailures` and `OtelCollectorQueueNearFull`
  (`otelcol_exporter_queue_size / otelcol_exporter_queue_capacity > 0.8`), all
  labelled `mctl_agent_self: "true"` so they do not open incidents against the
  platform's own collector. `tests/test_otel_collector_alert_windows.py`
  enforces the `increase(...[W]) < for: H` invariant.
- `docs/runbooks/otel-collector.md` documents the swap procedure and closes
  with "Accepted residuals: **No trace backend selected.**"

### What is missing

- **No trace backend of any kind.** No Tempo, Traceway, Langfuse, Phoenix or
  SigNoz manifest exists anywhere in the repo. `backendEndpoint` is `""`.
- **No Grafana tracing datasource.** Grafana `12.4.2` runs at
  `grafana.mctl.ai` behind Dex OIDC
  (`bootstrap/templates/observability/monitoring.yaml:314-390`) with a
  datasource sidecar keyed on the `grafana_datasource: "1"` ConfigMap label.
  Loki and academy-postgres are provisioned this way
  (`bootstrap/templates/observability/loki-datasource.yaml`,
  `academy-postgres-datasource.yaml`); nothing of type `tempo` or `jaeger`
  exists.
- **No `docs/adr/` directory.** Only `docs/plans/`, `docs/runbooks/`,
  `docs/soc2/`. The ADR this spike produces creates it.
- **No span producers.** `mctlhq/mctl-agent#38` and `mctlhq/mctl-agents#195`
  have not shipped. There is no real DevLoop trace to compare backends with.
  The #902 proposal parked exactly this
  (`platform-gitops/agents-state/mctl-gitops/proposals/issue-902-feat-observability-deploy-opentelemetry/requirements.md:191-194`:
  "Which trace backend, and when? ... Nothing in the repo references either.").
- **No fan-out.** `backendEndpoint` is a scalar. Comparing five candidates
  against it today means five sequential deploys, five values edits, and five
  different span streams — which is not a comparison.

### The environment the candidates must fit in

- `infrastructure/k3s-preview/kube.tf:120-150` — one `cx33` control plane and
  three `cx43` agents in Hetzner `fsn1`, `cluster_name = "mctl-preprod"`.
- Existing stateful observability footprint: VMSingle on a 25Gi PVC with
  `retentionPeriod: "28d"` and a `vmbackup` sidecar to R2; Loki with
  `persistence.enabled: false` writing tsdb chunks straight to R2
  (`bucketnames: loki`, `retention_period: 336h`).
- Object storage precedent is **Cloudflare R2**
  (`https://6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com`), used
  by Loki, the VM backup sidecar, Argo Workflows artifacts
  (`bootstrap/templates/core-infra/argo-workflows.yaml:164`) and CNPG backups
  (`infra-components/data/cnpg/shared/cluster.yaml:26`). MinIO exists
  (`bootstrap/templates/data/minio.yaml`, chart `5.4.0`, 40Gi, buckets
  `platform-cache`/`platform-state`/`postgres-backups`) but is not the
  established trace-scale store.
- Data tier already present: CloudNativePG shared cluster
  (`infra-components/data/cnpg/shared/`), Valkey
  (`infra-components/data/valkey/`), Temporal
  (`bootstrap/templates/data/temporal.yaml`). **No ClickHouse anywhere** —
  `grep -rli clickhouse platform-gitops` returns nothing. Any ClickHouse-backed
  candidate (Langfuse, SigNoz) introduces a brand-new stateful system class to
  this cluster, not just a new workload.
- mctl already has LLM cost telemetry without any tracing backend:
  `infra-components/observability/grafana-dashboards/openclaw-llm-usage-dashboard-configmap.yaml`
  and `vm-rules/openclaw-llm-alerts.yaml` alert on
  `openclaw_llm_prompt_tokens_total{provider=...}` scraped from `/metrics`.
  This is the baseline that a specialist AI backend has to beat, and it is
  the reason "general trace store only" is a live outcome rather than a
  strawman.

## Proposed solution

Three moving parts: a **fan-out harness** (a backwards-compatible values
change to the existing collector), an **evaluation sandbox** (a disposable
namespace with a declared teardown date), and a **decision artifact** (a
weighted matrix and the repo's first ADR). Nothing touches producer code,
because there is no producer code to touch.

### 1. Generalize `backendEndpoint` to `backends` (values-only, backwards compatible)

Replace the single templated exporter in
`bootstrap/templates/observability/otel-collector.yaml` with a loop, keeping
the legacy scalar working:

```yaml
exporters:
  debug:
    verbosity: normal
  {{- if .Values.otelCollector.backendEndpoint }}
  otlp/backend:
    endpoint: {{ .Values.otelCollector.backendEndpoint | quote }}
    # sending_queue / retry_on_failure unchanged
  {{- end }}
  {{- range .Values.otelCollector.backends }}
  otlp/{{ .name }}:
    endpoint: {{ .endpoint | quote }}
    {{- if .insecure }}
    tls:
      insecure: true
    {{- end }}
    {{- with .headers }}
    headers:
      {{- toYaml . | nindent 8 }}
    {{- end }}
    sending_queue:
      enabled: true
      num_consumers: {{ .numConsumers | default 4 }}
      queue_size: {{ .queueSize | default 5000 }}
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 300s
  {{- end }}
```

and the matching `{{- range }}` in
`service.pipelines.traces.exporters`. `otelCollector.backends` defaults to
`[]` in `bootstrap/values.yaml`, so **with no candidate configured the
rendered ConfigMap is byte-identical to today's** and
`docs/runbooks/otel-collector.md`'s one-key swap remains literally true.

Why this shape and not five separate collectors, or a `routing` connector:

- Every exporter gets its **own** `sending_queue`. In the OpenTelemetry
  Collector, exporters in a pipeline are fanned out independently; a failing
  or slow exporter drains into its own queue and drops on full, it does not
  stall the receiver or the siblings. That is precisely the "backend outage
  does not break producer workloads" acceptance criterion, and it is already
  alerted on by the existing `OtelCollectorQueueNearFull` /
  `OtelCollectorExportFailures` rules — which are per-exporter series, so they
  keep working unchanged and now tell us *which* candidate is unhealthy.
- A `routing` connector would send different spans to different candidates.
  For a comparison that is the wrong primitive: the requirement is identical
  input. `routing` becomes interesting only in outcome 2, after the decision.
- Separate collector deployments would multiply the redaction config, which is
  the single most safety-critical block in the file. One pipeline, one
  redaction processor, N exporters keeps exactly one copy of the block lists.

**Credentials.** Candidates that need an auth header (Langfuse uses HTTP Basic
over its OTLP endpoint; a managed tier of anything would need a key) must not
put it in `values.yaml`. The pattern already used everywhere in this repo
applies: a Vault path under `secret/data/teams/...`, an `ExternalSecret` in
`infra-components/observability/otel-collector/`, the chart's `extraEnvsFrom`
pointing at the synced Secret, and the config referencing
`${env:CANDIDATE_AUTH_HEADER}`. The `headers` map in the values above holds
the `${env:...}` expression, never a literal.

### 2. A committed, representative DevLoop trace fixture

Because #38/#195 have not shipped, the "same representative mctl execution"
criterion has to be satisfied by a fixture. Add:

- `tests/fixtures/devloop-trace.json` — one trace, OTLP/JSON, with the span
  tree the issue specifies: DevLoop root -> Temporal orchestration -> Argo
  worker/pod -> agent/model invocation (child MCP/tool spans, GitHub
  read/write spans) -> artifact generation -> terminal outcome, plus a second
  execution whose outcome span is an error so error navigation is comparable.
  Correlation attributes as enumerated in `requirements.md`.
- `tests/fixtures/devloop-trace-redaction.json` — a deliberately poisoned
  variant carrying `gen_ai.prompt.0.content`, `mcp.tool.arguments`,
  `http.request.header.authorization` and a benign key
  (`mctl.artifact.note`) whose value is `ghp_` + 36 chars. This is the
  privacy proof: whatever reaches a candidate from this file is what the
  redaction processor let through.
- `platform-gitops/argo-workflows/cluster-templates/wft-otel-trace-fixture.yaml`
  — a `ClusterWorkflowTemplate` that runs a container POSTing the fixture to
  `http://otel-collector.monitoring.svc.cluster.local:4318/v1/traces` at a
  declared rate for a declared duration. Argo Workflows already run in
  `argo-workflows`, which the collector NetworkPolicy already allows on
  4317/4318 — no policy change needed to emit the fixture. Parameters:
  `ratePerSecond`, `durationMinutes`, `executionCount`.

Running the fixture through the *real* collector rather than pointing an
emitter at each candidate directly is the point: it proves the comparison ran
through the redaction and enrichment the production path will have.

### 3. Two-stage elimination: paper screen, then live PoC

**Stage A — architecture/ops-fit screen (no cluster changes).** For all five
candidates record, in a single matrix file: license of the self-hostable
artifact; whether a maintained Helm chart or Kubernetes manifests exist and at
what pinnable version; the full stateful dependency list; whether plain OTLP
(not a vendor SDK, not OpenInference-only) is a supported ingestion path; and
raw-data export capability. The issue itself asks for this for SigNoz; this
design applies it uniformly. A candidate fails the screen — and is recorded as
failed, not omitted — if it has no pinnable self-host deployment path, if it
requires producer-side vendor instrumentation, or if its dependency set cannot
be sized onto three `cx43` workers alongside the existing VMSingle/Loki/
Grafana/CNPG/Valkey/Temporal/MinIO footprint.

Traceway is the one candidate this investigation could not verify at all: it
appears nowhere in the clone and the issue's description of it is the only
evidence available. The screen resolves it first, because if it has no
self-hostable chart the rest of the spike does not need to budget for it.

**Stage B — live PoC for survivors only.** Each survivor gets an ArgoCD
`Application` at
`platform-gitops/bootstrap/templates/observability/eval/<candidate>.yaml`,
destination namespace `observability-eval`, single replica, smallest viable
storage, `syncPolicy.automated` **without** `selfHeal` (so an operator can
scale a candidate to zero for the outage test without ArgoCD fighting back).
Supporting manifests at
`platform-gitops/infra-components/observability/eval/<candidate>/`:

- a NetworkPolicy with a `podSelector` matching that candidate's pods only —
  never `{}` — allowing ingress from `monitoring` (the collector) and from
  Traefik if the candidate has a UI;
- a `VMServiceScrape` if the candidate exposes Prometheus metrics, so its own
  health is visible in the stack we already trust;
- an `ExternalSecret` for any credential.

Each candidate's upstream chart repo must also be whitelisted. ArgoCD
`AppProject`s in `platform-gitops/bootstrap/templates/projects/` restrict
`sourceRepos` (for example `project-platform.yaml` lists
`https://go.temporal.io/helm-charts`) and carry
`clusterResourceWhitelist`/`namespaceResourceWhitelist`. A candidate chart
pulled from a repo that is not listed, or rendering a kind that is not
whitelisted, fails to sync with a project-permission error rather than a
chart error — a cheap failure to mistake for a candidate defect, so it is
called out as its own task DoD.

The namespace itself carries
`mctl.ai/teardown-after: "<date>"` and `mctl.ai/purpose: "issue-903-spike"` so
an abandoned spike is greppable. `observability-eval` is a *new* namespace on
purpose: a crashlooping ClickHouse in `monitoring` shares a namespace with
Grafana, VMSingle, vmagent and Loki, and `monitoring` has no namespace-wide
NetworkPolicy to contain it.

The collector then gets, in `bootstrap/values.yaml`:

```yaml
otelCollector:
  backends:
    - name: tempo
      endpoint: tempo-distributor.observability-eval.svc.cluster.local:4317
      insecure: true
    # ... one entry per surviving candidate
```

### 4. Scoring and the decision rule

`docs/adr/0001-agent-execution-trace-backend.md` (creating `docs/adr/`) holds
the matrix. Weights, fixed before any candidate is deployed so the rubric
cannot be retrofitted to a favourite:

| Dimension | Weight |
|---|---|
| Trace reconstruction | 25 |
| AI/agent observability | 25 |
| Data ownership / portability | 20 |
| Operations | 15 |
| Security / privacy | 10 |
| Evals / quality loop | 5 |

Each cell scores 0-5 with a one-line evidence citation (a screenshot path, a
PromQL result, a query that worked). Weighted total out of 500. Tie margin:
25 points; inside it, the candidate adding the smaller new dependency surface
on this cluster wins, which given "no ClickHouse anywhere" is a concrete and
decidable criterion rather than a taste judgement.

Decision rule:

1. If one candidate wins outright on both trace reconstruction and AI/agent
   observability and its operations score is not the lowest -> **single
   backend** for that candidate.
2. Else if the best general trace store and the best AI specialist each win
   their own axis by more than the tie margin, and their combined measured
   footprint fits the cluster -> **general trace store + AI specialist**
   (outcome 2), with the specialist fed by a `routing` connector or a second
   exporter and explicitly *not* the FinOps source of truth.
3. Else if no candidate's AI/agent score exceeds what the existing
   `openclaw-llm-usage` dashboard pattern already delivers by more than one
   point -> **ADOPT TEMPO / mctl-native only**. This is the deliberate default
   when the spike is inconclusive, because it costs one values key, one
   Grafana datasource ConfigMap and an R2 bucket, and it is the only outcome
   that is trivially reversible.
4. Else **CONTINUE COMPARISON** with one named blocker.

### 5. Cost/FinOps boundary is enforced, not assumed

A separate, explicit check: before the ADR is written, confirm that
per-DevLoop spend can be computed from the collector's own
`spanmetrics`-derived or producer-emitted metrics in VictoriaMetrics, without
querying any candidate. If a candidate would become the only place token/cost
data lives, that candidate loses points on portability regardless of how good
its cost UI is. This is the `mctlhq/.github#48` boundary made testable.

### 6. Teardown is part of the change, not a follow-up

The final PR of this proposal deletes every non-selected
`bootstrap/templates/observability/eval/` Application, deletes
`infra-components/observability/eval/`, removes the namespace (ArgoCD
`prune: true` handles the workloads; PVCs are deleted explicitly), and leaves
`otelCollector.backends` naming only the winner — or `[]` if the verdict is
mctl-native only. `docs/runbooks/otel-collector.md`'s "Swapping the backend"
and "Accepted residuals" sections are updated in the same PR.

## Alternatives

**Sequential single-candidate evaluation using the existing
`backendEndpoint`.** Zero template change: point the scalar at one candidate,
observe, repeat. Dropped because each candidate would see a different span
stream at a different time under different cluster load, which violates the
issue's "same representative mctl execution is exported through the Collector
to each viable candidate" criterion outright. It is also slower in wall-clock
(five sequential soak windows) than the template change costs to write, and it
gives no way to A/B two UIs side by side on the same trace id — which is the
single most informative thing a reviewer can do.

**Point a standalone OTLP emitter at each candidate directly, bypassing the
collector.** Simpler to set up and needs no repo change at all. Dropped
because it tests the candidates against a span stream that never went through
`redaction`, `k8sattributes` or `resource`. The whole question this spike
answers is "is this backend useful on *metadata-first, prompt-free*
telemetry", and an emitter that bypasses redaction would answer a different,
flattering question. It would also leave the privacy criterion unproven, since
what reaches a candidate is exactly what redaction let through.

**Adopt Tempo immediately, skip the comparison.** Defensible on the evidence
already in the repo — Tempo is OTLP-native, writes to S3-compatible object
storage (Cloudflare R2 is already the pattern for Loki, VM backups, Argo
artifacts and CNPG), plugs into the existing Grafana `12.4.2` via one
`grafana_datasource: "1"` ConfigMap exactly like `loki-datasource.yaml`, adds
no new stateful system class, and is from the same vendor as the Loki already
deployed. Dropped as the *starting* position because the issue explicitly
asks for a comparative decision and because the AI/agent axis — token, cache
and reasoning usage, per-execution cost, session grouping — is the one Tempo
is weakest on and the one mctl actually needs (`mctlhq/.github#48`,
`mctl-agents#195/#196/#199`). Adopting without measuring would make outcome 2
unfalsifiable later. Tempo remains the strong prior and the documented default
under decision rule 3.

**Deploy all five candidates for a full live PoC with no paper screen.** Most
thorough, and dropped on capacity. Langfuse (ClickHouse + Postgres + Redis +
blob) and SigNoz (ClickHouse) each introduce ClickHouse, which exists nowhere
in this cluster today; running both plus three others alongside VMSingle,
Loki, Grafana, CNPG, Valkey, Temporal and MinIO on three `cx43` workers risks
node-pressure eviction of the production observability stack to answer a
question a license file and a dependency list answer for free.

## Platform impact

**Migrations.** None. No schema, no data, no producer change. The collector
ConfigMap changes shape only when `otelCollector.backends` is non-empty; with
the default `[]` the rendered output is identical and a `helm template` diff
against `main` proves it.

**Backward compatibility.** `otelCollector.backendEndpoint` keeps working
alongside `backends`, so `docs/runbooks/otel-collector.md`'s documented
procedure does not become wrong mid-spike. If both are set, both exporters
render — intentional, and the runbook says so.

**Resource impact.** The collector itself is unchanged
(100m/384Mi request, 500m/512Mi limit, `replicaCount: 2`); N exporters add
queue memory bounded by `queue_size * batch size`, which is why each entry
can override `queueSize` and why evaluation candidates should run with a
smaller queue than the 5000 default. The real cost is the candidates: a new
`observability-eval` namespace on a cluster with three `cx43` workers already
carrying VMSingle (25Gi PVC), Loki, Grafana, CNPG, Valkey, Temporal, MinIO
(40Gi) and the platform's own services. Mitigation: the Stage A screen caps
how many candidates ever get deployed; single replicas; smallest viable
storage; explicit teardown date; and the candidates are scraped by the
existing vmagent so their footprint shows up in the dashboards we already
watch.

**Risks and mitigations.**

- *An evaluation candidate destabilises the production observability stack.*
  Separate namespace, per-candidate pod-scoped NetworkPolicy, no `selfHeal`
  so an operator can scale to zero instantly, and resource limits on every
  candidate workload. The collector's own `sending_queue` drop-on-full means
  even a wedged candidate cannot backpressure the gateway.
- *A `podSelector: {}` NetworkPolicy is copied into `monitoring` by accident.*
  Documented hazard already
  (`infra-components/observability/otel-collector/networkpolicy.yaml`,
  runbook "NetworkPolicy" section). The eval policies live in a different
  namespace and are reviewed for a non-empty selector as an explicit task DoD.
- *A candidate's UI is exposed without authentication.* Any Ingress goes
  through the same Traefik + Dex OIDC path as `grafana.mctl.ai`; the default
  is no Ingress at all and `kubectl port-forward` for the human review.
- *Redaction misses a new attribute the fixture introduces.* The poisoned
  fixture exists specifically to fail loudly here, and the runbook's "When
  #38/#195 land and add new attributes" section already prescribes adding a
  *pattern* rather than an exact key.
- *A candidate credential leaks into git.* Vault + `ExternalSecret` +
  `${env:...}` only; a task DoD is that `git grep` for the credential shape
  over the PR is empty. The repo's existing `blocked_values` patterns
  (`ghp_`, `sk-`, `hvs.`, JWT) are the same shapes to grep for.
- *The spike never ends.* Teardown annotation with a date, teardown is a
  numbered task in this proposal rather than a follow-up issue, and decision
  rule 3 supplies a concrete default so "inconclusive" still closes.
- *The fixture's attribute names diverge from what #38/#195 actually emit.*
  Accepted and recorded in the ADR. Relative backend ranking does not depend
  on the exact strings; if a real trace is available before the ADR is
  written, re-run and record the divergence.
- *`selfHeal: true` on `otel-collector` reverts a manual exporter tweak.* Real
  and intended: every collector change in this spike goes through
  `bootstrap/values.yaml` and a PR, same as any other template/values change
  in this repo.
