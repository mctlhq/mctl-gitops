# Close the #617 correlation contract: durable edge evidence, tool-call spans, worked example

## Context

Issue #617 asks for two things in order: measure what actually reaches the
`tg.mctl.ai` ingress (Slice 1), then build the MCP correlation contract on the
measured result (Slice 2). The clone shows Slice 1 has been performed and
Slice 2 Branch A has largely been implemented: `internal/edgectx/edgectx.go`
records the 2026-09-12 measurement in its package doc, `internal/mcp/server.go`
captures the arriving facts in `httpContext` via
`mcpserver.WithHTTPContextFunc`, `internal/db/store.go` (`LogToolCall`,
`AuditEntry`, `ListAuditFor`) persists and returns `edge_request_id`,
`edge_route`, `mcp_method`, `mcp_name` and `protocol_version`,
`internal/db/audit_chain.go` folds them into the tamper-evident hash under a
dedicated marker byte, and `internal/db/db.go` adds the columns additively with
a partial index.

Three acceptance items of #617 are still open, and they are the ones that make
the result usable by somebody who was not in the room. First, the Slice 1
evidence lives only as prose inside a Go package comment: there is no dated,
in-repo header table for both routes with a per-candidate verdict, and no
repeatable way to re-run the measurement when the Portal changes. Second,
Branch A requires the identifier to be exposed "as OTel span attributes on the
tool call"; `internal/mcp/tools.go` mirrors the facts to `slog` and states
plainly that no tracer is wired (OpenTelemetry is an indirect dependency in
`go.mod`), so the trace leg of the target chain does not exist. Third, the
worked example — one `tg_list_dialogs` call shown as Portal evidence, audit
entry and trace span joined on a single identifier — has never been produced,
which is the actual deliverable the enterprise roadmap `mctlhq/.github#35`
is waiting on. This proposal closes exactly those three gaps and changes no
existing field, column or response shape.

## User stories

- AS a platform operator I WANT a dated, in-repo record of which headers arrive
  at `tg.mctl.ai/mcp` on the Portal route and on the direct route SO THAT the
  correlation contract can be re-checked after a Portal change instead of being
  trusted from memory.
- AS a platform operator I WANT to re-run that header measurement on demand
  without reading message content or credentials SO THAT a suspected regression
  is answered by evidence rather than by inference.
- AS an incident responder I WANT an MCP tool call to emit a trace span
  carrying the edge request id, route, MCP method/name and protocol version SO
  THAT I can pivot from a Cloudflare ray to a span and back to the audit row.
- AS an auditor I WANT the audit row to carry the trace id of the call SO THAT
  the join from audit to trace is deterministic instead of a timestamp guess.
- AS a reviewer of `mctlhq/.github#35` I WANT one end-to-end worked example
  (edge evidence, audit entry, span) joined on stated identifiers SO THAT the
  "cross-layer trace/audit correlation example" deliverable is demonstrably
  met.
- AS a security reviewer I WANT the direct-route case documented and countable
  SO THAT a direct-URL bypass of the Portal is recognisable in audit, which is
  the input Phase 4 (`mctl-telegram#616`) needs.

## Acceptance criteria (EARS)

Evidence

- WHEN the repository is read at any later date THE SYSTEM SHALL provide
  `docs/reports/edge-headers-617.md` containing, for both the Portal route and
  the direct route, the complete observed inbound header table with exact
  header names as received, the date of the measurement, and a per-candidate
  verdict of `arrives` / `does not arrive` / `arrives but is not stable across
  calls` for at least `Cf-Ray`, `CF-Connecting-IP`, `Cf-Worker`, `traceparent`,
  `tracestate`, `Mcp-Method`, `Mcp-Name` and `MCP-Protocol-Version`.
- WHILE that document states a verdict THE SYSTEM SHALL scope every claim to
  the measured route and date and SHALL NOT extrapolate to Cloudflare Gateway
  logs, other zones or other upstreams.
- WHERE a candidate was not measured THE SYSTEM SHALL record it as
  `not measured` with the reason, rather than omitting it.
- IF a header value is a credential-bearing header (`Authorization`, `Cookie`,
  `Proxy-Authorization`) THEN THE SYSTEM SHALL record only its name and
  presence, never any part of its value.

Repeatable capture

- WHEN the operator sets the header-survey environment flag and a request
  reaches the MCP path THE SYSTEM SHALL emit one structured log record listing
  the inbound header names and, for each, a non-reversible value shape (byte
  length, character class, and a truncated digest that is stable for a repeated
  identical value), and SHALL NOT emit raw values.
- WHILE the header-survey flag is unset THE SYSTEM SHALL emit nothing
  additional and SHALL behave byte-for-byte as it does today.
- WHEN the survey is enabled THE SYSTEM SHALL rate-limit its records so a
  sustained request rate cannot flood the log pipeline.

Tracing

- WHEN tracing is configured (OTLP endpoint set) and an MCP request arrives THE
  SYSTEM SHALL start one server span for that request.
- WHEN an inbound `traceparent` is present and well-formed THE SYSTEM SHALL
  continue that trace rather than starting a new one.
- WHEN an MCP tool call is audited THE SYSTEM SHALL set on the current span the
  attributes `mctl.edge.request_id`, `mctl.edge.route`, `mcp.method`,
  `mcp.name`, `mcp.protocol_version`, `mctl.tool.name`, `mctl.tool.status` and
  `mctl.user.id`, each sourced from `edgectx.From(ctx)` with no second capture.
- WHILE any span is emitted THE SYSTEM SHALL NOT place message bodies, peer
  handles, phone numbers, session strings or raw tool arguments on it.
- IF no OTLP endpoint is configured THEN THE SYSTEM SHALL use a no-op tracer,
  write no `trace_id` to audit, and keep startup, latency and memory behaviour
  unchanged.

Audit join key

- WHEN a tool call is audited and a valid, sampled span context exists THE
  SYSTEM SHALL store its trace id in a new nullable `trace_id` column on
  `audit_logs` and return it as an additive `trace_id` field from
  `get_my_audit_log`, `get_user_audit_log` and `GET /api/account/audit`.
- WHILE a row carries no trace id THE SYSTEM SHALL leave the column NULL and
  omit the JSON field, exactly as the five existing correlation fields behave.
- WHEN the audit hash chain is recomputed over rows written before this change
  THE SYSTEM SHALL produce byte-identical hashes, so `VerifyAuditChain` still
  reports `ok` for every existing chain.
- IF a row carries a trace id THEN THE SYSTEM SHALL fold it into the entry hash
  under its own marker block, so it is tamper-evident like every other audit
  field.

Worked example and bypass

- WHEN the worked example is produced THE SYSTEM SHALL publish
  `docs/reports/correlation-example-617.md` showing one read-only tool call by
  a single user through `mcp.mctl.ai` as (1) Portal/Access evidence,
  (2) the `mctl-telegram` audit entry, (3) the trace span, with the join keys
  named explicitly and no message content in any of the three.
- WHILE the example is presented THE SYSTEM SHALL state which join is
  deterministic and which is corroborating, including that `Cf-Ray` arrives on
  both routes and that one Portal tool call is more than one upstream request.
- WHEN a call arrives without the Portal marker THE SYSTEM SHALL record
  `edge_route = "direct"` and THE SYSTEM SHALL expose a low-cardinality
  Prometheus counter of tool calls by route so direct-URL use is observable for
  `mctl-telegram#616`.
- WHILE any of these fields exist THE SYSTEM SHALL NOT use them as an
  authorization input; they remain headers as received.

## Out of scope

- Re-opening the Branch A / Branch B decision. Branch A was chosen on the
  2026-09-12 measurement and is already implemented; this proposal does not
  introduce an `mctl_request_id` fallback.
- Changing, renaming or removing any existing audit field, column, JSON key or
  tool response shape.
- Capturing correlation on non-MCP audit rows: the OAuth `connect:*` events
  (`internal/oauth/`) and `internal/agentapi` write through handlers that never
  pass `internal/mcp.httpContext`, and their NULL correlation columns remain a
  documented true statement rather than a gap to close here.
- Cloudflare Gateway, Gateway log correlation, and the hardening follow-up
  `mctlhq/mctl-gitops#1193`. The Portal path alone must correlate.
- Deploying or operating an OTLP collector; this proposal makes the exporter
  configurable and off by default.
- Retiring the legacy MCP protocol path or any other part of
  `mctl-telegram#568`; `protocol_version` is already the shared column and stays
  shared.
- Any logging of message bodies, phone numbers, @handles or session strings.

## Open questions

- Does the Portal forward `traceparent`/`tracestate`? The existing
  `internal/edgectx` doc comment does not record a verdict for them. Proceeding
  on the assumption that it may not: the design continues an inbound trace when
  one is present and starts a fresh one otherwise, so both outcomes are
  correct, and task 1 records the actual verdict in the evidence document.
- Whether Cloudflare strips a client-supplied `Cf-Worker` on the direct route
  was explicitly not measured (stated in `internal/edgectx/edgectx.go`).
  Proceeding by keeping `edge_route` strictly as evidence, never as an
  authorization input, and by adding this to the evidence document as an
  open `not measured` row with a re-measurement step.
- Trace sampling ratio in production is undecided. Proceeding with a
  configurable ratio defaulting to 1.0 when tracing is enabled, because MCP
  tool-call volume is low and a sampled-out call would otherwise store a trace
  id pointing at a trace no backend holds.
- No OTLP collector endpoint is referenced anywhere in the clone
  (`deploy/` has alerts, grafana and ingress only). Proceeding with tracing
  disabled by default so the change is inert until an endpoint exists.
- The tracer bootstrap may already be owned elsewhere (a roadmap child for
  platform-wide OpenTelemetry). If so, tasks 4-6 below collapse to the
  attribute-setting shim plus the `trace_id` column, and `internal/tracing`
  is dropped in favour of the platform package. Proceeding with the
  self-contained, default-off package because nothing in the clone references
  such a package or endpoint; the attribute names above are chosen to match the
  mapping already circulated so the shim is portable either way.
- Any new field on `db.AuditEntry` must keep the reflected output schema open
  to additive fields: `internal/mcp/output_schema.go` strips
  `additionalProperties: false` precisely because the Cloudflare portal's
  frozen catalogue rejected the five correlation fields once (#631/#637).
  Proceeding by adding `trace_id` through the same path and relying on
  `TestOutputSchemasStayOpenToAdditiveFields` to prove it.
- The issue asks for the example to be "posted here and linked from
  `mctlhq/.github#35`". Posting and linking are actions outside the repository;
  the proposal produces the committed artifact the comment quotes, and lists
  the posting step as a task with no code dependency.
