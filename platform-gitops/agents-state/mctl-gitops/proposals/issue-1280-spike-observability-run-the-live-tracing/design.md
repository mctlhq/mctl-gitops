# Design: issue-1280-spike-observability-run-the-live-tracing

## Current state

### The producer boundary exists and points nowhere

`#902` shipped the gateway collector and `#903` shipped everything around it
that can be built without a cluster. Concretely, in this clone:

- `platform-gitops/bootstrap/templates/observability/otel-collector.yaml` is an
  ArgoCD Application for chart `opentelemetry-collector` pinned `0.173.0`, with
  the image forced to `otel/opentelemetry-collector-contrib:0.160.0` and
  `command.name: otelcol-contrib` because `k8sattributes`, `redaction` and the
  OTTL `filter` processor do not exist in the core distribution. It runs
  `mode: deployment`, `replicaCount: 2`, in `monitoring`.
- Its traces pipeline is `receivers: [otlp]` →
  `memory_limiter, k8sattributes, resource, redaction, filter/health, batch` →
  `debug` plus any configured backends. `logs` and `metrics` are explicitly
  `null`.
- `platform-gitops/bootstrap/values.yaml:14-43` holds the three switches this
  proposal flips: `otelCollector.backendEndpoint: ""` ("Empty until a trace
  backend is chosen"), `otelCollector.backends: []`, and
  `otelCollector.eval: {enabled: false, teardownAfter: "", candidates: []}`.
  Every one of those comments names `mctlhq/mctl-gitops#1280` as the issue that
  fills them in.
- `otel-collector.yaml:241-261` renders one `otlp/<name>` exporter per
  `backends[]` entry, each with its own `sending_queue`
  (`numConsumers` default 4, `queueSize` default 5000) and `retry_on_failure`
  (5s / 30s / 300s), and `:285-287` appends each to the single traces pipeline.
  Because there is exactly one pipeline, every candidate necessarily receives
  spans that passed the identical processors. That is the property that makes
  the comparison fair, and it is already built.
- `serviceMonitor.enabled: false` and `podMonitor.enabled: false` on the
  collector itself, because vmagent runs `selectAllByDefault: true`
  (`bootstrap/templates/observability/monitoring.yaml:287`) and would otherwise
  double-scrape — incident `#1159`.

### The sandbox exists but renders nothing

`bootstrap/templates/observability/eval-namespace.yaml` is wholly wrapped in
`{{- if .Values.otelCollector.eval.enabled }}`. When enabled it creates the
`observability-eval` Namespace (label `mctl.ai/purpose: issue-903-spike`,
annotation `mctl.ai/teardown-after` as a greppable abandonment guard) and four
NetworkPolicies: `default-deny-all`, `allow-intra-namespace`,
`allow-cluster-egress` (DNS to `kube-system`, then `10.0.0.0/8` minus the
worker `10.0.0.0/24` and control-plane `10.255.0.0/24` subnets, a 6443
carve-out for `kubernetes.default`, `172.16.0.0/12`, `192.168.0.0/16` — and
therefore **no public internet**), and `allow-ingress-from-monitoring` (TCP
4317/4318 from the `monitoring` namespace only).

`eval-candidates.yaml` ranges over `otelCollector.eval.candidates` and renders
one ArgoCD `Application` named `otel-eval-<name>` per entry into that
namespace, single-source or dual-source depending on whether the entry sets
`manifestsPath`. `automated.prune: true` is set and `selfHeal` is deliberately
omitted, with a comment stating that this is so an operator running the outage
test under `#1280` can `kubectl scale --replicas=0` a candidate without ArgoCD
reverting it. Its header also instructs `#1280` to disable each candidate
chart's own `ServiceMonitor`/`PodMonitor` preset for the same `#1159` reason.

`tests/fixtures/otel-eval-candidates.example-values.yaml` is a worked
two-candidate overlay used by `tests/test_otel_collector_backends_render.py`
and by the kubeconform step in `.github/workflows/validate-manifests.yml`, so
the shape of the values this proposal writes is already schema-validated in CI.

### The evidence instruments exist and are unused

- `docs/adr/0001-rubric.yaml` — six dimensions with weights
  25/25/20/15/10/5, a written 0-5 `cell_scale`, `weighted_total_max: 500`,
  `tie_margin: 25`, a tie-break favouring the smaller new operational
  dependency, a four-branch `decision_rule`, seven `permitted_verdicts`,
  `verdict: null`, and a `stage_a` paper screen in which **only Tempo is
  `SURVIVES`**; Traceway, Langfuse, Phoenix and SigNoz are all `UNVERIFIED`.
  Every one of the thirty score cells is `{score: null, citation: ""}`.
- `docs/adr/0001-agent-execution-trace-backend.md` — Status `Proposed`, Decision
  section carrying `<!-- VERDICT: UNFILLED -->`, and an "Exit procedure" whose
  six steps are literally this proposal's checklist.
- `tests/test_adr_rubric_frozen.py` enforces the freeze: all scores null, all
  citations empty, `verdict` null, ADR status `Proposed`, the `UNFILLED` marker
  present, the Markdown weight table and the YAML weights agreeing
  dimension-for-dimension, and the Stage A honesty rule that no row whose
  `evidence` is `issue-903-body` may be `SURVIVES`.
- `platform-gitops/argo-workflows/cluster-templates/wft-otel-trace-fixture.yaml`
  registers the `otel-trace-fixture` `ClusterWorkflowTemplate`, parameters
  `rate_per_second: 5`, `duration_minutes: 1`, `execution_count: 10`,
  `fixture: devloop-trace.json`, POSTing to
  `otel-collector.monitoring.svc.cluster.local:4318/v1/traces` with fresh trace
  and span ids per execution. There is no CronWorkflow, so it is inert until
  submitted. Its ConfigMap
  (`platform-gitops/argo-workflows/config/otel-trace-fixture-configmap.yaml`) is
  generated from the fixtures by `scripts/materialize-otel-trace-fixture.py` and
  CI enforces freshness with `--check`.
- `tests/fixtures/devloop-trace.json` carries `gen_ai.chat` spans with
  `gen_ai.usage.input_tokens`, `output_tokens`, `cache_read_input_tokens` and
  `reasoning_tokens`; `devloop-trace-redaction.json` is the poisoned variant
  whose values are fabricated on purpose.

### The three facts that shape this design

**1. The redaction pattern eats the token counters.**
`otel-collector.yaml:179` blocks
`'(?i).*(authorization|cookie|api[-_]?key|token|secret|password|credential).*'`.
That is a substring match, so `gen_ai.usage.input_tokens` and every sibling
counter are masked before any exporter sees them. This is `#1332`, and it means
the `ai_agent_observability` dimension — 25 of the 100 weight points — cannot be
scored on token or cost evidence until it is fixed upstream of this work. The
constraint worth recording is that the collector's `redaction` processor
compiles Go RE2, which has no negative lookahead, so the fix in `#1332` has to
be a narrowed positive pattern, not an exclusion.

**2. There is essentially no live producer traffic today.**
`platform-gitops/helm-charts/base-service/values.yaml` defaults `otel.enabled:
false` and no service in `platform-gitops/services/*/*/values.yaml` opts in.
`claude-agent-sdk` appears nowhere in this repo. So unless
`mctlhq/mctl-agent#38` / `mctlhq/mctl-agents#195` are live on the cluster during
the soak window, the only spans reaching candidates are the committed fixtures.
The design must therefore be explicit about which cells are fixture-derived.

**3. `observability-eval` has NetworkPolicies but no quota.**
`eval-namespace.yaml` creates no `ResourceQuota` and no `LimitRange`, unlike the
tenant chart which has both (`helm-charts/tenant/templates/resourcequota.yaml`,
`limitrange.yaml`). The cluster is three `cx43` workers plus one `cx33` control
plane (`infrastructure/k3s-preview/kube.tf:120-145`), with `hcloud-volumes` as
the only storage class and no Longhorn. Dropping an unbounded ClickHouse-backed
candidate into an unquota'd namespace on that cluster is the single largest
operational risk in this spike.

## Proposed solution

Six sequential gates, each a separate commit, ordered so that no measurement can
precede its own declaration and no score can precede the instrument that
consumes it.

### Gate 0 — precondition verification (no cluster change)

Record in the ADR the resolved state of `#1332`, `mctl-agent#38`/PR 137,
`mctl-agents#195`/PR 466 and `mctl-agent#139`. Add a test asserting the
post-`#1332` redaction behaviour directly against the rendered collector config:
`gen_ai.usage.input_tokens` must survive, `github_token` must still be masked.
The test lives here even though the fix lives in `#1332`, because this repo is
where the pattern is rendered and this proposal is the consumer that breaks if
it regresses. If `#1332` is unresolved when the window opens, this gate records
that fact rather than blocking, and the token/cost cells become unmeasured.

### Gate 1 — resolve Stage A and widen the candidate axis

Every `UNVERIFIED` row in `docs/adr/0001-rubric.yaml`'s `stage_a` block moves to
`SURVIVES` with a verified license, a real chart or image coordinate and a
pinnable version, or to `SCREENED-OUT` with a reason. The portability gate is
decisive here: a candidate that needs a vendor SDK or vendor-specific
instrumentation in `mctl-agent` / `mctl-agents` producer code is screened out,
because the no-candidate-SDK constraint is what the whole `#902` collector
boundary exists to protect. Phoenix's OpenInference orientation and Traceway's
unlocatable artifact are the two rows most likely to end as `SCREENED-OUT`.

Candidate F is added in the same commit, as two separately scored entries
`agento11y-self-managed` and `agento11y-cloud`, appended to `candidates` and to
all six `dimensions[].candidates` maps, with matching `stage_a` rows and two new
`permitted_verdicts`. Dimension keys, weights, `cell_scale`, `tie_margin`,
`tie_break` and `decision_rule` are left byte-identical — the freeze that
matters is the freeze on the scoring instrument, and widening the candidate axis
before any score exists cannot retrofit the rubric to a favourite. This is the
one place this proposal knowingly amends a file `#903` called frozen, and it
does so in a reviewed commit whose tree still contains no non-null score, so
`tests/test_adr_rubric_frozen.py` still passes at that commit.

### Gate 2 — quota the sandbox, then open it

`eval-namespace.yaml` gains a `ResourceQuota` and a `LimitRange` inside the same
`{{- if .Values.otelCollector.eval.enabled }}` guard, sized from
`otelCollector.eval.quota` (new values key, defaulted so the rendered output
stays unchanged while `enabled` is false). The shape copies
`helm-charts/tenant/templates/resourcequota.yaml` and `limitrange.yaml` rather
than inventing a new one. Then `otelCollector.eval.enabled: true` and
`teardownAfter: "<date>"` land together, in a commit that sets both or neither.

Candidate deployment follows in waves, because six candidate shapes — two of
them ClickHouse-backed, one of them Langfuse's ClickHouse + Postgres + Redis +
blob storage — do not plausibly coexist on three `cx43` nodes. Each wave is one
`otelCollector.eval.candidates` list and one declared soak window. Per-candidate
values must set that chart's `serviceMonitor.enabled: false` and
`podMonitor.enabled: false`.

The Cloud shape of candidate F is the one case that collides with the
namespace's design: `allow-cluster-egress` admits no public internet. The
resolution is a narrowly scoped, single-destination egress NetworkPolicy added
as a fifth policy for that one candidate's pod selector, reviewed on its own
merits, with the requirement itself scored as a cost against
`data_ownership_portability`. If that carve-out is refused on review, the Cloud
shape's cells are marked unmeasured rather than scored from documentation.

### Gate 3 — declare the window, then fan out

A new `soak:` block is added to `docs/adr/0001-rubric.yaml` carrying, per wave:
`declared_at`, `window_start`, `window_end`, `candidates`, the fixture emitter
parameters actually used (`rate_per_second`, `duration_minutes`,
`execution_count`, `fixture`), the resulting declared span volume, and whether
live producer telemetry is expected. This commit's tree must contain no non-null
score cell — that is the mechanical form of the issue's "declared before the
measurements, not chosen afterwards" requirement, and it is checkable rather
than a promise.

Only then does `otelCollector.backends` gain one entry per live candidate,
`{name, endpoint: "<svc>.observability-eval.svc.cluster.local:4317", insecure:
true}`, matching the `candidate-a` shape in the example fixture. Any candidate
needing an authorization header gets `${env:...}` sourced from a Vault-backed
ExternalSecret surfaced through the chart's `extraEnvFrom`, exactly as
`docs/runbooks/otel-collector.md` already documents; no literal credential ever
enters this repository.

The soak is driven by submitting `otel-trace-fixture` with the declared
parameters, for both `devloop-trace.json` and `devloop-trace-redaction.json`.

### Gate 4 — measure

Each dimension gets a named measurement rather than an impression:

| Dimension | How it is measured |
|---|---|
| `trace_reconstruction` | Open one fixture execution in each candidate's UI; record whether the Temporal, Argo, model, MCP/tool, GitHub, artifact and outcome spans form one tree, and whether search by workflow/repo/issue/PR/agent attribute returns it. |
| `ai_agent_observability` | Group by `gen_ai.request.model`; read `gen_ai.usage.*` counters. Gated on `#1332`; unmeasured if the counters are still masked. |
| `data_ownership_portability` | Export the soak's spans through the candidate's own API; confirm that removing its `backends[]` entry is the only producer-side change needed to drop it. |
| `operations` | VictoriaMetrics series over the declared window: candidate CPU, working-set memory, PVC growth, restart counts. Plus collector-side `otelcol_exporter_send_failed_spans`, `otelcol_exporter_queue_size` and `otelcol_exporter_queue_capacity`, which are labelled `exporter="otlp/<candidate>"` and therefore give per-candidate ingest reliability for free. |
| `security_privacy` | Replay `devloop-trace-redaction.json`, then search each candidate's own store for the fabricated `ghp_*`, `sk-*`, `hvs.*` and JWT-shaped strings and for `gen_ai.prompt.*`, `mcp.tool.arguments`, `http.request.header.authorization`. Any hit is a measured failure. |
| `evals_quality_loop` | Attach one mctl-owned score to a fixture execution and record whether the candidate stores and surfaces it without requiring backend-owned semantics. |
| Producer isolation | Scale one candidate to zero replicas mid-window — enabled by `eval-candidates.yaml`'s deliberate omission of `selfHeal` — and record whether `otelcol_receiver_refused_spans` rose and whether the other candidates kept receiving. |

Each cell is filled with either `{score: <0-5>, citation: "<one line>"}` or
`{score: null, unmeasured_reason: "<why>"}`. The rubric schema gains
`unmeasured_reason`, and exactly one of the two forms is permitted per cell.
Where a candidate has unmeasured cells, its weighted total is stated as a range
between "unmeasured cells count zero" and "unmeasured cells count five", with
the unmeasured dimensions named. A range that still decides the verdict is a
valid decision; a range that straddles the decision is branch 4.

The producer-isolation test will trip `OtelCollectorExportFailures` in
`platform-gitops/infra-components/observability/vm-rules/otel-collector-alerts.yaml`.
That alert firing is the expected outcome, not an incident; the window
declaration says so in advance so the on-call reading Telegram is not surprised.

### Gate 5 — decide, promote, tear down

Evaluate the merged `decision_rule` branches in order, apply the `tie_margin`
and `tie_break` if needed, select exactly one `permitted_verdicts` entry. In one
commit: set `verdict` in the rubric, replace the ADR's Decision section with the
verdict plus the evidence that decided it, delete the `<!-- VERDICT: UNFILLED -->`
marker, and move Status from `Proposed` to `Accepted`.

`tests/test_adr_rubric_frozen.py` is inverted rather than deleted. It keeps its
weight-agreement and Stage A honesty assertions verbatim, and its freeze
assertions become their post-decision duals: every cell has exactly one of
`score` or `unmeasured_reason`; `verdict` is non-null and a member of
`permitted_verdicts`; the ADR contains that verdict verbatim; Status is
`Accepted`; the `UNFILLED` marker is absent; the `soak` block exists and its
`declared_at` is the recorded declaration. The dimension keys and weights are
hard-coded in the test file itself so a later edit cannot move a weight to suit
a score.

`docs/runbooks/otel-collector.md` is updated in the same change: its "Swapping
the backend" section names the selected backend and the section "The evaluation
namespace and the fixture emitter (issue #903 / #1280)" is rewritten from a
description of a pending spike into either the steady-state operating notes for
the selected backend or a record that none was selected.

Teardown reverses Gate 2 and Gate 3: `otelCollector.backends: []`,
`otelCollector.eval.candidates: []`, `otelCollector.eval.enabled: false`,
`teardownAfter: ""`. ArgoCD's `prune: true` plus the Applications'
`resources-finalizer.argocd.argoproj.io` removes the candidate workloads;
because `CreateNamespace=false` and the namespace is owned by the bootstrap
chart, flipping `enabled` removes the namespace itself. Verification is that no
`otel-eval-*` Application, no `observability-eval` namespace, no `hcloud-volumes`
PVC and no candidate Vault path remain. If a candidate is adopted, it is
relocated first — a new Application under
`platform-gitops/infra-components/observability/<backend>/`, with its trace
datasource ConfigMap following the `grafana_datasource: "1"` label pattern of
`bootstrap/templates/observability/loki-datasource.yaml` — and only then is the
sandbox destroyed.

## Alternatives

**Skip the sandbox; point `otelCollector.backendEndpoint` at one candidate at a
time and compare sequentially.** Cheapest on cluster capacity and needs none of
the eval scaffolding. Dropped because sequential evaluation compares candidates
against different span streams taken at different times, which destroys exactly
the fairness property the single-pipeline fan-out was built to provide, and
because it puts an unvetted backend on the production collector's only
non-debug exporter path.

**Score candidate F in an appendix and leave the rubric literally untouched.**
Honours `#903`'s "closed list" language exactly and requires no amendment to a
file declared frozen. Dropped as the primary path because the issue explicitly
asks that F be carried into the live comparison and scored, and an appendix that
cannot contribute to the weighted total is not a comparison — it is a footnote.
Retained as the documented fallback if a reviewer rejects the amendment.

**Deploy all candidates in one wave with no `ResourceQuota`, relying on chart
defaults.** Fastest to a single declared window and avoids inventing a quota
number. Dropped because three `cx43` workers also carry Vault, CNPG, Valkey,
VictoriaMetrics, Loki, Grafana, Argo and every tenant workload; an unbounded
ClickHouse plus an unbounded Postgres would be evicting production pods, and
"the spike took the cluster down" is not an acceptable measurement of the
operations dimension.

**Run the soak on live producer traffic only, waiting for `mctl-agent#38`,
`mctl-agents#195` and `mctl-agent#139` to land.** Gives the most faithful
evidence. Dropped as a gate because the issue explicitly permits preparing
namespaces and manifests while those close, and because an indefinite wait on
three other repositories is how a spike becomes permanent scaffolding. The
committed fixtures carry the same span shape; where fidelity matters, the cell
records that its evidence is fixture-derived.

## Platform impact

**Migrations.** None to data. The only schema change is additive and confined to
`docs/adr/0001-rubric.yaml`: two new candidate keys, an `unmeasured_reason`
field per cell, a `soak` block, two new `permitted_verdicts`.

**Backward compatibility.** Every cluster-affecting change is behind values keys
that default to off. With `otelCollector.eval.enabled: false` and
`backends: []`, the rendered collector ConfigMap is byte-identical to the golden
`tests/fixtures/otel-collector-config-default.yaml` that
`tests/test_otel_collector_backends_render.py` compares against, and
`eval-namespace.yaml` / `eval-candidates.yaml` render nothing. The new
`ResourceQuota` and `LimitRange` live inside the same guard, so merging them
changes no cluster state. Teardown returns the repository to exactly this state
plus the ADR, the rubric and the runbook.

**Resource impact.** The material one. Candidates land on three `cx43` workers
with `hcloud-volumes` PVCs and no Longhorn. The `ResourceQuota` is the control;
waves are the schedule. Span volume is bounded by the declared fixture emitter
parameters, and the collector's `memory_limiter` (75/20) plus per-exporter
`sending_queue` already bound the collector's own footprint — a slow candidate
fills its own queue and drops its own batches without stalling the receiver or
affecting the other candidates.

**Risks and mitigations.**

- *A candidate exhausts the cluster.* Mitigated by the `ResourceQuota` and
  `LimitRange` added in Gate 2 and by wave-based deployment. Detection: existing
  VictoriaMetrics node alerts.
- *`#1332` is not fixed and token evidence is silently accepted anyway.*
  Mitigated by Gate 0's explicit verification test and by the requirement that
  those cells carry `unmeasured_reason` rather than a score.
- *The sandbox becomes permanent.* Mitigated by `mctl.ai/teardown-after` being
  mandatory in the same commit that enables the sandbox, by the greppable
  `mctl.ai/purpose: issue-903-spike` label, and by the ADR's own `Abandoned`
  status path if the spike is dropped rather than concluded.
- *A candidate double-scrape recreates `#1159`.* Mitigated by the per-candidate
  values requirement to disable chart `ServiceMonitor`/`PodMonitor` presets, and
  detectable with the runbook's existing
  `count by (pod) (otelcol_receiver_accepted_spans)` check.
- *The producer-isolation test is mistaken for a real outage.* Mitigated by
  declaring the scale-to-zero in the window declaration, since
  `OtelCollectorExportFailures` and `OtelCollectorQueueNearFull` will fire to
  Telegram by design.
- *A Cloud candidate's credential leaks into git.* Mitigated by the existing
  `${env:...}`-only rule on `backends[].headers`, and by the fact that the
  poisoned fixture plus the collector's `blocked_values` already exercise the
  credential-shape path.
- *The rubric amendment for candidate F is read as retrofitting.* Mitigated by
  landing it as its own commit, before any score exists, leaving weights and the
  decision rule byte-identical, and recording the amendment and its rationale in
  the ADR.
- *Teardown leaves orphans.* Mitigated by an explicit post-teardown verification
  of Applications, namespace, PVCs and Vault paths, and by the fact that
  `prune: true` plus the ArgoCD resources finalizer is already set on every
  `otel-eval-*` Application.
