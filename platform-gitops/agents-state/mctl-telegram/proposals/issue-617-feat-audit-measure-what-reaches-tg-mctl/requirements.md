# Correlation-to-OTel adapter for the shipped MCP evidence contract

## Context

mctlhq/mctl-telegram#617 has already completed and shipped its two mctl-owned
correlation slices.

Measured and shipped baseline, which this proposal MUST NOT repeat:

- Slice 1 measured the complete inbound header set on both the Portal and direct
  routes.
- `Cf-Ray` arrives on both routes and is a per-request identifier; it is not a
  route discriminator by itself.
- `Cf-Worker: gateway.agents.cloudflare.com` is the measured Portal-route
  discriminator on the current proxied zone.
- `Mcp-Method`, `Mcp-Name` and `MCP-Protocol-Version` reach the upstream.
- the end-user IP is not propagated through the Portal and is not an actor
  identifier.
- no inbound W3C `traceparent` / `tracestate` was observed on either measured
  route.
- the client-leg Cloudflare ray cannot be deterministically joined to the
  Worker-to-upstream ray on the current Free-zone evidence surface; Cloudflare
  cross-layer correlation is therefore by principal + time, while
  `edge_request_id` joins mctl-owned records.
- the temporary header probe and its runbook were removed after measurement.
- release 0.66.0 already persists and exposes
  `edge_request_id`, `edge_route`, `mcp_method`, `mcp_name` and
  `protocol_version` and mirrors the same values to slog.
- direct-client `Cf-Worker` forgery was measured and stripped by Cloudflare on
  the current zone; this remains evidence, never an authorization primitive.

The issue was deliberately left open only for the OTel half. The issue also
explicitly assigns ownership of tracer/bootstrap/exporter architecture to
mctlhq/.github#55 (vendor-neutral observability). mctl-telegram currently has no
tracer wired; OpenTelemetry API modules are indirect dependencies only.

This amendment narrows #617 to the service-local adaptation point that can land
safely now without creating a second tracing stack.

## Goal

When a canonical recording span is present in the request context, copy the
already-captured MCP correlation facts from `internal/edgectx` onto that span.
When no recording span is present, behavior remains unchanged.

This makes mctl-telegram ready for the tracer that arrives through the
observability roadmap while keeping exactly one capture path and one correlation
contract.

## Acceptance criteria

- WHEN `Server.audit` executes with a recording span in `ctx` THE SYSTEM
  SHALL set these attributes from the same values already used for audit/slog:
  - `mctl.edge.request_id` <- `edgectx.Context.RequestID`
  - `mctl.edge.route` <- `edgectx.Context.Route`
  - `mcp.method` <- `edgectx.Context.Method`
  - `mcp.name` <- `edgectx.Context.Name`
  - `mcp.protocol_version` <- `edgectx.Context.ProtocolVersion`
  - `mctl.tool.name` <- audited tool name
  - `mctl.tool.status` <- audited status
  - `mctl.user.id` <- authenticated mctl user id
- WHEN any optional correlation value is empty THE SYSTEM SHALL omit that
  attribute rather than writing an empty value.
- WHEN there is no recording span THE SYSTEM SHALL perform no tracing side
  effect and SHALL preserve current audit, DB and slog behavior.
- THE SYSTEM SHALL read correlation data only from the existing
  `edgectx.From(ctx)` value and SHALL NOT re-read HTTP headers or introduce a
  second request-correlation capture path.
- THE SYSTEM SHALL NOT put tool arguments, peer values, handles, message text,
  authorization values or other private payload data on the span.
- THE SYSTEM SHALL treat every edge attribute as evidence only. No value added
  here may become an authorization, identity or policy decision input.
- THE SYSTEM SHALL preserve the span through the existing detached-audit path
  where `context.WithoutCancel` is used.
- THE CHANGE SHALL use only the OpenTelemetry API needed to write attributes to
  an already-existing span. It SHALL NOT install a tracer provider, exporter,
  processor, propagator, HTTP tracing middleware or new sampling policy.
- THE CHANGE SHALL NOT add a `trace_id` audit column, alter the tamper-evident
  audit hash, reintroduce the header probe, repeat the header measurement, or
  create a second correlation identifier.
- Documentation SHALL state that producing/exporting the actual server span is
  owned by mctlhq/.github#55 and its producer-side implementation work; #617 only
  provides the mctl-telegram attribute adapter.

## Dependency boundary

This adapter can merge before the canonical tracer exists because it is inert
without a recording span. End-to-end exported-span evidence is intentionally not
an acceptance gate for #617; it belongs to the observability rollout in
mctlhq/.github#55.

## Out of scope

- header discovery or measurement already completed by #617 Slice 1;
- changes to `edge_request_id`, `edge_route`, MCP method/name or protocol
  persistence already shipped in Slice 2;
- Cloudflare Gateway/DLP work;
- paid-plan/Logpush work to expose Cloudflare per-request datasets;
- a tracer provider, OTLP exporter, collector configuration or trace sampling;
- a new `trace_id` column or audit-chain marker;
- route counters or unrelated metrics;
- changes to authentication, authorization, consent or tool policy.
