# Tasks: issue-2211-spike-can-stable-ottl-in-the-opentelemet

- [ ] 1. Baseline and syntax check. Record the current collector span
  throughput (`otelcol_receiver_accepted_spans`,
  `otelcol_exporter_sent_spans`), the Loki bytes for the collector's stdout
  over 7 days, and Tempo ingested bytes. Run `otelcol-contrib validate` at
  `0.160.0` against both statement forms (explicit `trace_statements`
  contexts, and context-inferred `statements:` with `span.` prefixes). —
  DoD: numbers and the validate result are recorded in a draft of
  `docs/spikes/ottl-telemetry-pipeline.md`.
- [ ] 2. Add `otelCollector.ottl` (`scrub.enabled: false`,
  `scrub.maxValueLength: 4096`, `tenants: []`) to
  `platform-gitops/bootstrap/values.yaml`, with comments. — DoD: the default
  render of `otel-collector.yaml` is unchanged apart from task 4.
- [ ] 3. In `platform-gitops/bootstrap/templates/observability/otel-collector.yaml`,
  render `transform/scrub` (`error_mode: ignore`, `truncate_all` plus the two
  `replace_all_patterns` statements) and one `filter/tenant-<team>` per
  `ottl.tenants[]` entry, with the template-added
  `resource.attributes["mctl.team"] == "<team>"` guard. Insert them into
  `service.pipelines.traces.processors` in the order from design.md
  (depends on 1, 2). — DoD: `helm template` of `platform-gitops/bootstrap`
  with an overlay that enables both renders valid YAML, and
  `otelcol-contrib validate` passes on it.
- [ ] 4. Render `debug.verbosity: basic` when `otelCollector.backendEndpoint`
  is set, and `normal` otherwise. — DoD: the default render shows `basic`,
  and a render with `backendEndpoint: ""` shows `normal`.
- [ ] 5. Add tenant-rule validation: team is DNS-safe, exists under
  `platform-gitops/tenants/`, and has no `"` in conditions. Wire it into
  `.github/workflows/validate-manifests.yml` next to the existing
  otel-collector steps (depends on 2). — DoD: CI fails on a bad team name and
  passes on an empty list.
- [ ] 6. Update `docs/runbooks/otel-collector.md`: add an "OTTL rules"
  section (scrub, tenant filters, a commented `admins` example, how to read
  `otelcol_processor_filter_spans_filtered`), describe the debug verbosity
  behaviour, and fix the `summary: info` drift (depends on 3, 4). — DoD:
  every key the runbook documents exists in the template.
- [ ] 7. Separate follow-up PR: set `otelCollector.ottl.scrub.enabled: true`.
  Leave it 7 days, then write before/after numbers and per-signal verdicts
  (traces go, logs follow-up, metrics no change) into
  `docs/spikes/ottl-telemetry-pipeline.md` (depends on 3-6). — DoD: the
  spike document is merged with measured numbers and filed follow-up issue
  links (logs via collector, tail sampling, and a collector bump if task 1
  found one needed).

## Tests

- [ ] T1. `tests/test_otel_collector_ottl_render.py`: a default-values render
  contains no `transform/` or `filter/tenant-` keys, and its traces processor
  list equals today's list. Run it in `validate-manifests.yml`.
- [ ] T2. Same file: with scrub enabled and two tenants, the processor order
  is `memory_limiter, k8sattributes, resource, redaction, transform/scrub,
  filter/health, filter/tenant-a, filter/tenant-b, batch`, and every
  tenant-filter condition starts with the `mctl.team` guard.
- [ ] T3. `tests/test_otel_collector_ottl_e2e.py`, modelled on
  `tests/test_otel_collector_redaction_e2e.py` (docker, real `0.160.0`, file
  exporter). Send spans and check that:
  - an email inside `url.full` becomes `<email>` while the rest of the URL
    survives;
  - `?token=abc` becomes `token=****`;
  - a 10 000-char attribute is truncated to `maxValueLength`;
  - a benign attribute is byte-identical;
  - `gen_ai.usage.input_tokens` keeps its intValue.
  Include a mutation proof: with the scrub processor removed, the test must
  fail.
- [ ] T4. Same e2e: a span with `mctl.team="admins"` that matches an admins
  drop condition is dropped. An identical span with `mctl.team="labs"` is
  exported.
- [ ] T5. Existing `tests/test_otel_collector_redaction.py`,
  `tests/test_otel_collector_redaction_e2e.py` and
  `tests/test_otel_collector_backends_render.py` still pass unchanged.
- [ ] T6. Validation script (task 5) rejects `team: "Admins"`,
  `team: "nosuchtenant"` and a condition that contains `"`.

## Rollback

- Pilot enablement: set `otelCollector.ottl.scrub.enabled: false` and
  `tenants: []` in `platform-gitops/bootstrap/values.yaml`. Argo CD
  (selfHeal) restores the previous collector config and rolls the 2 replicas.
- Full rollback: revert the template PR. The default render returns to today's
  output, including `debug.verbosity: normal`.
- Emergency, if the collector crashloops on a bad rule: revert the values PR.
  Producers keep retrying OTLP export, so the gap is bounded by their own
  queues. Tempo keeps the data it already has.
