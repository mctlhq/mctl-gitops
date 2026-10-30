# Spike + pilot: stable OTTL for per-tenant filtering, redaction and telemetry cost control in the otel-collector

## Context

Issue #2211 (scout-generated) asks whether stable OTTL (OpenTelemetry
Transformation Language, declared v1/stable per
https://opentelemetry.io/blog/2026/ottl-v1/) can be used in the platform's
OpenTelemetry Collector to filter, redact and cut telemetry cost in the
multi-tenant observability pipeline. The requested outcome is an "OTTL
pipeline pilot".

The platform already runs a gateway-mode collector
(`platform-gitops/bootstrap/templates/observability/otel-collector.yaml`,
contrib image pinned to `0.160.0`) for **traces only**. Its pipeline uses one
OTTL-based processor (`filter/health`, written in the older context-less
style) and stamps every span with the tenant identity `mctl.team` /
`mctl.component` through `k8sattributes`. Logs go promtail -> Loki and metrics
go vmagent -> VMSingle; neither passes through the collector, so OTTL cannot
touch them today. This proposal answers the spike question with a written
assessment, and pilots OTTL on the traces pipeline in three ways:
(a) value-level redaction and attribute-size caps that the `redaction`
processor cannot express, (b) per-tenant drop/keep rules keyed on
`mctl.team`, both driven from values and empty by default, and (c) removing
the largest avoidable cost already visible in the config: the `debug` exporter
that copies every span into Loki at `verbosity: normal`, even though Tempo is
the permanent backend.

## User stories

- AS a platform operator I WANT a written verdict on whether stable OTTL
  covers our filtering, redaction and cost needs, per signal (traces, logs,
  metrics) SO THAT later observability work starts from evidence, not from
  a blog post.
- AS a platform operator I WANT per-tenant OTTL rules (drop spans, truncate
  attributes, scrub values) declared in `platform-gitops/bootstrap/values.yaml`
  SO THAT I can control one tenant's trace volume and sensitive data without
  touching other tenants or editing the collector template.
- AS a security reviewer I WANT OTTL value scrubbing (for example email
  addresses and credentials embedded inside URLs and messages) applied after
  the existing `redaction` processor SO THAT a secret embedded inside a longer
  string is caught, not only a whole value that matches a pattern.
- AS the cost owner I WANT the collector to stop mirroring every span into
  Loki through the `debug` exporter SO THAT Loki ingestion and R2 storage stop
  paying twice for traces that Tempo already stores.

## Acceptance criteria (EARS)

- WHEN the spike is complete THE SYSTEM SHALL contain
  `docs/spikes/ottl-telemetry-pipeline.md` that answers the issue question
  separately for traces, logs and metrics, states which OTTL syntax (context
  inference and path prefixes) the pinned collector `0.160.0` accepts, and
  gives a go/no-go verdict for each signal.
- WHILE `otelCollector.ottl` is absent or every list under it is empty THE
  SYSTEM SHALL render a collector ConfigMap with no `transform/*` or
  `filter/tenant-*` processors. The only render diff from today is the
  `debug` exporter change below.
- WHEN `otelCollector.ottl.scrub.enabled` is true THE SYSTEM SHALL render one
  `transform/scrub` processor, placed after `redaction` and before
  `filter/health`. It SHALL use `replace_all_patterns` to mask email
  addresses and credential shapes embedded inside longer attribute values,
  and SHALL cap span attribute values at `otelCollector.ottl.scrub.maxValueLength`
  characters with `truncate_all`.
- WHEN an entry `{team, dropSpans: [{attribute, operator, value}]}` is listed
  under `otelCollector.ottl.tenants` THE SYSTEM SHALL render a
  `filter/tenant-<team>` processor. Tenant values SHALL NOT contain free-form
  OTTL: `attribute` and `operator` come from closed allowlists, and the
  template compiles each rule into OTTL itself, ANDed with
  `resource.attributes["mctl.team"] == "<team>"`, so a rule for one tenant
  can never drop another tenant's spans.
- IF a tenant rule has an unknown key, an `attribute` or `operator` outside
  the allowlist, or a `value` outside `^[A-Za-z0-9._/:-]{1,128}$` (which
  excludes quotes, parentheses, whitespace, newlines and template
  delimiters), THEN THE SYSTEM SHALL fail CI before merge.
- IF a tenant rule names a team that has no directory under
  `platform-gitops/tenants/`, or its name is not DNS-safe, THEN THE SYSTEM
  SHALL fail CI (`validate-manifests.yml`) before merge.
- IF an OTTL statement fails to evaluate at runtime THEN THE SYSTEM SHALL
  keep the span and continue (`error_mode: ignore`), and the failure SHALL
  be countable through the collector's own metrics, so a bad rule never
  drops a whole batch or crashes the pod.
- WHILE `otelCollector.backendEndpoint` is set THE SYSTEM SHALL configure the
  `debug` exporter with `verbosity: basic` (one summary line per batch, no
  span bodies). That `basic` prints no span attributes or body at `0.160.0`
  SHALL be proven by running the real binary, not inferred from the name. It SHALL return to `normal` only when the backend is unset,
  which is the documented rollback state.
- WHEN the pilot is merged THE SYSTEM SHALL keep every existing guarantee:
  `memory_limiter` first, `k8sattributes` before any tenant-keyed rule,
  `redaction` before `transform/scrub`, `batch` last.
  `tests/test_otel_collector_redaction.py` and
  `tests/test_otel_collector_redaction_e2e.py` SHALL keep passing unchanged.
- THE SYSTEM SHALL deliver the work in three steps: PR A (mechanism, scrub
  off, no tenant rules, debug cost cut), PR B (owner-approved
  `scrub.enabled: true`), and after 7 days PR C (report with numbers and a
  GO/NO-GO verdict). PR A and PR B SHALL reference the issue without a
  closing keyword; only PR C may close it.
- WHEN the pilot has run for 7 days THE SYSTEM SHALL have a recorded
  before/after comparison in the spike document: collector accepted vs.
  exported spans, Loki ingestion bytes for `{namespace="monitoring",
  container=~".*otel.*"}`, and Tempo ingested bytes.

## Out of scope

- Moving logs from promtail to a collector-based log pipeline (filelog
  receiver). The spike document assesses this; doing it is a separate
  proposal.
- Moving metrics from vmagent to the collector.
- Tail sampling (the `tail_sampling` processor) and probabilistic sampling.
  The spike may recommend them, but this pilot changes nothing about
  sampling.
- Changing the existing `redaction` processor's key and value lists, or
  replacing it with OTTL.
- Bumping the collector image or chart. If the spike finds the pinned
  `0.160.0` lacks a needed OTTL feature, that becomes a follow-up issue.
- Per-tenant billing or chargeback of telemetry volume.

## Open questions

- Which collector release is the first to ship OTTL v1 as described in the
  blog post, and does `0.160.0` accept the context-inferred `statements:`
  form with `span.` / `resource.` path prefixes? This proposal assumes yes,
  since that form predates the pin, and the first task verifies it against
  the binary. If not, the pilot falls back to the explicit
  `trace_statements: [{context: span, statements: [...]}]` form, which
  `0.160.0` certainly accepts.
- Which tenants should get pilot rules? The deployed producers are all in
  `admins` (`mctl-agents-worker*`, `mctl-support`, plus `mctl-agent` in
  `bootstrap/templates/mctl-platform/mctl-agent.yaml`). The pilot therefore
  ships the mechanism with an empty tenant list and one documented example.
  No live tenant rule is enabled without an owner deciding which spans are
  waste.
- Is the `debug` exporter at `verbosity: normal` still relied on for
  anything? The runbook calls it "phase 1" verification, and Tempo has since
  replaced it. This proposal assumes it is now waste while a backend is set.
- I could not read current span volume or the collector's Loki volume in
  this run (see design.md). The size of the cost saving is unmeasured until
  task 1 runs.
- `docs/runbooks/otel-collector.md` says `summary` is "deliberately left
  unset" on `redaction`, but the template sets `summary: info`. The runbook
  update in this proposal fixes that drift.
