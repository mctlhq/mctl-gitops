# Trace-backend spike harness: frozen rubric, paper screen, DevLoop trace fixtures and collector fan-out (gitops side of #903)

## Context

Issue #902 already shipped the vendor-neutral producer boundary. A
gateway-mode OpenTelemetry Collector runs in `monitoring`
(`platform-gitops/bootstrap/templates/observability/otel-collector.yaml`),
accepts OTLP on `otel-collector.monitoring.svc.cluster.local:4317/4318`,
enriches spans with `mctl.team` / `mctl.component` / `k8s.*` /
`deployment.environment`, redacts credential-shaped and prompt-shaped
attributes, and exports to exactly one sink: the `debug` exporter, whose
stdout lands in Loki via promtail. `platform-gitops/bootstrap/values.yaml`
holds `otelCollector.backendEndpoint: ""` with the comment "Empty until a
trace backend is chosen". Issue #903 is the comparison that fills that key in
— or decides it stays empty — across five self-hostable candidates (Traceway,
Grafana Tempo, Langfuse, Arize Phoenix, SigNoz).

The issue's DevLoop boundary note dated 2026-09-19 splits that work in two.
**This proposal is the mctl-gitops repository half only**: the frozen scoring
rubric, the Stage A paper screen, the representative DevLoop trace fixtures,
the generalized exporter list, the collector fan-out and evaluation manifests,
the render and fixture tests, and an ADR skeleton whose verdict section is
explicitly left unfilled. Everything that requires a live cluster — creating
the evaluation namespace, deploying candidates, turning the fan-out on, the
soak, filling the rubric cells from measurements, writing the verdict and
tearing down — is `mctlhq/mctl-gitops#1280` and is deliberately **not** part of
implementer done-ness. The whole of this proposal is completable in one pull
request against this repository, and merging it changes zero cluster state:
every new manifest is values-gated off by default, and the rendered collector
ConfigMap is byte-identical to `main` until an operator sets a key.

## User stories

- AS a platform operator I WANT the collector to be able to fan the same span
  stream out to several candidate backends at once, configured by values
  alone, SO THAT the later comparison is apples-to-apples and never needs a
  producer change, a redeploy, or a serialized one-candidate-at-a-time
  schedule.
- AS a platform operator I WANT the evaluation namespace, its NetworkPolicies
  and the per-candidate Application shape committed but inert SO THAT the live
  spike under #1280 is a values edit and a review of already-merged manifests,
  not a scramble to author Kubernetes objects under time pressure.
- AS a reviewer I WANT the scoring rubric — dimensions, weights, cell scale,
  tie margin, decision rule — frozen and merged BEFORE any candidate is
  deployed SO THAT the rubric cannot be retrofitted to a favourite after the
  numbers are in.
- AS a reviewer I WANT the Stage A paper screen to state, per candidate, what
  was verified and what was only asserted by the issue text SO THAT an
  unverified claim about a young project is never silently promoted to a
  measured fact.
- AS a DevLoop maintainer I WANT a committed, representative DevLoop trace
  fixture covering the Temporal, Argo, model, MCP/tool, GitHub, artifact and
  outcome spans SO THAT every candidate is later judged on identical input
  even though the real span producers (`mctlhq/mctl-agent#38`,
  `mctlhq/mctl-agents#195`) have not shipped.
- AS a security reviewer I WANT a deliberately poisoned fixture carrying a
  prompt attribute, tool arguments, an authorization header and a
  GitHub-token-shaped value under an innocuous key SO THAT the redaction
  processor's block lists are exercised by an artifact in the repo rather than
  trusted.
- AS a future maintainer I WANT the ADR skeleton merged with the rubric filled
  and the verdict section explicitly marked unfilled SO THAT the decision has
  one home from the start and a half-finished spike is visible rather than
  invisible.

## Acceptance criteria (EARS)

### Fan-out harness (template and values)

- WHEN `otelCollector.backends` in `platform-gitops/bootstrap/values.yaml` is
  set to a list of named OTLP endpoints THE SYSTEM SHALL render one
  `otlp/<name>` exporter per entry into the collector's traces pipeline, each
  with its own `sending_queue` and `retry_on_failure` block, and SHALL list
  each of them in `service.pipelines.traces.exporters`.
- WHILE `otelCollector.backends` is empty or unset THE SYSTEM SHALL render the
  collector ConfigMap exactly as `main` renders it today — `exporters:
  [debug]` only — and every `platform-gitops/services/*/*/values.yaml` SHALL
  continue to render byte-identical output.
- IF the legacy scalar `otelCollector.backendEndpoint` is non-empty THEN THE
  SYSTEM SHALL keep honouring it as a single `otlp/backend` exporter with its
  existing queue and retry settings, so the one-key swap procedure in
  `docs/runbooks/otel-collector.md` stays literally true.
- IF both `otelCollector.backendEndpoint` and `otelCollector.backends` are set
  THEN THE SYSTEM SHALL render both, and `docs/runbooks/otel-collector.md`
  SHALL state that this is the defined behaviour.
- WHILE one or more backend exporters are configured THE SYSTEM SHALL keep the
  `debug` exporter enabled alongside them, so collector stdout in Loki remains
  an independent record of what was actually sent.
- WHEN a candidate entry declares `headers` THE SYSTEM SHALL render them as
  `${env:...}` expansion expressions sourced from the collector pod's
  environment, and THE SYSTEM SHALL NOT contain any credential value in any
  file in this repository.
- WHILE the traces pipeline contains more than one exporter THE SYSTEM SHALL
  keep the single shared `redaction` processor as the only copy of the block
  lists, so no candidate can be fed through a weaker redaction path than
  another.

### Evaluation manifests (committed, inert)

- WHILE `otelCollector.eval.enabled` is false — the committed default — THE
  SYSTEM SHALL render no `observability-eval` Namespace, no candidate
  `Application`, and no evaluation NetworkPolicy, and the full
  `platform-gitops/bootstrap` render SHALL be unchanged from `main`.
- WHEN `otelCollector.eval.enabled` is true and `otelCollector.eval.candidates`
  lists candidates THE SYSTEM SHALL render the `observability-eval` Namespace
  carrying `mctl.ai/purpose: "issue-903-spike"` and a
  `mctl.ai/teardown-after` date annotation, one ArgoCD `Application` per
  candidate targeting that namespace, and the namespace's NetworkPolicy set.
- WHILE any evaluation NetworkPolicy exists THE SYSTEM SHALL scope every
  candidate-ingress rule so that OTLP ingress is permitted only from the
  `monitoring` namespace, and SHALL place the `podSelector: {}` default-deny
  only inside `observability-eval`, never in `monitoring`.
- WHEN a candidate `Application` is rendered THE SYSTEM SHALL pin the upstream
  chart to an explicit `targetRevision` supplied by the values entry, SHALL
  set `syncPolicy.automated.prune: true`, and SHALL omit `selfHeal`, so an
  operator can scale a candidate to zero for the outage test without ArgoCD
  reverting it.
- IF a candidate entry omits `manifestsPath` THEN THE SYSTEM SHALL render a
  single-source Application rather than referencing a repository directory
  that does not exist.
- WHEN the rendered evaluation manifests are validated THE SYSTEM SHALL pass
  `kubeconform -strict` under the same schema locations
  `.github/workflows/validate-manifests.yml` already uses.

### Representative execution fixtures

- WHEN `tests/fixtures/devloop-trace.json` is parsed THE SYSTEM SHALL present
  valid OTLP/JSON containing at least two executions, each one trace with a
  single root, comprising a DevLoop/workflow root span, a Temporal
  orchestration span, an Argo worker/pod span, at least one agent/model
  invocation span, at least two MCP/tool spans, at least two GitHub
  read/write spans, an artifact-generation span and a terminal-outcome span.
- WHILE the fixture set is committed THE SYSTEM SHALL contain at least one
  execution whose terminal outcome is an error, with span status set
  accordingly, so error navigation is comparable across candidates.
- WHEN the fixture is parsed THE SYSTEM SHALL carry the correlation attributes
  `mctl.execution_id`, `mctl.temporal.workflow_id`, `mctl.temporal.run_id`,
  `mctl.argo.workflow`, `mctl.argo.pod`, `mctl.agent.role`,
  `mctl.workflow.stage`, `mctl.repository`, `mctl.github.issue`,
  `mctl.github.pr`, `mctl.outcome`, `gen_ai.system`, `gen_ai.request.model`,
  `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`,
  `gen_ai.usage.cache_read_input_tokens`, `gen_ai.usage.reasoning_tokens`,
  `mcp.tool.name` and `mctl.cost.usd` at least once each.
- WHEN `tests/fixtures/devloop-trace-redaction.json` is parsed THE SYSTEM
  SHALL carry `gen_ai.prompt.0.content`, `mcp.tool.arguments`,
  `http.request.header.authorization` and a benign key `mctl.artifact.note`
  whose value matches the collector's `ghp_[A-Za-z0-9]{36}` blocked value
  shape, and every one of those four SHALL match at least one pattern in the
  collector's committed `redaction` configuration.
- WHILE the emitter `ClusterWorkflowTemplate` exists THE SYSTEM SHALL keep the
  fixture JSON under `tests/fixtures/` as the single source of truth and
  SHALL generate the in-cluster ConfigMap copy from it, with a `--check` mode
  that fails CI when the two diverge.
- IF the emitter template binds any workflow parameter THEN THE SYSTEM SHALL
  bind it through `env:` and read it as a quoted shell variable, and SHALL NOT
  interpolate `{{inputs.parameters.*}}` or `{{workflow.parameters.*}}` into a
  script body, so `scripts/validate-shell-param-interpolation.py` passes with
  no new BASELINE entry.

### Frozen rubric and Stage A screen

- WHEN the rubric file is merged THE SYSTEM SHALL declare six dimensions —
  trace reconstruction, AI/agent observability, data ownership/portability,
  operations, security/privacy, evals/quality loop — with weights summing to
  100, a 0-5 cell scale with written cell definitions, a declared tie margin,
  and the four-branch decision rule.
- WHILE the rubric is merged in this PR THE SYSTEM SHALL contain no score for
  any candidate in any dimension; every cell SHALL be null and every citation
  field SHALL be empty.
- WHEN the rubric is rendered into the ADR skeleton THE SYSTEM SHALL keep the
  weights in the Markdown table and the weights in the machine-readable rubric
  identical, enforced by a test rather than by review.
- WHEN the Stage A paper screen is recorded THE SYSTEM SHALL give each of the
  five candidates a row containing license of the self-hostable artifact,
  deployment path and whether a pinnable version exists, full stateful
  dependency list, whether plain OTLP (not a vendor SDK, not OpenInference
  only) is a supported ingestion path, raw-data export capability, and a
  verdict of `SURVIVES`, `SCREENED-OUT` or `UNVERIFIED`.
- WHILE a Stage A claim rests only on the text of issue #903 THE SYSTEM SHALL
  record its evidence field as the issue rather than as documentation, and
  SHALL mark the candidate `UNVERIFIED` rather than `SURVIVES` where the claim
  is load-bearing for the deployment path.
- WHILE a candidate has been screened out THE SYSTEM SHALL keep its row in the
  matrix with the elimination reason rather than removing the candidate, so a
  reader can see what was rejected and why.
- IF a candidate cannot ingest plain OTLP without a vendor SDK or
  vendor-specific instrumentation in producer code THEN THE SYSTEM SHALL
  record it as failing the Stage A portability gate, because that would
  violate the no-candidate-SDK constraint in `mctl-agent` / `mctl-agents`.

### ADR skeleton

- WHEN the ADR is merged THE SYSTEM SHALL create `docs/adr/` (which does not
  exist today — `docs/` holds only `plans/`, `runbooks/`, `soc2/`) and contain
  context, the frozen rubric, the Stage A screen, the decision rule, the
  FinOps boundary statement, and the exit procedure.
- WHILE the live evaluation under #1280 has not run THE SYSTEM SHALL carry an
  ADR status of `Proposed` and a Decision section containing an explicit
  unfilled marker naming `mctlhq/mctl-gitops#1280` as its owner, and SHALL NOT
  state or imply any verdict.
- WHEN the ADR is merged THE SYSTEM SHALL state that the selected backend is
  not automatically the financial source of truth and that per-DevLoop spend
  must be reconstructible without it, per `mctlhq/.github#48`.
- WHEN the ADR is merged THE SYSTEM SHALL enumerate the seven permitted
  verdicts from issue #903 verbatim, so the later decision selects from a
  closed list rather than inventing one.

### Scope containment

- WHILE this proposal is implemented THE SYSTEM SHALL NOT modify any file
  outside the `mctlhq/mctl-gitops` repository.
- WHEN this PR merges THE SYSTEM SHALL require no operator action for the
  merge to be safe: no namespace is created, no candidate is deployed, no
  exporter is added to the running collector, and no workflow is submitted.
- WHILE the emitter `ClusterWorkflowTemplate` and its fixture ConfigMap are
  synced by ArgoCD THE SYSTEM SHALL leave them inert — a registered template
  runs nothing until submitted — and SHALL NOT add any CronWorkflow.

## Out of scope

- **The live evaluation itself.** Creating `observability-eval`, deploying
  candidates, setting `otelCollector.eval.enabled: true` and
  `otelCollector.backends`, running the emitter, the soak, filling rubric
  cells from PromQL, choosing a verdict and tearing down are
  `mctlhq/mctl-gitops#1280`.
- **The verdict.** This PR must not state one. The ADR's Decision section is
  deliberately unfilled.
- Instrumenting `mctl-agent` or `mctl-agents` to emit real spans
  (`mctlhq/mctl-agent#38`, `mctlhq/mctl-agents#195`). This proposal consumes
  their eventual output and proposes correlation attribute names as a starting
  contract only.
- Defining the usage/cost contract (`mctlhq/.github#48`); this proposal only
  records the boundary in the ADR and makes it testable later.
- Building mctl-native FinOps dashboards, and migrating logs or metrics off
  Loki / VictoriaMetrics.
- Sampling policy. The collector exports every span today
  (`docs/runbooks/otel-collector.md`, "Accepted residuals"); sampling becomes
  a real question only once a volume-billed backend is live.
- Enabling prompt/completion capture. It stays off; any future opt-in is a
  separate, separately-reviewed change.
- Production-grade HA or multi-cluster deployment of any candidate.
- Alert rules for a selected backend. Those follow the verdict, under #1280.

## Open questions

- **ADR numbering.** `docs/adr/` does not exist in this repo, but ADR-007,
  ADR-008 and ADR-010 are referenced throughout it as living in
  `mctlhq/mctl-agents` (`platform-gitops/agent-platform/README.md:4`,
  `wft-lifecycle-bootstrap.yaml:8`). Whether `.github#55` intends one org-wide
  sequence (making this ADR-011) or a per-repo sequence starting at 0001 is
  not stated. This proposal uses `docs/adr/0001-agent-execution-trace-backend.md`
  and records the cross-repo sequence explicitly in the ADR header, so a
  renumber is a `git mv` and a link fix. A reviewer who wants the org-wide
  sequence should say so on the PR.
- **Traceway identity.** Traceway appears nowhere in this clone; the issue text
  is the only evidence available, and this investigation could not verify the
  project, its chart or its license. Stage A therefore records it as
  `UNVERIFIED` with the issue as its evidence, and #1280 resolves it before
  budgeting cluster capacity for it. This is recorded, not blocking.
- **Weights.** The issue names six dimensions but not their relative
  importance. This proposal fixes them at trace reconstruction 25, AI/agent
  observability 25, data ownership/portability 20, operations 15,
  security/privacy 10, evals 5, reasoning that portability plus operations (35
  combined) should outweigh either single feature axis on a three-worker
  cluster, and that evals are the dimension most cheaply deferred to a separate
  later decision. Freezing them in this PR is the whole point: a reviewer who
  disagrees must change them here, before any candidate is deployed.
- **Fixture fidelity.** With #38/#195 unshipped, the attribute names above are
  this proposal's invention. If those issues land with different names the
  fixture is wrong but the comparison is not — the relative ranking of
  backends does not depend on the exact string. The ADR states this explicitly.
- **Fan-out during the spike only, or permanently?** The list form supports
  both a temporary comparison fan-out and outcome 2's permanent general-store
  plus AI-specialist pair. Whether outcome 2 keeps a two-exporter fan-out or
  routes by attribute with a `routing` connector is deferred to the ADR under
  #1280.
- **Golden-file brittleness.** The default-render test compares the collector
  ConfigMap against a committed golden file. Any legitimate future edit to the
  collector config must regenerate it. That is intended friction — the golden
  file is what makes "byte-identical to today" checkable in CI — but it will
  annoy someone eventually, and the test prints the regeneration command for
  that reason.
