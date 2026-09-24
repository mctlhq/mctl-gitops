# Tasks: issue-1280-spike-observability-run-the-live-tracing

Ordered as six gates. Each gate is at least one commit, and the ordering is
load-bearing: no measurement may precede its declaration, and no score may
precede the instrument that consumes it.

## Gate 0 — preconditions

- [ ] 1. Record the resolved state of each declared precondition
  (`mctlhq/mctl-gitops#1332`, `mctlhq/mctl-agent#38`/PR 137,
  `mctlhq/mctl-agents#195`/PR 466, `mctlhq/mctl-agent#139`) in a new
  "Preconditions" section of `docs/adr/0001-agent-execution-trace-backend.md`.
  — DoD: each of the four is marked resolved-and-verified or unresolved, with
  the date checked; no other ADR section is touched.
- [ ] 2. Verify the `#1332` fix against the rendered collector config, not
  against the issue. — DoD: `helm template` of
  `platform-gitops/bootstrap` shows `blocked_key_patterns` no longer matching
  `gen_ai.usage.input_tokens`, while `github_token` still matches; if `#1332`
  is unfixed, this task records that and Gate 4 marks the token/cost cells
  unmeasured.
- [ ] 3. Add `tests/test_otel_collector_token_redaction.py` (depends on 2) —
  DoD: asserts, against the rendered config from
  `platform-gitops/bootstrap/templates/observability/otel-collector.yaml`, that
  `gen_ai.usage.{input,output,cache_read_input,reasoning}_tokens` survive and
  that `github_token`, `authorization`, `api_key` and `vault.token` are still
  blocked; wired into `.github/workflows/validate-manifests.yml` beside the
  existing `tests/test_otel_collector_*` steps.
- [ ] 4. Determine whether live producer telemetry will exist during the soak
  (depends on 1) — DoD: a recorded yes/no, grounded in whether any
  `platform-gitops/services/*/*/values.yaml` sets `otel.enabled: true` and
  whether `mctl-agent`/`mctl-agents` are emitting; drives the
  `live_producers_expected` field written in task 13.

## Gate 1 — Stage A resolution and candidate axis

- [ ] 5. Resolve every `UNVERIFIED` row in `docs/adr/0001-rubric.yaml`'s
  `stage_a` block (depends on 1) — DoD: traceway, langfuse, phoenix and signoz
  each end as `SURVIVES` with a verified license, chart or image coordinate and
  a pinnable version, or as `SCREENED-OUT` with a reason; no row is deleted;
  `tests/test_adr_rubric_frozen.py` still passes.
- [ ] 6. Apply the Stage A portability gate (depends on 5) — DoD: any candidate
  that cannot ingest plain OTLP without a vendor SDK or vendor-specific
  producer instrumentation is `SCREENED-OUT` with that as the stated reason;
  Phoenix's OpenInference question is answered one way or the other.
- [ ] 7. Add candidate F as two scored shapes (depends on 5) — DoD:
  `agento11y-self-managed` and `agento11y-cloud` appear in `candidates`, in all
  six `dimensions[].candidates` maps, and as two `stage_a` rows; two matching
  entries are appended to `permitted_verdicts`; dimension keys, weights,
  `cell_scale`, `weighted_total_max`, `tie_margin`, `tie_break` and
  `decision_rule` are byte-identical to the merged file; the commit tree still
  contains zero non-null score cells.
- [ ] 8. Record the rubric amendment in the ADR (depends on 7) — DoD: a short
  subsection under "Frozen rubric" states that the candidate axis and
  `permitted_verdicts` were widened for candidate F before any score existed,
  names the commit, and states that the scoring instrument was not changed.
- [ ] 9. State the `agento11y` application-dependency finding (depends on 7) —
  DoD: the ADR says explicitly whether `agento11y` can observe the production
  `claude-agent-sdk` DevLoop execution path without a Grafana-specific
  application dependency, and, if it cannot, records that limitation as the
  reason for the scores it receives; the ADR also restates that
  `mctlhq/mctl-agents#197`/`#198` remains the authoritative policy boundary and
  Grafana guards are not a substitute.

## Gate 2 — sandbox

- [ ] 10. Add `ResourceQuota` and `LimitRange` to
  `platform-gitops/bootstrap/templates/observability/eval-namespace.yaml`
  (depends on 5) — DoD: both inside the existing
  `{{- if .Values.otelCollector.eval.enabled }}` guard, driven by a new
  `otelCollector.eval.quota` / `eval.limits` values block defaulted in
  `platform-gitops/bootstrap/values.yaml`, shaped after
  `helm-charts/tenant/templates/resourcequota.yaml` and `limitrange.yaml`; with
  `eval.enabled: false` the rendered output is unchanged. The quota caps
  `persistentvolumeclaims: 4` and `requests.storage: 40Gi` (design, owner
  constraint 1), and a render test asserts both values.
- [ ] 11. Open the sandbox (depends on 10) — DoD: one commit sets
  `otelCollector.eval.enabled: true` and
  `otelCollector.eval.teardownAfter: "<date>"` together, with the date at most
  14 days after that commit (owner constraint 3); ArgoCD reports the
  `observability-eval` namespace, its four NetworkPolicies, the quota and the
  limit range as Synced/Healthy.
- [ ] 12. Deploy wave 1 candidates (depends on 6, 7, 11) — DoD:
  `otelCollector.eval.candidates` lists only Stage A survivors with verified
  pins; each entry's `values` sets `serviceMonitor.enabled: false` and
  `podMonitor.enabled: false`; each entry uses ephemeral storage where its chart
  allows it, and otherwise PVCs of exactly 10Gi; the wave's PVC count and GiB fit
  the quota and are recorded in its `soak:` entry, and a candidate that does not
  fit is marked unmeasured rather than the quota raised (owner constraint 1);
  each `otel-eval-*` Application is Synced/Healthy;
  `count by (pod) (otelcol_receiver_accepted_spans)` still shows one series per
  collector pod (no `#1159` regression).
- [ ] 12a. Only if the owner has provisioned a Grafana Cloud stack token at
  Vault `secret/platform/observability-eval/grafana-cloud` (never create an
  account or a token yourself), and `agento11y-cloud` is in a wave, add a
  single-destination egress
  NetworkPolicy for exactly that candidate's pods (depends on 12) — DoD: the
  policy names one destination and one port, `allow-cluster-egress` is
  unchanged, and the egress requirement is noted for scoring against
  `data_ownership_portability`; if the carve-out is refused on review, the Cloud
  shape's affected cells are marked unmeasured in task 20.
- [ ] 12b. Tear a wave down before the next one (depends on 12, and on that
  wave's measurements in Gate 4) — DoD: the wave's `otel-eval-*` Applications
  are pruned, and `observability-eval` holds zero PVCs and Hetzner holds zero
  released volumes for that wave before the next wave's `candidates` commit
  (owner constraint 2).

## Gate 3 — declaration and fan-out

- [ ] 13. Declare the soak window (depends on 4, 12) — DoD: a `soak:` block in
  `docs/adr/0001-rubric.yaml` carrying, per wave, `declared_at`,
  `window_start`, `window_end`, `candidates`, `rate_per_second`,
  `duration_minutes`, `execution_count`, `fixtures`, declared total span volume
  and `live_producers_expected`; the commit tree contains zero non-null score
  cells.
- [ ] 14. Turn on the fan-out (depends on 13) — DoD: one
  `otelCollector.backends` entry per live candidate, endpoint
  `<svc>.observability-eval.svc.cluster.local:4317`, `insecure: true` for
  in-cluster candidates; any header is a `${env:...}` expansion backed by a
  Vault ExternalSecret surfaced through `extraEnvFrom`; no literal credential in
  git; `otelcol_exporter_queue_size{exporter="otlp/<name>"}` exists for every
  candidate. The `agento11y-cloud` exporter, if present, sits in a dedicated
  traces pipeline that filters to the fixture emitter's resource attributes, so
  live producer telemetry can never reach it; a render test asserts that filter
  (owner constraint 4).
- [ ] 15. Run the soak (depends on 14) — DoD: `otel-trace-fixture` submitted
  with exactly the declared parameters for both `devloop-trace.json` and
  `devloop-trace-redaction.json`; the workflow reports zero failed executions;
  every candidate's UI shows the fixture executions.
- [ ] 16. If the window must be extended or restarted (depends on 15) — DoD: a
  new commit amends the `soak:` block with the new bounds and the reason; no
  measurement taken outside a declared window is used.

## Gate 4 — measurement

- [ ] 17. Extend the rubric cell schema (depends on 13) — DoD:
  `docs/adr/0001-rubric.yaml` documents `unmeasured_reason` alongside `score`
  and `citation`, and states that exactly one of `score` or `unmeasured_reason`
  is permitted per cell.
- [ ] 18. Measure `trace_reconstruction`, `ai_agent_observability`,
  `data_ownership_portability` and `evals_quality_loop` per candidate (depends
  on 15) — DoD: each cell filled with a score plus a one-line citation naming
  what was observed, or with an `unmeasured_reason`; no cell cites vendor
  documentation.
- [ ] 19. Measure `operations` from VictoriaMetrics (depends on 15) — DoD:
  per-candidate CPU, working-set memory, PVC growth and restart counts over the
  declared window, plus collector-side
  `otelcol_exporter_send_failed_spans{exporter="otlp/<name>"}`,
  `otelcol_exporter_queue_size` and `otelcol_exporter_queue_capacity`; each
  citation names the series and the window.
- [ ] 20. Measure `security_privacy` from the poisoned fixture (depends on 15) —
  DoD: each candidate's own store and UI searched for the fabricated `ghp_*`,
  `sk-*`, `hvs.*` and JWT-shaped values and for `gen_ai.prompt.*`,
  `mcp.tool.arguments` and `http.request.header.authorization`; any retrievable
  hit recorded as a measured failure with the query used.
- [ ] 21. Measure producer isolation (depends on 15) — DoD: one candidate scaled
  to zero replicas inside the declared window; recorded whether
  `otelcol_receiver_refused_spans` rose, whether the other candidates kept
  receiving, and how long the queue took to drain after recovery; the resulting
  `OtelCollectorExportFailures` alert noted as expected, not as an incident.
- [ ] 22. Complete the rubric honestly (depends on 18, 19, 20, 21) — DoD: every
  cell of every candidate has exactly one of `score` or `unmeasured_reason`; for
  any candidate with unmeasured cells, the weighted total is stated as a range
  with the unmeasured dimensions named.

## Gate 5 — decision, promotion, teardown

- [ ] 23. Apply the decision rule (depends on 22) — DoD: the four branches
  evaluated in order, `tie_margin: 25` and the `tie_break` applied where
  relevant, and exactly one `permitted_verdicts` entry selected; if a candidate's
  range straddles the decision, branch 4 is selected with one named blocker.
- [ ] 24. Record the verdict (depends on 23) — DoD: one commit sets `verdict` in
  `docs/adr/0001-rubric.yaml`, replaces the ADR's Decision section with the
  verdict and the evidence that decided it, removes
  `<!-- VERDICT: UNFILLED -->`, and changes Status from `Proposed` to
  `Accepted`.
- [ ] 25. Invert `tests/test_adr_rubric_frozen.py` (depends on 24) — DoD: the
  file is rewritten, not deleted; weight agreement with the Markdown table and
  the Stage A honesty rule are kept verbatim; the freeze assertions become their
  post-decision duals (exactly one of `score`/`unmeasured_reason` per cell,
  non-null `verdict` that is a `permitted_verdicts` member and appears verbatim
  in the ADR, Status `Accepted`, `UNFILLED` marker absent, `soak` block present
  with `declared_at`); dimension keys and weights are hard-coded in the test so
  a weight cannot later be moved to suit a score.
- [ ] 26. Update `docs/runbooks/otel-collector.md` (depends on 24) — DoD:
  "Swapping the backend (one key, no code change)" names the selected backend;
  "The evaluation namespace and the fixture emitter (issue #903 / #1280)" is
  rewritten from pending-spike description into steady-state operating notes or
  a record that no backend was selected; "Accepted residuals" updated.
- [ ] 27. Relocate the winner, if any (depends on 24; a separate pull request that
  is not merged without the owner's explicit approval on it, owner constraint 5;
  tasks 28 and 29 do not wait for it) — DoD: a new Application
  under `platform-gitops/infra-components/observability/<backend>/` outside
  `observability-eval`, with a Grafana trace datasource ConfigMap following the
  `grafana_datasource: "1"` label pattern of
  `bootstrap/templates/observability/loki-datasource.yaml`; the winner is
  Synced/Healthy in its permanent home.
- [ ] 28. Tear down (depends on 26) — DoD: `otelCollector.backends: []`,
  `otelCollector.eval.candidates: []`, `otelCollector.eval.enabled: false`,
  `teardownAfter: ""`; no `otel-eval-*` Application, no `observability-eval`
  namespace, no candidate `hcloud-volumes` PVC and no candidate Vault path
  remain.
- [ ] 29. Confirm the repository returned to its pre-spike render (depends on
  28) — DoD: the rendered collector ConfigMap is byte-identical to
  `tests/fixtures/otel-collector-config-default.yaml`; only the ADR, the rubric,
  the runbook, the quota template and the two test files differ from the
  pre-spike tree.

## Tests

- [ ] T1. `tests/test_otel_collector_token_redaction.py` — `gen_ai.usage.*_tokens`
  survive the rendered `blocked_key_patterns`; `github_token`, `authorization`,
  `api_key` and `vault.token` are still blocked. (task 3)
- [ ] T2. `tests/test_otel_collector_backends_render.py` — unchanged and still
  green after the `ResourceQuota`/`LimitRange` addition, proving the default
  render is byte-identical to the golden fixture with the eval gate off.
  (task 10)
- [ ] T3. `kubeconform` of the eval overlay in
  `.github/workflows/validate-manifests.yml` extended so
  `tests/fixtures/otel-eval-candidates.example-values.yaml` also exercises the
  new `eval.quota` / `eval.limits` keys and renders a schema-valid
  `ResourceQuota` and `LimitRange`. (task 10)
- [ ] T4. Declaration-precedes-measurement check — a test asserting that if any
  cell in `docs/adr/0001-rubric.yaml` is non-null, a `soak` block with a
  `declared_at` exists; runs on every commit from task 13 onward so the
  ordering is enforced by CI rather than by discipline. (task 13)
- [ ] T5. Rewritten `tests/test_adr_rubric_frozen.py` — post-decision
  consistency as specified in task 25, including that no cell has both `score`
  and `unmeasured_reason` and none has neither. (task 25)
- [ ] T6. `scripts/materialize-otel-trace-fixture.py --check` stays green
  throughout; the fixtures are read during the soak, never edited to suit a
  candidate. (tasks 15, 29)
- [ ] T7. Manual, recorded in the ADR: replay `devloop-trace-redaction.json` and
  confirm no fabricated credential-shaped value is retrievable from any
  candidate's store or UI. (task 20)
- [ ] T8. Manual, recorded in the ADR: `helm template` of
  `platform-gitops/bootstrap` at the teardown commit contains no
  `observability-eval` resource and no `otlp/` exporter other than the optional
  `otlp/backend`. (task 28)

## Rollback

Every cluster-affecting step is a values key with an off default, so rollback is
a revert plus an ArgoCD sync at any point.

- **During Gate 2 or 3** (candidates deployed, fan-out on): set
  `otelCollector.backends: []` first — this detaches every candidate from the
  production collector's traces pipeline within one sync and returns it to the
  `debug`-only exporter set. Then set `otelCollector.eval.enabled: false`, which
  prunes every `otel-eval-*` Application (`prune: true` plus the ArgoCD
  resources finalizer are already set) and removes the `observability-eval`
  namespace. Delete any orphaned `hcloud-volumes` PVC by hand, since a pruned
  namespace can leave released volumes behind.
- **If the collector misbehaves rather than a candidate** — reverting the
  `backends` commit restores the byte-identical golden render in
  `tests/fixtures/otel-collector-config-default.yaml`, which is the fastest
  proof that the collector is back to its pre-spike configuration.
- **During Gate 1** (rubric widened, nothing deployed): revert the candidate-F
  commit. Because it changed no dimension key, weight or rule and no score
  existed yet, the revert restores the exact merged frozen rubric and
  `tests/test_adr_rubric_frozen.py` passes unmodified.
- **After Gate 5** (verdict recorded): the ADR is amended, never deleted. If the
  decision is later found unsound, add a superseding ADR and, per the merged
  exit procedure, set this one's status to `Abandoned` with the reason so the
  next attempt starts from this screen rather than from zero. The adopted
  backend is removed by deleting its Application under
  `platform-gitops/infra-components/observability/` and clearing
  `otelCollector.backendEndpoint` — one key, zero producer-code changes, which
  is the portability property the `#902` boundary exists to guarantee.
- **If the spike is abandoned mid-flight**: run Gate 5's teardown tasks (28, 29)
  without tasks 23-27, and set the ADR status to `Abandoned` with the reason.
  The `mctl.ai/teardown-after` annotation is the trigger that makes an abandoned
  sandbox greppable rather than silently permanent.
