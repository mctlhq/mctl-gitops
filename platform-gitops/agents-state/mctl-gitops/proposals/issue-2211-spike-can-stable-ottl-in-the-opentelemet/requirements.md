# Spike + pilot: stable OTTL for per-tenant filtering, redaction and telemetry cost control in the otel-collector

## Context

Issue #2211 (scout-generated) asks whether stable OTTL (OpenTelemetry
Transformation Language, declared v1/stable upstream from collector-contrib
0.164.0) can be used in the platform's OpenTelemetry Collector to filter,
redact and cut telemetry cost in the multi-tenant observability pipeline. The
requested outcome is an "OTTL pipeline pilot".

The platform already runs a gateway-mode collector
(`platform-gitops/bootstrap/templates/observability/otel-collector.yaml`,
contrib image pinned to `0.160.0`) for **traces only**. Its pipeline uses one
OTTL-based processor (`filter/health`, written in the older context-less
style) and stamps every span with the tenant identity `mctl.team` /
`mctl.component` through `k8sattributes`. Logs go promtail -> Loki and metrics
go vmagent -> VMSingle; neither passes through the collector, so OTTL cannot
touch them today.

This proposal deliberately separates two questions that the earlier draft
conflated:

1. **Functional feasibility on the current 0.160.0 pin** — do the required
   OTTL functions and processor shapes work at all?
2. **Stable OTTL/v1 suitability** — do they still work after moving the
   collector to the first upstream release carrying the OTTL v1/stability
   guarantee (`0.164.0`), without regressing the existing trace pipeline?

PR A MUST answer both before any OTTL pilot is enabled. Functional success on
`0.160.0` alone is not sufficient for a GO verdict on this spike.

## User stories

- AS a platform operator I WANT separate functional-feasibility and
  stable-suitability verdicts SO THAT a working beta-era configuration is not
  mistaken for a stable OTTL adoption decision.
- AS a platform operator I WANT per-tenant OTTL rules (drop spans, truncate
  attributes, scrub values) declared in `platform-gitops/bootstrap/values.yaml`
  SO THAT I can control one tenant's trace volume and sensitive data without
  touching other tenants or editing the collector template.
- AS a security reviewer I WANT OTTL value scrubbing applied after the
  existing `redaction` processor SO THAT credentials embedded inside longer
  strings are caught, not only whole values.
- AS the cost owner I WANT the collector to stop mirroring every span into
  Loki through the `debug` exporter SO THAT Loki ingestion and R2 storage stop
  paying twice for traces that Tempo already stores.

## Acceptance criteria (EARS)

- WHEN PR A starts THE SYSTEM SHALL record a baseline on the current
  `otel/opentelemetry-collector-contrib:0.160.0`: current span throughput,
  Loki bytes for collector stdout, Tempo ingested bytes, and validation of the
  required OTTL syntax/functions. This baseline answers only
  `FUNCTIONAL_FEASIBILITY`.
- BEFORE any OTTL processor is enabled in production THE SYSTEM SHALL pin the
  collector image to `otel/opentelemetry-collector-contrib:0.164.0` and SHALL
  run the existing collector/redaction/render e2e tests plus the new OTTL and
  debug-exporter tests against that target binary. A failure on `0.164.0`
  blocks the pilot and yields `STABLE_OTTL_SUITABILITY: NO_GO`.
- WHEN the spike report is written THE SYSTEM SHALL contain two explicit
  trace verdicts: `FUNCTIONAL_FEASIBILITY: GO|NO_GO` and
  `STABLE_OTTL_SUITABILITY: GO|NO_GO`. It SHALL NOT predeclare `Traces: go`
  before the `0.164.0` validation succeeds. The report SHALL also note that
  OTTL language stability and component stability of individual processors
  are separate upstream guarantees.
- WHILE `otelCollector.ottl` is absent or every list under it is empty THE
  SYSTEM SHALL render no `transform/*` or `filter/tenant-*` processors. After
  PR A, the intentional default-state changes are the collector image bump
  (`0.160.0 -> 0.164.0`) and `debug.verbosity: normal -> basic` while a Tempo
  backend is configured.
- WHEN `otelCollector.ottl.scrub.enabled` is true THE SYSTEM SHALL render one
  `transform/scrub` processor, placed after `redaction` and before
  `filter/health`. It SHALL use `replace_all_patterns` to mask email addresses
  and credential shapes embedded inside longer attribute values and SHALL cap
  span attribute values at `otelCollector.ottl.scrub.maxValueLength` with
  `truncate_all`.
- WHEN an entry `{team, dropSpans: [{attribute, operator, value}]}` is listed
  under `otelCollector.ottl.tenants` THE SYSTEM SHALL render a
  `filter/tenant-<team>` processor. Tenant values SHALL NOT contain free-form
  OTTL: `attribute` and `operator` come from closed allowlists, and the
  template compiles each rule into OTTL itself, ANDed with
  `resource.attributes["mctl.team"] == "<team>"`, so a rule for one tenant
  cannot drop another tenant's spans.
- IF a tenant rule has an unknown key, an `attribute` or `operator` outside
  the allowlist, or a `value` outside `^[A-Za-z0-9._/:-]{1,128}$`, THEN THE
  SYSTEM SHALL fail CI before merge.
- IF a tenant rule names a team that has no directory under
  `platform-gitops/tenants/`, or its name is not DNS-safe, THEN THE SYSTEM
  SHALL fail CI before merge.
- IF an OTTL statement fails to evaluate at runtime THEN THE SYSTEM SHALL
  keep the span and continue (`error_mode: ignore`), and the failure SHALL be
  countable through collector metrics.
- WHILE `otelCollector.backendEndpoint` is set THE SYSTEM SHALL configure the
  `debug` exporter with `verbosity: basic`. The target `0.164.0` binary SHALL
  prove that `basic` prints no span attributes or body; this SHALL NOT be
  inferred from the verbosity name. It SHALL return to `normal` only when the
  backend is unset.
- WHEN PR A is merged THE SYSTEM SHALL keep every existing guarantee:
  `memory_limiter` first, `k8sattributes` before any tenant-keyed rule,
  `redaction` before `transform/scrub`, `batch` last, and all existing
  collector/redaction/render tests SHALL pass against `0.164.0`.
- THE SYSTEM SHALL deliver the work in three steps: PR A (baseline,
  collector bump to `0.164.0`, mechanism with scrub off/no tenant rules,
  debug cost cut), PR B (owner-approved `scrub.enabled: true`), and after 7
  days PR C (report with numbers and final GO/NO-GO verdicts). PR A and PR B
  SHALL reference the issue without a closing keyword; only PR C may close it.
- WHEN the pilot has run for 7 days THE SYSTEM SHALL record before/after
  collector accepted/exported spans, Loki ingestion bytes for the collector,
  and Tempo ingested bytes.

## Out of scope

- Moving logs from promtail to a collector-based log pipeline.
- Moving metrics from vmagent to the collector.
- Tail sampling and probabilistic sampling.
- Changing the existing `redaction` processor's key/value lists or replacing
  it with OTTL.
- Bumping the Helm chart. The **collector image bump to `0.164.0` is in
  scope and required**; a chart bump is not.
- Per-tenant billing or chargeback of telemetry volume.

## Open questions

- Does the exact existing pipeline remain compatible with collector-contrib
  `0.164.0`, including `redaction`, `filter/health`, exporter settings and the
  chosen OTTL statement form? PR A answers this with the real binary.
- Does the transform processor's own component stability level affect the
  final adoption recommendation even though the OTTL language is v1/stable?
  The report must state the distinction rather than collapsing them.
- Which tenants should get pilot rules? The mechanism ships with an empty
  tenant list; no live tenant rule is enabled without an owner decision.
- Is the `debug` exporter at `verbosity: normal` still relied on for anything?
  The target-binary sentinel test plus the rollback path answer the technical
  part; operational dependence is checked before PR A merge.
- Current span/debug volume is not yet measured; task 1 establishes the
  baseline.
- `docs/runbooks/otel-collector.md` says `summary` is deliberately unset on
  `redaction`, while the template sets `summary: info`; PR A fixes that drift.
