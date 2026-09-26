# Document mctl-agent OTLP tracing and the new LLM Prometheus counters

## Context
On 2026-09-23, `mctl-agent` shipped `0c9e8f2` ("feat(telemetry): trace
ticket processing over OTLP and count LLM tokens"), part of
`mctlhq/mctl-agent#38`. It adds one root span per ticket
(`mctl_agent.process_ticket`) with child spans for evidence collection,
skill matching, diagnosis and the fix, plus a client span per model call
following `gen_ai.*` conventions; tracing is configured only through the
standard `OTEL_*` environment variables and installs nothing when no OTLP
endpoint is set, so the agent runs unchanged without a collector. It also
adds two Prometheus counters, `mctl_agent_llm_tokens_total` and
`mctl_agent_llm_requests_total`, because the platform Collector currently
masks `gen_ai.usage.*` span attributes via redaction
(`mctlhq/mctl-gitops#1332`), making the counters the only currently-usable
source for token/cost visibility. The commit message explicitly notes
"Attribute names are reserved in mctlhq/mctl-docs#120" — this mctl-docs
repo already has an open issue anticipating this exact doc need, and
`docs/reference/telemetry-attributes.md` (which already exists on
`docs.mctl.ai`, evidently written to close that issue) already reserves
every attribute name this commit emits
(`mctl.ticket.id`, `mctl.ticket.type`, `mctl.ticket.outcome`,
`mctl.skill.name`, `mctl.diagnosis.confidence`, `mctl.diagnosis.fixable`,
and the `gen_ai.*` model-call attributes) — but still marks them
**`reserved`**, and its opening paragraph still states "no MCTL service has
a tracer, exporter or propagator installed yet." Both are now stale for
`mctl-agent` specifically: `internal/telemetry/telemetry.go` is the
producer this commit ships. Separately, neither `docs/platform/components.md`
(the mctl-agent block) nor `docs/reference/troubleshooting.md` mentions
tracing, the `OTEL_*` variables, or either Prometheus counter at all.

## User stories
- AS a platform operator running mctl-agent, I WANT to know which `OTEL_*`
  environment variables to set to get traces flowing to a collector SO THAT
  I can turn on tracing without reading Go source.
- AS a platform operator investigating LLM cost or latency, I WANT to know
  the two Prometheus counters exist, their exact names and labels, and why
  they exist alongside (not instead of) trace attributes SO THAT I query
  the right metric instead of assuming trace-based cost attribution works
  today.
- AS a maintainer of `docs/reference/telemetry-attributes.md`, I WANT the
  page's `reserved`/`shipped` status for the specific attributes this
  commit emits corrected, naming the producer, SO THAT the catalog's own
  stated promotion rule ("naming the producer and the file that emits it,
  in the same change that ships it") is actually followed.
- AS a reader of the Components page, I WANT the mctl-agent block to
  mention observability as a capability, consistent with how it already
  lists its other capabilities (skills, dispatch, Telegram notifications).

## Acceptance criteria (EARS)
- WHEN a reader opens the mctl-agent block of `docs/platform/components.md`
  THE SYSTEM SHALL state that mctl-agent can emit OpenTelemetry traces over
  OTLP when the standard `OTEL_*` variables are configured, and that no
  collector means no behavior change.
- WHEN a reader opens the observability subsection of
  `docs/reference/troubleshooting.md` THE SYSTEM SHALL document
  `mctl_agent_llm_tokens_total` (labels: `model`, `skill`, `ticket_type`,
  `direction`) and `mctl_agent_llm_requests_total` (labels: `model`,
  `skill`, `outcome`), and SHALL state they exist because the platform
  Collector currently masks `gen_ai.usage.*` span attributes.
- IF a reader wants to enable tracing THEN THE SYSTEM SHALL name the
  specific `OTEL_*` variables that gate it
  (`OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`,
  and the opt-out `OTEL_SDK_DISABLED=true` / `OTEL_TRACES_EXPORTER=none`).
- WHEN a reader opens `docs/reference/telemetry-attributes.md` THE SYSTEM
  SHALL reflect that `mctl.ticket.id`, `mctl.ticket.type`,
  `mctl.ticket.outcome`, `mctl.skill.name`, `mctl.diagnosis.confidence`,
  `mctl.diagnosis.fixable`, `mctl.repository.name`, `mctl.pr.number`
  (incident-agent table) and `gen_ai.operation.name`,
  `gen_ai.provider.name`, `gen_ai.request.model`,
  `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` are `shipped`
  by `mctl-agent`'s `internal/telemetry/telemetry.go`, not `reserved`, and
  SHALL correct the page's blanket "no MCTL service has a tracer... yet"
  statement for this producer.
- WHILE token-count trace attributes are masked by Collector redaction
  today THE SYSTEM SHALL say so explicitly wherever it documents the
  Prometheus counters, so a reader does not attempt cost attribution from
  trace attributes and hit a silent `****`.
- WHILE this is a confirmed-shipped, opt-in feature (not a preview/beta)
  THE SYSTEM SHALL NOT use beta/preview language for it.

## Out of scope
- Deploying or configuring an actual OpenTelemetry Collector — that is
  `mctl-gitops` territory (`platform-gitops/bootstrap/templates/observability/otel-collector.yaml`),
  already referenced from `docs/reference/telemetry-attributes.md`.
- Fixing the Collector's `gen_ai.usage.*` redaction defect
  (`mctlhq/mctl-gitops#1332`) — that is a `mctl-gitops` code change, not a
  docs change; this proposal only documents the current, masked behavior.
- Renaming the two shipped-but-non-conforming `mcp.*` attributes
  (`mctlhq/mctl-telegram#658`) — unrelated producer, already tracked
  elsewhere in the catalog.
- A dedicated `docs/reference/observability.md` page — deferred until a
  second service ships tracing, per the analyst's rationale; this proposal
  uses the existing `docs/reference/troubleshooting.md` instead.
