# Run the live tracing backend bake-off and record the decision

## Context

`mctlhq/mctl-gitops#903` has landed. Everything it owned is merged and inert in
this repository: the frozen rubric (`docs/adr/0001-rubric.yaml`), the ADR
skeleton with an unfilled Decision section
(`docs/adr/0001-agent-execution-trace-backend.md`), the two representative
DevLoop trace fixtures (`tests/fixtures/devloop-trace.json` and
`devloop-trace-redaction.json`), the fixture emitter
(`platform-gitops/argo-workflows/cluster-templates/wft-otel-trace-fixture.yaml`
plus its materialized ConfigMap at
`platform-gitops/argo-workflows/config/otel-trace-fixture-configmap.yaml`), the
generalized collector fan-out (`otelCollector.backends` in
`platform-gitops/bootstrap/values.yaml`, rendered by
`platform-gitops/bootstrap/templates/observability/otel-collector.yaml`), and
the gated evaluation namespace and candidate Applications
(`bootstrap/templates/observability/eval-namespace.yaml`,
`eval-candidates.yaml`, both behind `otelCollector.eval.enabled: false`). None
of it has ever run: `otelCollector.backends` is `[]`, `otelCollector.eval` is
`{enabled: false, teardownAfter: "", candidates: []}`, every score cell in the
rubric is `null`, and the ADR still carries `<!-- VERDICT: UNFILLED -->`.

This proposal is the other half — the half that needs a live cluster. It turns
the gates on, deploys the candidates that survive a *verified* Stage A screen,
fans the collector out to them, runs a soak whose window and volume are
declared in a commit *before* any measurement, fills every rubric cell from an
observation (or records honestly that a cell could not be measured), selects
exactly one permitted verdict, promotes that decision into the ADR and
`docs/runbooks/otel-collector.md`, and tears the sandbox down. It also carries
the newly added candidate F (Grafana Agent Observability / `agento11y`, added
to the issue on 2026-09-24) into the comparison — which the merged rubric does
not yet list, and therefore cannot silently absorb. The value is that the one
values key `otelCollector.backendEndpoint`, empty since `#902` with the comment
"Empty until a trace backend is chosen", finally gets an answer backed by
measurements taken on this cluster rather than by vendor copy.

## User stories

- AS a platform operator I WANT every trace-backend candidate deployed into one
  disposable, network-isolated namespace SO THAT evaluating five-plus products
  cannot damage or outlive the running platform.
- AS a platform operator I WANT the collector to fan the identical enriched,
  redacted span stream to every candidate at once SO THAT differences in the
  candidates' UIs are differences in the products, not in their inputs.
- AS a reviewer of the ADR I WANT the soak window and trace volume declared in
  a commit that predates every score SO THAT nobody can pick a measurement
  window that flatters a preferred candidate.
- AS a reviewer of the ADR I WANT a rubric cell that could not be measured to
  say so SO THAT an unmeasured dimension is never laundered into a numeric
  score that a weighted total then treats as fact.
- AS a security reviewer I WANT the poisoned fixture replayed into every
  candidate SO THAT the privacy dimension is scored by searching each
  candidate's own store for credential-shaped strings rather than by trusting
  its documentation.
- AS an engineer on call I WANT producer isolation demonstrated by scaling a
  candidate to zero SO THAT adopting a backend cannot make span production a
  new failure path for DevLoop runs.
- AS a FinOps owner (`mctlhq/.github#48`) I WANT token and cost evidence only
  from correctly exported telemetry SO THAT a backend is not credited with
  visibility it never actually received.
- AS the next person to read this repository I WANT every non-selected
  candidate and the sandbox gone SO THAT an evaluation namespace does not
  quietly become permanent infrastructure.

## Acceptance criteria (EARS)

### Preconditions and gating

- WHEN the bake-off begins THE SYSTEM SHALL record, in the ADR, the resolved
  state of each declared precondition: `mctlhq/mctl-gitops#1332` (collector
  redaction masking `gen_ai.usage.*_tokens`), `mctlhq/mctl-agent#38` / PR #137,
  `mctlhq/mctl-agents#195` / PR #466, and `mctlhq/mctl-agent#139`.
- IF `mctlhq/mctl-gitops#1332` is not fixed and verified at the moment the soak
  window opens THEN THE SYSTEM SHALL mark every token, cost and usage cell of
  the `ai_agent_observability` dimension as unmeasured with that issue named as
  the reason, and SHALL NOT assign those cells a numeric score.
- IF the merged producer instrumentation from `mctlhq/mctl-agent#38` and
  `mctlhq/mctl-agents#195` is not live on this cluster when the soak window
  opens THEN THE SYSTEM SHALL run the soak on the committed fixtures alone and
  SHALL record, per affected cell, that the evidence is fixture-derived rather
  than production-derived.
- WHILE any precondition is unresolved THE SYSTEM SHALL still permit namespace,
  manifest and pin preparation, and SHALL NOT permit the ADR verdict to be
  filled.
- WHEN the `#1332` fix is verified THE SYSTEM SHALL demonstrate it with a test
  asserting that an attribute named `gen_ai.usage.input_tokens` survives the
  collector's `redaction` processor while an attribute named `github_token` is
  still masked.

### Stage A resolution and candidate set

- WHEN a candidate carries the Stage A verdict `UNVERIFIED` in
  `docs/adr/0001-rubric.yaml` THE SYSTEM SHALL either resolve its row to
  `SURVIVES` with a verified license, chart or image coordinate and a pinnable
  version, or resolve it to `SCREENED-OUT` with a recorded reason, before any
  cluster capacity is allocated to it.
- IF a candidate cannot ingest plain OTLP without a vendor SDK or
  vendor-specific instrumentation in producer code THEN THE SYSTEM SHALL
  resolve that candidate to `SCREENED-OUT` against the Stage A portability
  gate, because no candidate-specific SDK may be added to `mctl-agent` or
  `mctl-agents`.
- WHEN candidate F (Grafana Agent Observability / `agento11y`) is carried into
  the live comparison THE SYSTEM SHALL first add it to `candidates` and to every
  `dimensions[].candidates` map in `docs/adr/0001-rubric.yaml`, as two
  separately scored shapes — `agento11y-self-managed` and `agento11y-cloud` —
  in a commit that predates any non-null score.
- WHILE the rubric is being widened for candidate F THE SYSTEM SHALL leave every
  dimension key, weight, `cell_scale` level, `tie_margin`, `tie_break` and
  `decision_rule` branch byte-identical to the merged values, so the freeze
  guarantee applies to the scoring instrument and not merely to the file.
- WHEN candidate F's permitted outcomes are added THE SYSTEM SHALL extend
  `permitted_verdicts` explicitly and in the same pre-scoring commit, so the
  decision still selects from a closed list fixed before any score exists.
- WHEN the bake-off states its conclusion on `agento11y` THE SYSTEM SHALL state
  explicitly whether it can observe the production `claude-agent-sdk` DevLoop
  execution path without introducing a Grafana-specific application dependency,
  and IF it cannot THEN THE SYSTEM SHALL record that limitation and score the
  approach accordingly rather than omitting it.
- WHILE candidate F is under evaluation THE SYSTEM SHALL treat
  `mctlhq/mctl-agents#197` / `#198` runtime policy and approval as the
  authoritative governance boundary, and SHALL NOT score Grafana guards as a
  substitute for it.

### Sandbox

- WHEN `otelCollector.eval.enabled` is set to `true` THE SYSTEM SHALL set
  `otelCollector.eval.teardownAfter` to a concrete date in the same commit.
- WHILE `observability-eval` exists THE SYSTEM SHALL enforce a `ResourceQuota`
  and a `LimitRange` on it, so that a ClickHouse- or Postgres-backed candidate
  cannot exhaust the three `cx43` worker nodes.
- WHILE `observability-eval` exists THE SYSTEM SHALL keep its default-deny
  NetworkPolicy set intact, admitting ingress only from the `monitoring`
  namespace on ports 4317 and 4318.
- IF a candidate requires egress to a service outside the cluster THEN THE
  SYSTEM SHALL record that requirement as a scored cost against
  `data_ownership_portability`, and SHALL either add a narrowly scoped,
  reviewed, single-destination egress NetworkPolicy for exactly that candidate
  or mark the affected cells unmeasured — never relax `allow-cluster-egress`
  namespace-wide.
- WHEN a candidate's Helm values are written THE SYSTEM SHALL disable that
  chart's own `ServiceMonitor` and `PodMonitor` presets, because vmagent runs
  `selectAllByDefault: true` and would otherwise double-scrape the candidate
  (incident `#1159`).
- WHILE a candidate is deployed THE SYSTEM SHALL keep ArgoCD `selfHeal`
  disabled for it, so the producer-isolation test can scale it to zero
  replicas without ArgoCD reverting the change mid-measurement.

### Fan-out and soak

- WHEN a candidate is confirmed healthy in `observability-eval` THE SYSTEM
  SHALL add exactly one `otelCollector.backends` entry for it, pointing at its
  in-cluster service on port 4317.
- WHILE fan-out is active THE SYSTEM SHALL route every candidate exporter
  through the single existing traces pipeline, so all candidates receive spans
  that passed the identical `k8sattributes`, `resource`, `redaction`,
  `filter/health` and `batch` processors.
- IF a `backends[]` entry needs an authorization header THEN THE SYSTEM SHALL
  express it only as a `${env:...}` expansion sourced from Vault via an
  ExternalSecret, and SHALL NOT commit a literal credential.
- WHEN the soak window opens THE SYSTEM SHALL have already committed its start
  time, end time, `rate_per_second`, `duration_minutes`, `execution_count` and
  fixture set into `docs/adr/0001-rubric.yaml`, in a commit whose tree contains
  no non-null score cell.
- WHILE the soak runs THE SYSTEM SHALL send both `devloop-trace.json` and
  `devloop-trace-redaction.json` to every candidate via the `otel-trace-fixture`
  ClusterWorkflowTemplate.
- IF the declared soak window has to be extended or restarted THEN THE SYSTEM
  SHALL amend the declaration in a new commit stating the reason, and SHALL NOT
  silently reuse measurements taken outside the declared window.

### Measurement

- WHEN the `operations` dimension is scored THE SYSTEM SHALL derive it from
  VictoriaMetrics series observed during the declared window — candidate CPU,
  memory, persistent-volume growth and restart counts — and never from vendor
  documentation.
- WHEN ingest reliability is assessed THE SYSTEM SHALL cite the collector's own
  per-exporter series `otelcol_exporter_send_failed_spans`,
  `otelcol_exporter_queue_size` and `otelcol_exporter_queue_capacity`, labelled
  by `exporter="otlp/<candidate>"`.
- WHEN the `security_privacy` dimension is scored THE SYSTEM SHALL do so by
  searching each candidate's own store and UI for the credential-shaped strings
  present in `tests/fixtures/devloop-trace-redaction.json` and recording whether
  any is retrievable.
- WHEN producer isolation is measured THE SYSTEM SHALL scale one candidate to
  zero replicas during the window and SHALL record whether
  `otelcol_receiver_refused_spans` rose and whether the remaining candidates
  continued to receive spans.
- WHEN every measurement is complete THE SYSTEM SHALL fill each
  `dimensions[].candidates[]` cell with either an integer score on the merged
  0-5 `cell_scale` plus a one-line evidence citation, or a recorded
  `unmeasured_reason`, and SHALL NOT leave a cell with neither and SHALL NOT
  give a cell both.
- WHILE any cell of a candidate is unmeasured THE SYSTEM SHALL state that
  candidate's weighted total as a bounded range rather than as a single number,
  and SHALL name the unmeasured dimensions alongside it.

### Decision, promotion and teardown

- WHEN the rubric is fully filled THE SYSTEM SHALL evaluate the merged
  `decision_rule` branches in order and SHALL select exactly one entry from
  `permitted_verdicts`.
- IF two candidates' weighted totals fall within the merged `tie_margin` of 25
  points THEN THE SYSTEM SHALL apply the merged `tie_break` and prefer the
  smaller new operational dependency surface on this cluster.
- IF no verdict can be justified from the filled rubric THEN THE SYSTEM SHALL
  select `CONTINUE COMPARISON with an explicit unresolved blocker` and name
  exactly one blocker in the ADR's Decision section.
- WHEN the verdict is recorded THE SYSTEM SHALL set `verdict` in
  `docs/adr/0001-rubric.yaml`, replace the ADR's Decision section, remove the
  `<!-- VERDICT: UNFILLED -->` marker, and move the ADR status from `Proposed`
  to `Accepted` in the same commit.
- WHEN the verdict is recorded THE SYSTEM SHALL update
  `docs/runbooks/otel-collector.md` so that its "Swapping the backend" and
  "The evaluation namespace and the fixture emitter" sections describe the
  selected backend's steady-state operation rather than a pending spike.
- WHEN the ADR is `Accepted` THE SYSTEM SHALL have converted
  `tests/test_adr_rubric_frozen.py` from a freeze assertion into a post-decision
  consistency assertion covering the same file pair, rather than deleting it.
- WHEN the decision is recorded THE SYSTEM SHALL remove every non-selected
  candidate's entry from `otelCollector.eval.candidates` and
  `otelCollector.backends`, set `otelCollector.eval.enabled` back to `false`,
  and confirm that the `observability-eval` namespace and every `otel-eval-*`
  ArgoCD Application are gone.
- IF a candidate is selected for adoption THEN THE SYSTEM SHALL relocate it out
  of `observability-eval` into a permanent home under
  `platform-gitops/infra-components/observability/` with its own Application,
  before the sandbox is deleted.
- WHEN teardown is complete THE SYSTEM SHALL verify that no persistent volume,
  object-storage bucket or Vault path created for a non-selected candidate
  remains.

## Out of scope

- Fixing `mctlhq/mctl-gitops#1332` itself. This proposal gates on that fix and
  verifies it; the redaction-pattern change is that issue's own change.
- Shipping the producer instrumentation in `mctlhq/mctl-agent#38` /
  `mctlhq/mctl-agents#195`, or performing the `mctlhq/mctl-agent#139` cluster
  rollout. This proposal consumes those when available and degrades to
  fixture-only evidence when not.
- Re-opening the rubric's dimensions, weights, `cell_scale`, `tie_margin`,
  `tie_break` or `decision_rule`. Those are frozen by `#903` and this proposal
  only widens the candidate axis.
- Defining the FinOps usage and cost contract. Per `mctlhq/.github#48` the
  selected backend is not automatically the financial source of truth; this
  proposal only records the boundary.
- Enabling the collector's `logs` and `metrics` pipelines, which remain `null`
  by design in phase 1.
- Building a Grafana dashboard suite for whichever backend wins. Adoption and
  dashboard work follow the ADR; they are not part of the bake-off.
- Multi-cluster rollout. `platform-gitops/bootstrap/values.yaml` describes the
  single `mctl-preprod` cluster ArgoCD reconciles here.

## Open questions

- **Candidate F is not in the frozen rubric.** The merged rubric's `candidates`
  list is exactly `[traceway, tempo, langfuse, phoenix, signoz]`, and
  `permitted_verdicts` is deliberately described as a closed list "so the later
  decision cannot invent an eighth option". The issue then asks for candidate F.
  These cannot both hold literally. Proceeding interpretation: widen the
  candidate axis and `permitted_verdicts` in one reviewed commit that lands
  before any score exists, leaving dimensions, weights and the decision rule
  untouched, and record the amendment in the ADR. A reviewer who believes the
  rubric must stay literally closed should say so on the pull request, in which
  case candidate F is screened as an appendix that informs but does not score.
- **Six candidates over two shapes on three `cx43` workers.** Running Tempo,
  Langfuse (ClickHouse plus Postgres plus Redis plus blob storage), SigNoz
  (ClickHouse), Phoenix, Traceway and an `agento11y` path concurrently may not
  fit. Proceeding interpretation: deploy in waves sharing one declared soak
  window per wave, and declare the wave boundaries with the window. Whether
  waves are acceptable, or whether the candidate set should instead be cut, is
  a reviewer call.
- **Grafana Cloud egress.** The `observability-eval` namespace denies public
  internet egress by design (`eval-namespace.yaml`, `allow-cluster-egress`
  permits only DNS and RFC1918). The Cloud shape of candidate F cannot be
  measured live without a carve-out. Proceeding interpretation: attempt a
  single-destination egress policy for that one candidate; if it is refused on
  review, score the Cloud shape's measurable cells from the self-managed shape
  where they coincide and mark the rest unmeasured.
- **ADR numbering.** `#903` recorded that whether `mctlhq/.github#55` intends an
  org-wide ADR sequence (making this ADR-011) or a per-repo sequence starting at
  0001 is unstated. Proceeding interpretation: keep
  `docs/adr/0001-agent-execution-trace-backend.md`; a renumber remains a
  `git mv` and a link fix.
- **Soak length and volume.** The issue requires the window be declared, not
  what it should be. Proceeding interpretation: a 72-hour window, with the
  fixture emitter at the template defaults scaled to produce a stated total
  span count, plus whatever live producer traffic exists. The exact numbers are
  set in the declaration commit and are a reviewer call at that point.
- **Traceway identity.** Stage A could not verify that Traceway exists as a
  locatable project. If `#1280` cannot resolve a license and a pinnable
  artifact, it is screened out with that reason rather than left pending.
