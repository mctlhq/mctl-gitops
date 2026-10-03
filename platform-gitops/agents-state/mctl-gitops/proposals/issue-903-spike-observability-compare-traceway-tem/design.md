# Design: issue-903-spike-observability-compare-traceway-tem

## Current state

### The producer boundary exists and is already vendor-neutral

`platform-gitops/bootstrap/templates/observability/otel-collector.yaml`
deploys a gateway-mode OpenTelemetry Collector (chart
`opentelemetry-collector` 0.173.0, image
`otel/opentelemetry-collector-contrib:0.160.0`, `replicaCount: 2`) into
`monitoring` as an ArgoCD `Application` with `automated.prune` and
`selfHeal: true`. Its traces pipeline is:

```
receivers: [otlp]  ->  memory_limiter, k8sattributes, resource, redaction,
                       filter/health, batch  ->  exporters: [debug]
```

Three parts of that file matter for this proposal:

1. **The exporter block is already values-templated but scalar.**

   ```yaml
   {{- if .Values.otelCollector.backendEndpoint }}
   otlp/backend:
     endpoint: {{ .Values.otelCollector.backendEndpoint | quote }}
     sending_queue: {enabled: true, num_consumers: 4, queue_size: 5000}
     retry_on_failure: {enabled: true, initial_interval: 5s,
                        max_interval: 30s, max_elapsed_time: 300s}
   {{- end }}
   ```

   with the matching conditional inside
   `service.pipelines.traces.exporters`. `platform-gitops/bootstrap/values.yaml`
   sets `otelCollector.backendEndpoint: ""` and comments "Empty until a trace
   backend is chosen". One endpoint, not a list — so it cannot feed a
   comparison.

2. **The `redaction` processor is the single safety-critical block**, running
   `allow_all_keys: true` with `blocked_key_patterns` covering
   authorization/cookie/api-key/token/secret/password/credential names,
   `^vault\..*`, `^gen_ai\.(prompt|completion).*`, `.*\.messages$`,
   `^mcp\.tool\.(arguments|result)$`, `^db\.statement$` and
   `^http\.(request|response)\.header\..*`, plus `blocked_values` matching
   `ghp_[A-Za-z0-9]{36}`, `gh[pousr]_[A-Za-z0-9]{20,}`, `sk-[A-Za-z0-9]{20,}`,
   `hvs\.[A-Za-z0-9]{20,}` and a JWT prefix. There is exactly one copy of it.

3. **`resource` uses `action: insert`, never `upsert`**, so a producer's own
   `k8s.cluster.name` / `deployment.environment` wins. The runbook
   (`docs/runbooks/otel-collector.md`) states this is deliberate and must not
   be changed.

`platform-gitops/infra-components/observability/otel-collector/networkpolicy.yaml`
allows 4317/4318 ingress from `admins`, `mctl-api`, `argo-workflows`,
`temporal`, `monitoring` and any namespace labelled `mctl.me/tenant`, with a
second rule granting `monitoring` access to :8888 for the vmagent scrape. The
`podSelector` matches the collector's own pods only, with an in-file comment
explaining that `{}` would convert the whole policy-free `monitoring`
namespace into an allowlist and cut off Grafana, VMSingle, vmagent and Loki.

`platform-gitops/infra-components/observability/vm-rules/otel-collector-alerts.yaml`
already alerts on `otelcol_receiver_refused_spans`, export failures and queue
depth; those are per-exporter series, so they keep working unchanged and start
naming which candidate is unhealthy the moment a second exporter exists.

### What already exists to build tests on

`.github/workflows/validate-manifests.yml` is the gate. It helm-lints the
internal charts, renders every `platform-gitops/services/*/*/values.yaml` and
the `bootstrap` and `argocd` charts through `kubeconform -strict`, runs
`kubeconform` directly over `platform-gitops/{tenants,argo-workflows,mcp,infra-components}`,
and then runs a long list of Python checks — most of them with a `--selftest`
first, on the stated principle that "a detector that has never been seen to
fire is not known to work". Two are OTEL-specific and are the direct model for
the tests here:

- `tests/test_base_service_otel_env.py` — shells out to `helm template`,
  parses the rendering with `yaml.safe_load_all`, accumulates failures in a
  list and exits non-zero with `FAIL:` lines. No pytest, no framework; plain
  `python3 tests/<file>.py`.
- `tests/test_otel_collector_alert_windows.py` — pure YAML parsing of a
  committed manifest, same output convention.

`scripts/materialize-openclaw-platform-skills.py` establishes the
generate-then-`--check` pattern for a file that must exist in two places (a
source of truth and a rendered copy), with CI running `--check` so a hand edit
that leaves the copy stale fails the build.

`scripts/validate-shell-param-interpolation.py` refuses any new
`{{inputs.parameters.X}}` / `{{workflow.parameters.X}}` interpolated into a
script body in `platform-gitops/argo-workflows/cluster-templates/`, with a
frozen `BASELINE` that may shrink and never grow. Any new workflow template
must bind parameters through `env:` and read them as `"$PARAM_X"`.

`platform-gitops/bootstrap/templates/core-infra/argo-workflows-config.yaml`
syncs `path: platform-gitops/argo-workflows` into the `argo-workflows`
namespace, which is how a ConfigMap committed under
`platform-gitops/argo-workflows/config/` becomes mountable by a workflow pod.

`platform-gitops/helm-charts/tenant/templates/networkpolicy.yaml` shows the
house layering for a namespace that is created and owned by the same chart:
`default-deny-all` with `podSelector: {}`, then `allow-intra-namespace`, then
an explicit cluster-egress allowance. That shape is correct precisely because
the namespace comes into existence with the policies, which is the situation
`observability-eval` will be in and `monitoring` is not.

### What is missing

- No way to send the same spans to more than one backend.
- No representative trace. `mctlhq/mctl-agent#38` and `mctlhq/mctl-agents#195`
  have not shipped, so no DevLoop emits spans at all; the collector's
  `otelcol_receiver_accepted_spans` is zero in practice.
- No `docs/adr/`. `docs/` holds `plans/`, `runbooks/`, `soc2/` only.
- No rubric, no screen, nowhere to record a decision.
- No evaluation namespace or any manifest shape for a disposable candidate.

### The boundary this proposal works inside

The issue's 2026-09-19 note scopes this DevLoop to mctl-gitops repository
artifacts and assigns every live-cluster step to `mctlhq/mctl-gitops#1280`.
So the design question is not "how do we run the spike" but **"what can be
merged now such that running the spike later is a values edit and a review of
already-merged manifests"** — and such that merging it today does nothing.

## Proposed solution

Seven artifacts, all in one PR, all inert on merge.

### 1. Generalize the exporter list (backwards compatible, default no-op)

In `bootstrap/templates/observability/otel-collector.yaml`, keep the existing
`{{- if .Values.otelCollector.backendEndpoint }}` block untouched and add a
loop beside it:

```yaml
exporters:
  debug:
    verbosity: normal
  {{- if .Values.otelCollector.backendEndpoint }}
  otlp/backend:
    # ... unchanged
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

with the mirrored `{{- range }}` in `service.pipelines.traces.exporters`, and
`backends: []` added under `otelCollector` in `bootstrap/values.yaml`.

Why this shape:

- **One pipeline, one redaction processor, N exporters.** Exporters in a
  collector pipeline fan out independently: a slow or failed exporter drains
  into its own `sending_queue` and drops on full; it does not stall the
  receiver or its siblings. That is exactly the "backend outage does not break
  producer workloads" criterion, and the existing per-exporter alert series
  keep working. Running five collectors instead would mean five copies of the
  redaction block — the one block in this repo that must never drift.
- **Not a `routing` connector.** Routing sends *different* spans to different
  backends. A comparison needs identical input. Routing becomes interesting
  only after the verdict, in outcome 2.
- **`headers` holds `${env:...}` expressions, never literals.** A candidate
  needing HTTP Basic or a bearer token gets a Vault path, an `ExternalSecret`
  in `infra-components/observability/otel-collector/` (the pattern used by
  `infra-components/observability/secrets/loki-minio-externalsecret.yaml`) and
  the chart's `extraEnvsFrom`. The credential never enters git; the values
  entry carries only the expansion expression.
- **The legacy scalar stays.** `docs/runbooks/otel-collector.md` documents the
  one-key swap in four numbered steps; silently removing the key it names
  would falsify a runbook that an operator reads under pressure. Both keys
  render if both are set, and the runbook is updated to say so.

`otelCollector.backends` defaults to `[]`, so the rendered ConfigMap is
byte-identical to `main` until an operator changes values under #1280.

### 2. Evaluation manifests, gated off

Two new gated templates under `bootstrap/templates/observability/`:

- `eval-namespace.yaml` — `{{- if .Values.otelCollector.eval.enabled }}`
  renders the `observability-eval` Namespace with
  `mctl.ai/purpose: "issue-903-spike"` and
  `mctl.ai/teardown-after: {{ .Values.otelCollector.eval.teardownAfter }}`,
  plus the three-policy layering copied from
  `helm-charts/tenant/templates/networkpolicy.yaml`: `default-deny-all`
  (`podSelector: {}` — correct here because this chart creates the namespace),
  `allow-intra-namespace`, DNS/cluster egress, and one explicit ingress rule
  admitting the `monitoring` namespace on the candidate ports. A `{}` selector
  is safe in a namespace this template owns and is the documented hazard in
  `monitoring`, which is why the two namespaces get different treatment and
  the file says so.
- `eval-candidates.yaml` — `{{- range .Values.otelCollector.eval.candidates }}`
  renders one ArgoCD `Application` per entry into `observability-eval`:
  pinned upstream `chart` + `targetRevision` from the entry, optional second
  source `path: platform-gitops/infra-components/observability/eval/<name>`
  rendered **only when the entry sets `manifestsPath`** (an Application
  pointing at a directory that does not exist fails to sync and looks like a
  candidate defect), `syncPolicy.automated.prune: true` with **`selfHeal`
  omitted** so an operator can `kubectl scale --replicas=0` a candidate for
  the outage test without ArgoCD fighting back.

`otelCollector.eval.enabled` defaults to `false` and `candidates` to `[]`, so
merging renders nothing at all.

The candidate list is a values input rather than five hardcoded Applications
because this investigation cannot verify any candidate's current chart
coordinates or license offline (see Stage A below), and four of five would be
deleted at teardown anyway. #1280 fills the list with the survivors' verified
pins; the shape, the namespace, the policies and the sync semantics are
already reviewed by then.

A committed example overlay, `tests/fixtures/otel-eval-candidates.example-values.yaml`,
drives both the render test and a new CI step that pipes the eval rendering
through `kubeconform -strict` — so the manifests are schema-valid in this PR
even though nothing deploys them.

### 3. The representative DevLoop trace fixture

`tests/fixtures/devloop-trace.json` — OTLP/JSON, two executions:

- **Execution 1 (success)**: `devloop.run` root -> `temporal.workflow`
  (`DevLoopWorkflow`) -> `argo.workflow` / `argo.pod` -> `agent.invoke`
  (implementer) -> `gen_ai.chat` model invocation -> two `mcp.tool.call`
  spans -> two `github.request` spans (one read, one write) ->
  `artifact.generate` -> `devloop.outcome` with `mctl.outcome=merged`.
- **Execution 2 (error)**: the same tree with `devloop.outcome` carrying
  `mctl.outcome=needs-triage` and an ERROR span status plus an exception
  event, so error navigation is comparable.

Every correlation attribute from `requirements.md` appears at least once:
`mctl.execution_id`, `mctl.temporal.workflow_id` (shaped like the real
`dev-loop-mctlhq-mctl-telegram-296` ids the MCP tooling uses),
`mctl.temporal.run_id`, `mctl.argo.workflow`, `mctl.argo.pod`,
`mctl.agent.role`, `mctl.workflow.stage`, `mctl.repository`,
`mctl.github.issue`, `mctl.github.pr`, `mctl.outcome`, `gen_ai.system`,
`gen_ai.request.model`, `gen_ai.usage.{input,output,cache_read_input,reasoning}_tokens`,
`mcp.tool.name`, `mctl.cost.usd`.

`tests/fixtures/devloop-trace-redaction.json` — the poisoned variant carrying
`gen_ai.prompt.0.content`, `mcp.tool.arguments`,
`http.request.header.authorization` and `mctl.artifact.note` whose value is
`ghp_` + 36 characters. This is not a secret: it is a syntactically valid but
fabricated token shape whose only purpose is to match
`blocked_values[0]`. A test asserts each of the four is matched by at least one
pattern actually present in the committed collector config, so the fixture and
the redaction rules cannot drift apart.

### 4. The emitter, committed but not scheduled

`platform-gitops/argo-workflows/cluster-templates/wft-otel-trace-fixture.yaml`
— a `ClusterWorkflowTemplate` named `otel-trace-fixture` following the
conventions of `cwft-argo-local-workdir-canary.yaml`: a
`workflows.argoproj.io/description` annotation, `serviceAccountName:
argo-workflow-sa`, `activeDeadlineSeconds`, `ttlStrategy`, and a non-root
container with `allowPrivilegeEscalation: false` and `capabilities.drop:
["ALL"]`. Parameters `rate_per_second`, `duration_minutes`,
`execution_count` and `fixture` are bound through `env:` and read as
`"$RATE_PER_SECOND"` etc. — never interpolated into the script body, so
`scripts/validate-shell-param-interpolation.py` stays green with no new
BASELINE entry. It POSTs to
`http://otel-collector.monitoring.svc.cluster.local:4318/v1/traces`, which
needs no NetworkPolicy change because `argo-workflows` is already an allowed
source namespace.

The fixture bytes reach the pod by ConfigMap. To avoid two divergent copies,
`scripts/materialize-otel-trace-fixture.py` generates
`platform-gitops/argo-workflows/config/otel-trace-fixture-configmap.yaml`
from `tests/fixtures/*.json`, and CI runs it with `--check` — the same
generate-and-check contract
`scripts/materialize-openclaw-platform-skills.py --check` already has in
`validate-manifests.yml`. The ConfigMap lands in `argo-workflows` because that
is the namespace `argo-workflows-config` syncs into and the namespace the
emitter pod runs in.

A registered `ClusterWorkflowTemplate` executes nothing. There is deliberately
no CronWorkflow: submission is #1280's job.

### 5. The frozen rubric

`docs/adr/0001-rubric.yaml`, machine-readable:

| Dimension | Weight |
|---|---|
| Trace reconstruction | 25 |
| AI/agent observability | 25 |
| Data ownership / portability | 20 |
| Operations | 15 |
| Security / privacy | 10 |
| Evals / quality loop | 5 |

Each cell is scored 0-5 with a written definition per level and a mandatory
one-line evidence citation; weighted total out of 500; tie margin 25 points,
broken in favour of the smaller new operational dependency surface on this
cluster — which, given that no ClickHouse runs anywhere in
`platform-gitops/infra-components/data/`, is a decidable criterion rather than
a taste judgement.

Decision rule, four branches:

1. One candidate wins outright on both trace reconstruction and AI/agent
   observability and is not last on operations -> **single backend**.
2. Else the best general trace store and the best AI specialist each win their
   own axis by more than the tie margin and their combined measured footprint
   fits the cluster -> **general trace store + AI specialist**, the specialist
   explicitly not the FinOps source of truth.
3. Else no candidate's AI/agent score exceeds by more than one point what the
   existing `openclaw-llm-usage` dashboard pattern
   (`infra-components/observability/grafana-dashboards/openclaw-llm-usage-dashboard-configmap.yaml`)
   already delivers -> **ADOPT TEMPO / mctl-native only**. This is the
   deliberate default when the spike is inconclusive: one values key, one
   Grafana datasource ConfigMap, one bucket, trivially reversible.
4. Else **CONTINUE COMPARISON** with one named blocker.

The whole point of merging this before any candidate is deployed is that the
rubric cannot then be retrofitted to a favourite. A test asserts the weights
sum to 100, that the Markdown table in the ADR and the YAML agree, and that
every score cell is null in this PR.

### 6. Stage A paper screen, with honesty about evidence

The same rubric file carries a `stage_a` block, one row per candidate:
license of the self-hostable artifact, deployment path and pinnable version,
stateful dependency list, whether plain OTLP (not a vendor SDK, not
OpenInference-only) is a supported ingestion path, raw-data export, footprint
claim — and for each, an `evidence` field plus a verdict of `SURVIVES`,
`SCREENED-OUT` or `UNVERIFIED`.

The critical rule, enforced by a test: a row whose evidence is
`issue-903-body` may not be marked `SURVIVES` on a load-bearing deployment
claim. Traceway is the clearest case — it appears nowhere in this clone and
the issue text is the only source, so it is recorded `UNVERIFIED` and #1280
resolves it first, before cluster capacity is budgeted for it. Screened-out
candidates keep their row with the reason; the table never loses a candidate.

This is a *paper* screen. It ranks nothing and scores nothing. The ADR says so.

### 7. The ADR skeleton with the verdict deliberately unfilled

`docs/adr/0001-agent-execution-trace-backend.md` creates `docs/adr/` and
contains: status `Proposed`, context (the #902 boundary, the five candidates,
the three architectural outcomes), the rubric table, the Stage A table, the
decision rule, the FinOps boundary from `mctlhq/.github#48` (the backend is
not automatically the financial source of truth; per-DevLoop spend must be
reconstructible without it), the exit procedure, and the seven permitted
verdicts verbatim from the issue.

Its Decision section is exactly:

```markdown
## Decision

<!-- VERDICT: UNFILLED -->

Not yet decided. The live evaluation that produces the scores for the matrix
above is tracked as mctlhq/mctl-gitops#1280. This section is filled by that
issue with exactly one of the seven verdicts listed under "Permitted
verdicts", and this ADR's status moves from Proposed to Accepted at the same
time.
```

A test asserts the `VERDICT: UNFILLED` marker is present, that no score cell
is populated, and that the status is `Proposed` — so an implementer or a later
editor cannot half-fill it and leave a decision that nobody made.

## Alternatives

**Hardcode five candidate Applications with pinned charts now.** Rejected on
verifiability: this investigation has no way to confirm any candidate's
current chart repository, chart version, license or dependency set, and the
repo's own convention is an exact pin with a comment recording the date it was
resolved (`otel-collector.yaml` does exactly this for chart 0.173.0 / image
0.160.0). Committing five unverified pins would put fabricated facts in a
GitOps repo that ArgoCD treats as truth, and four of the five would be deleted
at teardown. The parameterized list plus an example overlay gives the same
review value with none of the invention.

**Deploy the candidates in this PR and let #1280 only measure.** Rejected
because it violates the issue's own boundary — the implementation PR must not
require post-merge production actions — and because a merge that immediately
stands up several ClickHouse/Postgres-backed stacks on three `cx43` workers is
exactly the kind of change that should be a deliberate, separately-reviewed
operator step. The gate (`eval.enabled: false`) makes deploying them a
one-line values edit with its own PR and its own review.

**Skip the fan-out and evaluate candidates one at a time by re-pointing
`backendEndpoint`.** Rejected because serialized evaluation makes the
comparison depend on when each candidate ran — different fixture batches,
different cluster load, no way to prove identical input — and because the
producer-isolation criterion ("a backend outage does not break producer
workloads") is only demonstrable with siblings present: with one exporter,
"the others kept working" is unobservable.

**Put the fixture only in the Argo ConfigMap, or only in `tests/fixtures/`.**
Rejected both ways. ConfigMap-only makes the fixture invisible to the schema
test and hard to diff in review. Fixtures-only leaves the emitter with nothing
to send. The generate-plus-`--check` pattern already proven by
`materialize-openclaw-platform-skills.py` keeps one source of truth and fails
CI on drift.

**Use pytest for the new tests.** Rejected: `tests/` contains seven plain
`python3 tests/<file>.py` scripts that accumulate `failures` and exit
non-zero, invoked one per CI step with a comment explaining what each exists to
catch. Introducing a runner for two new files would be the only pytest
dependency in the repo.

## Platform impact

**Migrations.** None. No CRD, no schema, no data move.

**Backward compatibility.** `otelCollector.backendEndpoint` keeps working
unchanged and stays documented; `backends`, `eval.enabled` and
`eval.candidates` are new keys with inert defaults. The default render is
asserted byte-identical to `main` by a golden-file test, which is the
mechanism that makes "this merge changes nothing" a check rather than a claim.
Every `platform-gitops/services/*/*/values.yaml` renders unchanged — this
proposal does not touch `base-service`.

**Resource impact at merge: zero.** Two new ArgoCD-synced objects appear —
the `otel-trace-fixture` ClusterWorkflowTemplate and its ConfigMap in
`argo-workflows` — and both are inert; a registered template runs nothing and
a ConfigMap of a few KB costs nothing. No pod, no PVC, no namespace.

**Resource impact later, under #1280.** Flipping `eval.enabled` stands up the
candidates. The rubric's operations dimension requires measured footprint from
existing VictoriaMetrics series rather than vendor documentation, and the
namespace carries a teardown date, so an abandoned spike is greppable rather
than silently permanent. Sizing that against three `cx43` workers is #1280's
call, informed by Stage A's dependency lists.

**Risks and mitigations.**

- *A reviewer waves the rubric through and it is later disputed.* Mitigated
  only partly by a test — the test proves the weights are frozen and
  consistent, not that they are right. This is called out in `requirements.md`
  Open questions precisely so the PR review is the moment to argue about it.
- *Fixture attribute names diverge from what #38/#195 actually ship.* The
  fixture would then be wrong in its strings but not in its structure, and
  candidate ranking does not depend on the exact attribute name. The ADR
  records the caveat; re-running against a real execution once the producers
  land is an explicit follow-up in #1280's scope.
- *The poisoned fixture is mistaken for a real leaked credential.* The value
  is fabricated and matches only the shape. The fixture file carries a header
  comment saying so, and a test asserts the value matches
  `blocked_values[0]` in the committed collector config — its entire reason to
  exist. Secret scanners may still flag it; that is noted in the ADR's
  security section and in the file itself.
- *The golden file becomes stale friction.* Any legitimate collector-config
  edit must regenerate it. The test prints the exact regeneration command in
  its failure output, and the friction is the feature: it forces a reviewer to
  look at a diff of the redaction block every time it moves.
- *Someone flips `eval.enabled` without reading #1280.* The gate is one key,
  which is the point, but candidates then deploy into a default-deny namespace
  with no ingress except from `monitoring` and no credentials, so the blast
  radius is contained to `observability-eval` and ArgoCD shows the
  Applications by name. `selfHeal` is omitted so the same operator can scale
  them to zero immediately.
- *A candidate chart's own ServiceMonitor/PodMonitor double-scrapes.* vmagent
  runs `selectAllByDefault: true`; this is incident #1159, already commented
  in `otel-collector.yaml`. The eval Application shape carries the same note,
  and disabling a candidate's built-in monitor preset is a documented
  requirement on #1280's per-candidate manifests rather than something this PR
  can pre-empt for charts it has not seen.
