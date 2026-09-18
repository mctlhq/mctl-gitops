# Tasks: issue-903-spike-observability-compare-traceway-tem

Tasks 1-3 are paper/repo work and change no cluster state. Task 4 is the only
template change to a live component. Tasks 5-9 deploy and measure. Tasks
10-12 decide, record and tear down. Nothing in this proposal touches
`mctl-agent` or `mctl-agents`.

- [ ] 1. Freeze the scoring rubric before anything is deployed. Add
  `docs/adr/0001-agent-execution-trace-backend.md` as a draft containing only
  the context, the six dimensions with the weights from `design.md`
  (25/25/20/15/10/5), the 0-5 cell definition, the 25-point tie margin, and
  the four-branch decision rule — no scores. Creating this file creates
  `docs/adr/`, which does not exist today (`docs/` holds only `plans/`,
  `runbooks/`, `soc2/`).
  DoD: the draft ADR is merged, a reviewer has had the chance to change the
  weights, and no candidate manifest exists in the repo yet.

- [ ] 2. Stage A paper screen for all five candidates (depends on 1). For
  Traceway, Tempo, Langfuse, Phoenix and SigNoz record, in the ADR's matrix
  section: license of the self-hostable artifact; existence and pinnable
  version of a maintained Helm chart or Kubernetes manifests; full stateful
  dependency list; whether plain OTLP (not a vendor SDK, not OpenInference
  only) is a supported ingestion path; raw-data export capability; and
  measured-or-documented minimum footprint. Resolve Traceway first — it
  appears nowhere in this clone and the issue text is the only evidence.
  DoD: every candidate has a SURVIVES or SCREENED-OUT verdict with a one-line
  reason recorded in the matrix; screened-out candidates stay in the table
  rather than disappearing; the survivor list is explicit and dated.

- [ ] 3. Commit the representative DevLoop trace fixtures (depends on 1, can
  run parallel to 2). Add `tests/fixtures/devloop-trace.json` with the span
  tree from `requirements.md` (DevLoop root, Temporal orchestration, Argo
  worker/pod, agent/model invocation, >=2 MCP/tool spans, >=2 GitHub
  read/write spans, artifact generation, terminal outcome) across at least
  two executions, one of which ends in an error span. Populate every
  correlation attribute listed in `requirements.md`. Add
  `tests/fixtures/devloop-trace-redaction.json` carrying
  `gen_ai.prompt.0.content`, `mcp.tool.arguments`,
  `http.request.header.authorization` and `mctl.artifact.note` whose value is
  `ghp_` followed by 36 characters.
  DoD: both files parse as valid OTLP/JSON; a unit test asserts every
  attribute name in `requirements.md` appears at least once in
  `devloop-trace.json`; the poisoned fixture is referenced by name in T7.

- [ ] 4. Generalize the exporter list in
  `platform-gitops/bootstrap/templates/observability/otel-collector.yaml`
  (depends on 1). Add the `{{- range .Values.otelCollector.backends }}` blocks
  to both `exporters:` and `service.pipelines.traces.exporters` exactly as in
  `design.md`, keeping the existing `{{- if .Values.otelCollector.backendEndpoint }}`
  path intact. Add `backends: []` under `otelCollector` in
  `platform-gitops/bootstrap/values.yaml` with a comment pointing at this
  proposal. Update `docs/runbooks/otel-collector.md`'s "Swapping the backend"
  section to document both keys and state that both render if both are set.
  DoD: `helm template` of `platform-gitops/bootstrap` with `backends: []`
  produces a ConfigMap byte-identical to `main`; with two entries it produces
  two `otlp/<name>` exporters each with its own `sending_queue`; T1 and T2
  pass; `validate-manifests.yml` is green.

- [ ] 5. Add the emitter workflow (depends on 3, 4). Add
  `platform-gitops/argo-workflows/cluster-templates/wft-otel-trace-fixture.yaml`
  as a `ClusterWorkflowTemplate` named `otel-trace-fixture` with parameters
  `ratePerSecond`, `durationMinutes`, `executionCount` and `fixture`, POSTing
  the chosen fixture to
  `http://otel-collector.monitoring.svc.cluster.local:4318/v1/traces` with
  fresh trace/span ids per execution. Follow the conventions of the existing
  templates in that directory (`ttlStrategy`, `serviceAccountName:
  argo-workflow-sa`, `workflows.argoproj.io/description` annotation).
  DoD: a run against the live collector increments
  `otelcol_receiver_accepted_spans` by the expected count in Grafana, and the
  enriched, redacted spans are visible in the collector's `debug` output via
  Loki. No NetworkPolicy change was required (`argo-workflows` is already an
  allowed source namespace in
  `infra-components/observability/otel-collector/networkpolicy.yaml`).

- [ ] 6. Create the evaluation sandbox (depends on 2). Add a `Namespace`
  manifest `observability-eval` with annotations
  `mctl.ai/purpose: "issue-903-spike"` and `mctl.ai/teardown-after: "<date>"`,
  plus a `default-deny` posture consistent with how
  `platform-gitops/helm-charts/tenant/templates/networkpolicy.yaml` layers
  its policies. Whitelist each surviving candidate's chart repo in the
  relevant `AppProject` under
  `platform-gitops/bootstrap/templates/projects/`, and add any new resource
  kinds to its `clusterResourceWhitelist`/`namespaceResourceWhitelist`.
  DoD: namespace exists with both annotations; every surviving candidate's
  chart repoURL appears in an `AppProject.spec.sourceRepos`; a deliberate
  sync of one candidate does not fail with a project-permission error.

- [ ] 7. Deploy each surviving candidate (depends on 6). One
  `Application` per candidate at
  `platform-gitops/bootstrap/templates/observability/eval/<candidate>.yaml`,
  multi-source in the established style
  (pinned upstream chart + `path:
  platform-gitops/infra-components/observability/eval/<candidate>`),
  destination `observability-eval`, single replica, smallest viable storage,
  `syncPolicy.automated` with `prune: true` and **`selfHeal` omitted**.
  Companion manifests: a NetworkPolicy whose `podSelector` matches that
  candidate's pods only, a `VMServiceScrape` if it exposes `/metrics` (with
  the chart's own ServiceMonitor/PodMonitor preset disabled — vmagent runs
  `selectAllByDefault: true`, incident #1159), and an `ExternalSecret` for any
  credential. Any object storage goes to Cloudflare R2, following
  `infra-components/observability/secrets/loki-minio-externalsecret.yaml`.
  DoD: every candidate Application is Healthy/Synced; `kubectl -n
  observability-eval get networkpolicy -o yaml` shows no `podSelector: {}`;
  `git grep` over the PR finds no literal matching `ghp_`, `sk-`, `hvs\.` or a
  JWT prefix.

- [ ] 8. Turn on the fan-out (depends on 4, 7). Set `otelCollector.backends`
  in `platform-gitops/bootstrap/values.yaml` to one entry per deployed
  candidate, each with `queueSize` below the 5000 default so N queues do not
  multiply the collector's memory headroom past its 512Mi limit. Merge, let
  ArgoCD sync (`selfHeal: true` on `otel-collector`), then run task 5's
  workflow at the declared rate for the declared window.
  DoD: `otelcol_exporter_sent_spans` is non-zero for every `otlp/<name>`
  exporter; the same `mctl.execution_id` from the fixture is findable in every
  candidate's UI; `OtelCollectorRefusedSpans` has not fired.

- [ ] 9. Measure, do not guess (depends on 8). Over a fixed, declared soak
  window at a fixed, declared span rate, record per candidate from the
  existing VictoriaMetrics series: peak and steady `container_memory_working_set_bytes`,
  CPU, and persistent-storage growth per million spans. Record in the ADR
  alongside the collector's own `otelcol_exporter_queue_size` per exporter.
  DoD: every operations-dimension cell in the matrix cites a PromQL result
  measured on `mctl-preprod`, and no cell cites vendor documentation for
  footprint.

- [ ] 10. Score the matrix (depends on 2, 9, and tests T3-T8). Fill every cell
  0-5 with a one-line evidence citation. Compute weighted totals with the
  weights frozen in task 1. Apply the decision rule from `design.md` and emit
  exactly one of the issue's seven verdicts.
  DoD: matrix complete, totals arithmetic checked, verdict stated in one
  sentence, and each of the ten acceptance-criteria checkboxes in issue #903
  mapped to the task or test that satisfied it.

- [ ] 11. Finalize the ADR and the runbook (depends on 10). Promote
  `docs/adr/0001-agent-execution-trace-backend.md` from draft to accepted:
  context, scored matrix, decision, rejected options with reasons,
  consequences including the exit procedure and the explicit statement that
  the selected backend is not the FinOps source of truth
  (`mctlhq/.github#48`). Record the fixture-fidelity caveat from
  `requirements.md`. Update
  `docs/runbooks/otel-collector.md` "Accepted residuals" — the line "No trace
  backend selected" is now false.
  DoD: ADR merged; runbook no longer claims no backend is selected; if the
  verdict selects a backend, `otelCollector.backends` names it and a Grafana
  datasource ConfigMap (`grafana_datasource: "1"`, modelled on
  `bootstrap/templates/observability/loki-datasource.yaml`) is committed for
  it.

- [ ] 12. Tear down (depends on 11). Delete every non-selected
  `bootstrap/templates/observability/eval/*.yaml` and the corresponding
  `infra-components/observability/eval/*` directories; remove the
  `observability-eval` Namespace manifest and confirm its PVCs are gone;
  remove the now-unused `AppProject.sourceRepos` entries; leave
  `otelCollector.backends` naming only the winner, or `[]` if the verdict is
  mctl-native only. If a backend was selected, promote it out of `eval/` into
  a normal `bootstrap/templates/observability/<backend>.yaml` with
  `selfHeal: true` restored, add alert rules in
  `infra-components/observability/vm-rules/` with a unit test in
  `vm-rules/tests/` (precedent: `otel-collector-alerts.yaml` +
  `tests/otel-collector-alerts_test.yaml`), and open follow-up issues for
  sampling and for Grafana trace-to-logs correlation.
  DoD: `kubectl get ns observability-eval` returns NotFound; `kubectl get pvc
  -A` shows no orphaned candidate volumes; cluster resource usage is back to
  its pre-spike baseline plus at most the selected backend.

## Tests

- [ ] T1. `tests/test_otel_collector_backends_render.py` — render
  `platform-gitops/bootstrap` with `otelCollector.backends: []` and assert the
  collector ConfigMap is byte-identical to the render from `main`; then render
  with two entries and assert exactly two `otlp/<name>` exporter keys exist,
  both listed in `service.pipelines.traces.exporters`, each with its own
  `sending_queue` and `retry_on_failure`, and `debug` still present. Wire into
  `.github/workflows/validate-manifests.yml` next to the existing
  `tests/test_base_service_otel_env.py` and
  `tests/test_otel_collector_alert_windows.py` invocations.

- [ ] T2. Legacy-key regression — in the same test file, assert that a
  non-empty `otelCollector.backendEndpoint` still renders `otlp/backend`
  unchanged, and that setting both it and `backends` renders both, so
  `docs/runbooks/otel-collector.md`'s documented procedure stays true.

- [ ] T3. Fixture schema test — assert every correlation attribute named in
  `requirements.md` appears at least once in
  `tests/fixtures/devloop-trace.json`, that the span tree has a single root
  per execution with no orphaned parent ids, and that at least one execution
  terminates in an error span.

- [ ] T4. Trace reconstruction, per candidate — open the fixture's
  `mctl.execution_id` in each candidate and confirm the full parent/child
  tree renders with the Temporal, Argo, model, MCP/tool, GitHub, artifact and
  outcome spans all present and correctly nested. Record a screenshot path as
  the matrix cell citation.

- [ ] T5. Search and correlation, per candidate — query by
  `mctl.repository`, by `mctl.github.issue`, by `mctl.github.pr`, by
  `mctl.agent.role` and by `mctl.outcome`; record which of the five are
  first-class searchable, which need a full-text hack, and which are
  impossible.

- [ ] T6. Token, tool, error and cost visibility, per candidate — confirm
  whether `gen_ai.usage.input_tokens` / `output_tokens` /
  `cache_read_input_tokens` / `reasoning_tokens` and `mctl.cost.usd` are
  aggregatable per execution and groupable by `gen_ai.request.model` /
  `gen_ai.system` / `mcp.tool.name`, and whether errors are navigable from the
  root span without a manual query.

- [ ] T7. Privacy proof, per candidate — emit
  `tests/fixtures/devloop-trace-redaction.json` and assert that
  `gen_ai.prompt.0.content`, `mcp.tool.arguments`,
  `http.request.header.authorization` and the `ghp_`-shaped value in
  `mctl.artifact.note` are all unretrievable from the candidate's UI, its
  query API and its raw export. Any retrievable one is a spike-blocking
  finding against the collector, not against the candidate.

- [ ] T8. Producer-isolation proof — with the fan-out live, scale one
  candidate to zero (possible because task 7 omits `selfHeal`), keep the
  fixture emitting, and assert: the emitter workflow still succeeds,
  `otelcol_receiver_refused_spans` stays flat, every other exporter's
  `otelcol_exporter_sent_spans` keeps climbing, `debug` output continues in
  Loki, and `OtelCollectorExportFailures` / `OtelCollectorQueueNearFull` fire
  for the downed exporter only. Scale it back and confirm recovery.

- [ ] T9. FinOps independence — reconstruct total token usage and estimated
  cost for one fixture execution using only VictoriaMetrics and the collector,
  with every candidate scaled to zero. Passing means no candidate is the only
  home for cost data.

- [ ] T10. Export and exit — for the candidate the verdict selects, export a
  trace and confirm it round-trips in an OTLP-compatible form, and confirm a
  documented backup/restore path. Then set `otelCollector.backends: []`,
  re-render, and assert via T1 that the pipeline returns to `exporters:
  [debug]` with no producer-side change.

## Rollback

Four levels, cheapest first. Levels 1 and 2 are the operationally relevant
ones; 3 and 4 exist because the spike deploys new stateful workloads.

1. **Stop the fan-out.** Set `otelCollector.backends: []` (and
   `backendEndpoint: ""`) in `platform-gitops/bootstrap/values.yaml`, merge,
   let ArgoCD sync. The traces pipeline drops back to `exporters: [debug]` —
   the exact state `main` is in today. No producer restart, no image rebuild,
   nothing in `mctl-agent` or `mctl-agents` changes, because producers only
   ever address `otel-collector.monitoring.svc.cluster.local`. This is the
   same one-key rollback `docs/runbooks/otel-collector.md` already documents,
   and T1 is the test that guarantees the empty case renders identically.

2. **Take a single candidate out of the comparison.** Remove its entry from
   `otelCollector.backends` and delete its
   `bootstrap/templates/observability/eval/<candidate>.yaml`. ArgoCD
   (`prune: true`) removes its workloads. Every other candidate and the
   collector are unaffected, because each exporter has its own queue. If the
   candidate is merely misbehaving rather than rejected, `kubectl scale
   --replicas=0` is faster and will not be reverted, since task 7 deliberately
   omits `selfHeal`.

3. **Remove the sandbox entirely.** Delete the `observability-eval`
   Namespace manifest and all `infra-components/observability/eval/`
   directories, then verify no PVCs survive (`kubectl get pvc -n
   observability-eval` must return nothing, and the namespace itself must
   reach NotFound rather than sticking in Terminating on a finalizer). Remove
   the `AppProject.sourceRepos` entries added in task 6. This is task 12 run
   early.

4. **Revert the template change.** `git revert` the task-4 commit to restore
   the scalar-only `backendEndpoint` in
   `bootstrap/templates/observability/otel-collector.yaml`, plus the task-5
   `wft-otel-trace-fixture.yaml` and the task-3 fixtures. Safe at any point
   because nothing depends on `backends` once level 1 has run. Note that
   `otel-collector` has `selfHeal: true`, so the revert takes effect on the
   next ArgoCD sync without manual intervention — and conversely, a manual
   `kubectl edit` of the collector ConfigMap will be reverted by ArgoCD and is
   not a valid rollback path.

Non-rollback: `docs/adr/0001-agent-execution-trace-backend.md` is not reverted
if the spike is abandoned. It is amended with a "superseded / abandoned"
status and the reason, so the next attempt starts from what was learned rather
than from zero.
