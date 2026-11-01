# Tasks: issue-2211-spike-can-stable-ottl-in-the-opentelemet

- [ ] 1. Baseline on the current collector `0.160.0`. Record current span
  throughput (`otelcol_receiver_accepted_spans`,
  `otelcol_exporter_sent_spans`), collector stdout/Loki bytes over the previous
  7 days, and Tempo ingested bytes. Run `otelcol-contrib validate` at `0.160.0`
  against the existing pipeline and both relevant OTTL statement forms. — DoD:
  a draft `docs/spikes/ottl-telemetry-pipeline.md` records
  `FUNCTIONAL_FEASIBILITY: GO|NO_GO`; it does not call this stable suitability.

- [ ] 2. Bump the collector image pin from
  `otel/opentelemetry-collector-contrib:0.160.0` to **`0.164.0`**. Update the
  existing real-binary e2e fixtures/tests to use the target binary and run the
  current collector pipeline before adding any enabled OTTL rule. The Helm
  chart stays at `0.173.0`. — DoD: current redaction/render/e2e behaviour is
  green on `0.164.0`; any regression blocks the pilot.

- [ ] 3. Add `otelCollector.ottl` to
  `platform-gitops/bootstrap/values.yaml` with `scrub.enabled: false`,
  `scrub.maxValueLength: 4096`, `tenants: []`. — DoD: no transform or tenant
  filter is enabled by default.

- [ ] 4. In `platform-gitops/bootstrap/templates/observability/otel-collector.yaml`,
  render `transform/scrub` and one `filter/tenant-<team>` per typed tenant rule.
  Tenant rules are `{attribute, operator, value}` only; the template compiles
  them into OTTL behind the structural
  `resource.attributes["mctl.team"] == "<team>"` guard. Unknown attributes or
  operators make Helm rendering fail. Processor order is
  `memory_limiter, k8sattributes, resource, redaction, [transform/scrub],
  filter/health, [filter/tenant-*], batch`. — DoD: an overlay enabling scrub
  and two tenant rules renders valid YAML and `otelcol-contrib validate` passes
  with the real **0.164.0** binary.

- [ ] 5. Render `debug.verbosity: basic` when
  `otelCollector.backendEndpoint` is set, and `normal` otherwise. — DoD:
  default render shows `basic`; backend unset shows `normal`.

- [ ] 6. Add tenant-rule validation. Team must be DNS-safe and exist under
  `platform-gitops/tenants/`; each rule has exactly `attribute`, `operator`,
  `value`; attribute/operator are from closed allowlists; value matches
  `^[A-Za-z0-9._/:-]{1,128}$` with full-string validation. Wire it into
  `validate-manifests.yml`. — DoD: all negative/mutation cases below fail CI.

- [ ] 7. Update `docs/runbooks/otel-collector.md`: document the image pin and
  why `0.164.0` is the stable-OTTL floor for this spike; OTTL scrub and typed
  tenant rules; debug-exporter behaviour; filter counters; rollback; and fix
  the existing `summary: info` documentation drift. — DoD: every documented
  config key exists in the template.

- [ ] 8. In the draft spike report, record a separate
  `STABLE_OTTL_SUITABILITY: GO|NO_GO` from the **0.164.0** compatibility and
  OTTL validation. Also state separately the upstream language-stability and
  transform-processor component-stability levels. — DoD: PR A cannot merge
  with a predeclared `Traces: go`; stable suitability is evidence-based.

- [ ] 9. Delivery is three PRs. **PR A** is tasks 1-8: baseline, collector
  image bump to 0.164.0, inert OTTL mechanism (`scrub=false`, no tenant rules),
  and debug cost cut. **PR B**, only after explicit owner approval and only if
  `STABLE_OTTL_SUITABILITY: GO`, sets `otelCollector.ottl.scrub.enabled: true`.
  PR A and PR B say `Refs mctlhq/mctl-gitops#2211` and never use a closing
  keyword. **PR C**, after 7 days, writes before/after numbers and final
  `TRACES_PILOT: GO|NO_GO` plus logs/metrics recommendations and may close the
  issue.

## Tests

- [ ] T1. Default render after PR A has collector image `0.164.0`, contains no
  `transform/` or `filter/tenant-` keys, and preserves the current traces
  processor list. Existing render/redaction tests pass on the target version.

- [ ] T2. With scrub enabled and two tenants, processor order is
  `memory_limiter, k8sattributes, resource, redaction, transform/scrub,
  filter/health, filter/tenant-a, filter/tenant-b, batch`, and every tenant
  filter starts with the `mctl.team` guard.

- [ ] T3. New OTTL e2e test uses the real **0.164.0** binary and file exporter.
  Send spans and verify: embedded email is scrubbed while surrounding text
  survives; `?token=abc` is masked; a 10k-character attribute is truncated;
  benign attributes are byte-identical; `gen_ai.usage.input_tokens` keeps its
  numeric value. Mutation proof: remove `transform/scrub` and the test fails.

- [ ] T4. Cross-tenant e2e on real **0.164.0**: an `admins` span matching an
  admins drop rule is dropped; an otherwise identical `labs` span is exported.

- [ ] T5. Existing `tests/test_otel_collector_redaction.py`,
  `tests/test_otel_collector_redaction_e2e.py` and
  `tests/test_otel_collector_backends_render.py` still pass after their binary
  pin is moved to `0.164.0` where applicable.

- [ ] T6. Validator and template both reject: `team: "Admins"`, nonexistent
  team, value containing `) or true`, single quote, double quote, embedded or
  trailing newline, template-looking input (`{{ .x }}`), unknown operator,
  unknown attribute, and an extra key. Mutation proof: removing value
  validation must make the cross-tenant test fail or otherwise be caught by
  the negative suite.

- [ ] T7. `debug` exporter sentinel test uses the real **0.164.0** binary:
  `basic` must not print a sentinel span attribute/body; mutation at `normal`
  or `detailed` must print it.

- [ ] T8. Version-gate mutation: changing the target fixture/image back to
  `0.160.0` must fail the stable-suitability/version assertion. This prevents
  a future edit from silently turning a functional-beta test back into the
  evidence for stable OTTL adoption.

## Rollback

- PR B rollback: set `otelCollector.ottl.scrub.enabled: false`; tenant rules
  remain empty unless separately approved.
- PR A rollback: revert the template/values/image-pin change, restoring
  collector `0.160.0` and `debug.verbosity: normal`. Argo CD rolls the two
  collector replicas back.
- If `0.164.0` fails compatibility validation before merge, do not deploy it;
  record `STABLE_OTTL_SUITABILITY: NO_GO` and stop before PR B.
