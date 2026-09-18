# Spike: select the trace backend behind the otel-collector gateway (Traceway vs Tempo vs Langfuse vs Phoenix vs SigNoz)

## Context

Issue #902 already shipped the vendor-neutral producer boundary. A
gateway-mode OpenTelemetry Collector runs in `monitoring`
(`platform-gitops/bootstrap/templates/observability/otel-collector.yaml`),
accepts OTLP on `otel-collector.monitoring.svc.cluster.local:4317/4318`,
enriches spans with `mctl.team` / `mctl.component` / `k8s.*` /
`deployment.environment`, redacts credential-shaped and prompt-shaped
attributes, and exports to exactly one sink: the `debug` exporter, whose
stdout lands in Loki. `platform-gitops/bootstrap/values.yaml:25` holds
`otelCollector.backendEndpoint: ""` — an empty string with a comment that
reads "Empty until a trace backend is chosen". This proposal is the work that
fills that key in, or decides it stays empty.

Issue #903 asks for a comparative, evidence-based selection across five
self-hostable candidates (Traceway, Grafana Tempo, Langfuse, Arize Phoenix,
SigNoz) against three possible architectural outcomes: one backend, a general
trace store plus an AI specialist, or a general trace store only. The hard
constraint is that no candidate-specific SDK may enter `mctl-agent` or
`mctl-agents` — OTLP to the collector stays the only application contract, and
switching or removing a backend must remain the single-values-key edit that
`docs/runbooks/otel-collector.md` documents today. A complication that shapes
the entire spike: the two span producers (`mctlhq/mctl-agent#38`,
`mctlhq/mctl-agents#195`) have **not shipped**, so no real DevLoop trace
exists yet to compare backends with. The comparison must therefore be driven
by a committed, representative synthetic trace fixture rather than by
production traffic, and that fixture must be the same bytes for every
candidate or the comparison proves nothing.

## User stories

- AS a platform operator I WANT the collector to fan the same span stream out
  to several candidate backends at once SO THAT the comparison is apples-to-
  apples and does not require a producer change, a redeploy, or a serialized
  one-candidate-at-a-time schedule.
- AS a platform operator I WANT candidate backends to run in their own
  namespace with their own NetworkPolicy and a declared teardown date SO THAT
  a crashlooping evaluation stack cannot degrade Grafana, VMSingle, Loki or
  the collector itself.
- AS a DevLoop maintainer I WANT to open one execution and see the Temporal
  workflow, the Argo pod, the model invocation, the MCP tool calls, the GitHub
  reads/writes and the terminal outcome as one parent/child tree SO THAT I can
  debug a failed run without stitching Loki queries by hand.
- AS a DevLoop maintainer I WANT to search executions by repository, issue/PR
  number, agent role and outcome SO THAT I can find the run I care about
  without knowing its trace id.
- AS a FinOps owner (`mctlhq/.github#48`) I WANT per-call and per-execution
  token and cost attribution that mctl can reconstruct from its own data SO
  THAT the financial source of truth does not become a proprietary backend's
  pricing table or retention policy.
- AS a security reviewer I WANT prompts, completions, tool arguments, tool
  results and credential-shaped values to be absent from every candidate's
  store SO THAT choosing an observability vendor does not silently create a
  new place where secrets and private Telegram content live.
- AS a platform operator I WANT the CPU, memory and storage cost of each
  candidate measured on this cluster at a known span rate SO THAT the choice
  is sized against three `cx43` workers, not against a vendor's benchmark.
- AS a future maintainer I WANT the outcome recorded as an ADR in
  `docs/adr/` with the scored matrix and the rejected options SO THAT the
  decision can be revisited without repeating the spike.

## Acceptance criteria (EARS)

### Fan-out harness

- WHEN `otelCollector.backends` in `platform-gitops/bootstrap/values.yaml` is
  set to a list of named OTLP endpoints THE SYSTEM SHALL render one
  `otlp/<name>` exporter per entry into the collector's traces pipeline, each
  with its own `sending_queue` and `retry_on_failure` block.
- WHILE `otelCollector.backends` is empty or unset THE SYSTEM SHALL render the
  traces pipeline exactly as it renders today — `exporters: [debug]` only —
  and every `platform-gitops/services/*/*/values.yaml` SHALL continue to
  render byte-identical output.
- IF the legacy scalar `otelCollector.backendEndpoint` is non-empty THEN THE
  SYSTEM SHALL keep honouring it as a single `otlp/backend` exporter, so the
  swap procedure in `docs/runbooks/otel-collector.md` stays correct.
- WHILE more than one backend exporter is configured THE SYSTEM SHALL keep the
  `debug` exporter enabled alongside them, so collector stdout in Loki remains
  an independent source of truth for what was actually sent.
- WHEN a candidate backend requires an authorization header THE SYSTEM SHALL
  source it from a Kubernetes Secret produced by an `ExternalSecret` over a
  Vault path and reference it in the collector config as an `${env:...}`
  expansion, and SHALL NOT contain the credential value in any file in this
  repository.

### Representative execution

- WHEN the evaluation harness is run THE SYSTEM SHALL emit a committed,
  versioned synthetic DevLoop trace fixture containing, as one trace: a
  DevLoop/workflow root span, a Temporal orchestration span, an Argo
  worker/pod span, at least one agent/model invocation span, at least two
  MCP/tool spans, at least two GitHub read/write spans, an artifact-generation
  span and a terminal-outcome span, including at least one error path.
- WHILE the fixture is being emitted THE SYSTEM SHALL send byte-identical OTLP
  payloads to every configured candidate in the same collector pipeline pass,
  so no candidate sees a different input than another.
- WHEN the fixture is emitted THE SYSTEM SHALL populate the correlation
  attributes `mctl.execution_id`, `mctl.temporal.workflow_id`,
  `mctl.temporal.run_id`, `mctl.argo.workflow`, `mctl.agent.role`,
  `mctl.workflow.stage`, `mctl.repository`, `mctl.github.issue`,
  `mctl.github.pr`, `mctl.outcome`, `gen_ai.request.model`,
  `gen_ai.system`, `gen_ai.usage.input_tokens`,
  `gen_ai.usage.output_tokens`, `gen_ai.usage.cache_read_input_tokens`,
  `gen_ai.usage.reasoning_tokens`, `mcp.tool.name` and `mctl.cost.usd`.
- IF the producer issues `mctlhq/mctl-agent#38` or `mctlhq/mctl-agents#195`
  ship before this spike concludes THEN THE SYSTEM SHALL re-run the comparison
  against one real DevLoop execution and record any divergence from the
  fixture result in the ADR.

### Producer isolation

- WHILE any candidate backend is unreachable, crashlooping or scaled to zero
  THE SYSTEM SHALL continue to accept OTLP from producers and SHALL NOT
  propagate backpressure to them; the collector SHALL drop batches on a full
  `sending_queue` rather than block the receiver.
- WHILE any candidate backend is unreachable THE SYSTEM SHALL keep delivering
  spans to every other configured exporter, including `debug`.
- WHEN a candidate is added, swapped or removed THE SYSTEM SHALL require zero
  changes in `mctl-agent` or `mctl-agents`, zero producer restarts and zero
  image rebuilds; the only change SHALL be to
  `platform-gitops/bootstrap/values.yaml` and, for a new candidate, its
  Application manifest.
- IF a candidate backend cannot ingest plain OTLP without a vendor SDK or a
  vendor-specific instrumentation library in producer code THEN THE SYSTEM
  SHALL score that candidate as disqualified on the portability dimension and
  record the reason in the matrix.

### Security and privacy

- WHILE any candidate is receiving spans THE SYSTEM SHALL keep the existing
  `redaction` processor block lists in force, so attributes matching
  `(?i)^gen_ai\.(prompt|completion).*`, `(?i).*\.messages$`,
  `(?i)^mcp\.tool\.(arguments|result)$`, `^db\.statement$`,
  `^http\.(request|response)\.header\..*`, the credential-name pattern and the
  credential-value shapes never leave the collector.
- WHEN the spike verifies privacy THE SYSTEM SHALL emit a span deliberately
  carrying a prompt attribute, a tool-arguments attribute and a benign-named
  attribute whose value is GitHub-token-shaped, and SHALL demonstrate that
  none of the three is retrievable from any candidate's UI, API or export.
- WHILE a candidate is deployed for evaluation THE SYSTEM SHALL confine it to
  a dedicated `observability-eval` namespace with a NetworkPolicy whose
  `podSelector` matches the candidate's own pods and never `{}`.
- IF a candidate requires an externally reachable UI THEN THE SYSTEM SHALL
  expose it only through the existing Traefik + OIDC path used by
  `grafana.mctl.ai`, and SHALL NOT expose an unauthenticated Ingress.

### Measurement and scoring

- WHEN each surviving candidate has ingested the fixture at a fixed, declared
  span rate for a fixed, declared window THE SYSTEM SHALL record its measured
  CPU, memory working set and persistent-storage growth from the existing
  VictoriaMetrics series, not from vendor documentation.
- WHEN the comparison completes THE SYSTEM SHALL produce a scored matrix over
  the six dimensions named in the issue — trace reconstruction, AI/agent
  observability, evals/quality loop, data ownership/portability, operations,
  security/privacy — with published weights, a 0-5 score per cell and a
  one-line evidence citation per cell.
- WHILE a candidate has been eliminated at the paper-screen stage THE SYSTEM
  SHALL record the elimination reason in the matrix rather than omitting the
  candidate, so a reader can see what was screened out and why.
- WHEN scoring is complete THE SYSTEM SHALL emit exactly one of the verdicts
  enumerated in the issue: ADOPT TRACEWAY, ADOPT TEMPO + AI SPECIALIST, ADOPT
  LANGFUSE, ADOPT PHOENIX for eval specialization, ADOPT SIGNOZ, ADOPT TEMPO /
  mctl-native only, or CONTINUE COMPARISON with a named unresolved blocker.
- IF no candidate demonstrates AI/agent observability that materially beats
  mctl-native Grafana dashboards over collector-derived metrics THEN THE
  SYSTEM SHALL select the general-trace-store-only outcome rather than adopt a
  specialist backend on the strength of its demo alone.
- IF two candidates score within the rubric's declared tie margin THEN THE
  SYSTEM SHALL break the tie in favour of the candidate with the smaller new
  operational dependency surface on this cluster.

### Data ownership and exit

- WHEN a candidate is scored on portability THE SYSTEM SHALL document its
  self-hosting license, whether raw spans can be exported in an
  OTLP/OpenTelemetry-compatible form, the retention controls available, and a
  concrete backup/restore path.
- WHEN the cost/FinOps dimension is scored THE SYSTEM SHALL confirm that
  per-DevLoop spend can be reconstructed without the candidate — from
  collector-derived metrics and the `mctlhq/.github#48` usage/cost contract —
  and SHALL record any candidate that would become the only copy of cost data
  as failing that criterion.

### Decision record and teardown

- WHEN the verdict is reached THE SYSTEM SHALL create `docs/adr/` and commit
  an ADR containing the context, the scored matrix, the decision, the rejected
  options with reasons, and the consequences including the exit procedure.
- WHEN the ADR merges THE SYSTEM SHALL remove every non-selected candidate's
  Application, namespace and persistent volumes, and SHALL leave
  `otelCollector.backends` naming only the selected backend, or empty if the
  verdict is general-trace-store-only.
- WHILE the spike is running THE SYSTEM SHALL carry an explicit teardown date
  in the evaluation namespace's annotations, so an abandoned spike is visible
  rather than silently permanent.

## Out of scope

- Instrumenting `mctl-agent` or `mctl-agents` to emit real spans. That is
  `mctlhq/mctl-agent#38` and `mctlhq/mctl-agents#195`; this proposal consumes
  their eventual output and must not pre-empt their attribute design beyond
  proposing the correlation attribute names above as a starting contract.
- Defining the usage/cost contract itself. That is `mctlhq/.github#48`; this
  proposal only verifies that a chosen backend does not become its only home.
- Building mctl-native FinOps dashboards. If the verdict is
  general-trace-store-only, the dashboard work is a follow-up issue, not part
  of the spike.
- Migrating logs or metrics off Loki / VictoriaMetrics. The comparison is
  scoped to traces; a candidate's ability to also store logs and metrics is
  scored as an operational-overlap risk, not as a migration plan.
- Sampling policy. The collector exports every span today
  (`docs/runbooks/otel-collector.md`, "Accepted residuals"); sampling becomes
  a real question only once a volume-billed backend is live.
- Enabling prompt/completion capture. It is off by default for this evaluation
  and stays off; any future opt-in is a separate, separately-reviewed change.
- Multi-cluster or production-grade HA for the selected backend. The spike
  sizes a single-replica or minimal-HA deployment on `mctl-preprod`.

## Open questions

- **Traceway identity.** The issue describes Traceway as MIT-licensed,
  self-hostable, OTLP-native with unified traces/metrics/logs and AI tracing,
  with "compliance certifications still in progress for the managed offering".
  This clone contains no reference to it and the investigation had no network
  access to verify the project, its chart, or its current license. Task 2's
  paper screen must resolve this first; if no self-hostable Helm/Kubernetes
  deployment path with a pinned version can be established, Traceway is
  screened out on operations grounds and that is recorded in the matrix rather
  than treated as an unresolved blocker.
- **Weights.** The issue names six dimensions but not their relative
  importance. This proposal fixes them at trace reconstruction 25, AI/agent
  observability 25, data ownership/portability 20, operations 15,
  security/privacy 10, evals 5 — on the reasoning that portability plus
  operations (35 combined) should outweigh either single feature axis on a
  three-worker cluster, and that evals are the dimension most cheaply deferred
  to a later, separate decision. A reviewer who disagrees should change the
  weights in `tasks.md` task 3 before any scoring happens, not after.
- **Fixture fidelity.** With #38/#195 unshipped, the attribute names in the
  criteria above are this proposal's invention. If those issues land with
  different names, the fixture is wrong but the comparison is not — the
  relative ranking of backends does not depend on the exact string. Proceeding
  on that basis; the ADR must state it explicitly.
- **SigNoz screening depth.** The issue says to "run an architecture/ops-fit
  screen first and decide whether it deserves the same live-trace PoC". This
  proposal applies the same rule uniformly to all five candidates: paper
  screen first, live PoC only for survivors. SigNoz is not special-cased.
- **Evaluation cluster.** `infrastructure/k3s-preview/kube.tf` describes one
  `cx33` control plane and three `cx43` workers, and `bootstrap/values.yaml`
  sets `clusterName: mctl-preprod`. The spike runs there. Whether a
  ClickHouse-backed candidate's measured footprint on preprod predicts a
  production cluster is a question the ADR must answer honestly rather than
  extrapolate silently.
- **Fan-out during the spike only, or permanently?** This proposal generalizes
  `backendEndpoint` to a list because the comparison needs it. Whether outcome
  2 (general store + AI specialist) keeps a permanent two-exporter fan-out, or
  routes by attribute with a `routing` connector, is deferred to the ADR;
  the list form supports both.
