# Tasks: #617 correlation-to-OTel adapter

## Baseline — already complete, do not reimplement

- [x] Slice 1: measure the full inbound header set for Portal and direct routes.
- [x] Slice 1: establish `Cf-Ray` semantics and `Cf-Worker` route evidence.
- [x] Slice 1: measure absence of inbound W3C trace context.
- [x] Slice 1: remove the temporary header probe after measurement.
- [x] Slice 2: persist `edge_request_id`, `edge_route`, `mcp_method`,
      `mcp_name`, `protocol_version`.
- [x] Slice 2: expose those fields through audit tools and mirror them to slog.
- [x] Slice 2: publish a worked Portal call -> audit-row example.
- [x] Slice 2: measure direct-client `Cf-Worker` forgery behavior.
- [x] Slice 2: resolve the client-leg ray question and document the current
      principal+time Cloudflare-side fallback.

## Remaining implementation

- [ ] 1. Add a pure `auditSpanAttributes` helper next to the MCP audit
      correlation code. It builds OpenTelemetry `attribute.KeyValue` entries
      for:
      `mctl.edge.request_id`, `mctl.edge.route`, `mcp.method`,
      `mcp.name`, `mcp.protocol_version`, `mctl.tool.name`,
      `mctl.tool.status`, `mctl.user.id`.
      DoD: optional empty values are omitted; no tool arguments, peer, message,
      handle or authorization data is accepted by the helper signature.

- [ ] 2. Add `setAuditSpanAttributes(ctx, ...)` using
      `trace.SpanFromContext(ctx)`. Return immediately unless
      `span.IsRecording()`; otherwise apply the output of task 1.
      DoD: no provider/exporter/middleware is created and a background context
      is a no-op.

- [ ] 3. Call the adapter from `Server.audit` using the same
      `edgectx.From(ctx)` value already used for the existing correlation
      slog block.
      DoD: there is exactly one edge-context read/capture path; audit DB and
      slog behavior remain unchanged.

- [ ] 4. Make only the OpenTelemetry API dependencies required by tasks 1-3
      direct in `go.mod` as produced by `go mod tidy`.
      DoD: no `otel/sdk`, OTLP exporter, batch processor, sampler, resource
      bootstrap, propagator setup or HTTP tracing middleware is introduced.

- [ ] 5. Update the #617/runbook documentation to mark Slice 1/2 as shipped and
      state the ownership boundary: this adapter is mctl-telegram's hook;
      tracer/provider/exporter/propagation belongs to mctlhq/.github#55.
      Preserve the measured caveats: `Cf-Ray` is per request, not a route;
      one Portal tool call may create multiple upstream requests; edge values
      are evidence, never identity/authorization.

## Tests

- [ ] T1. Exact attribute mapping: populate every existing `edgectx.Context`
      correlation field and assert the helper returns the eight canonical keys
      with the expected values.

- [ ] T2. Empty omission: empty optional edge/MCP fields do not produce empty
      attributes; tool name/status/user id remain represented according to the
      audit call contract.

- [ ] T3. Sensitive-data surface: the helper API has no arguments for tool
      input, peer, handle, message body, authorization or arbitrary headers.

- [ ] T4. No-span behavior: calling the adapter with
      `context.Background()` is a no-op and does not panic.

- [ ] T5. Detached-audit regression: the existing
      `context.WithoutCancel` path continues to carry context values and does
      not create a second span.

- [ ] T6. Full repository checks required by mctl-telegram CI pass on the
      implementation head.

## Explicitly not tasks in this proposal

- reintroducing `MCP_HEADER_PROBE` / a header survey;
- repeating live Portal/direct measurements;
- creating `internal/tracing`;
- installing a TracerProvider or OTLP exporter;
- adding tracing HTTP middleware or a new propagator;
- adding `trace_id` to `audit_logs` or changing the audit hash;
- adding a second request id;
- creating route metrics unrelated to the remaining #617 acceptance item.

## Rollback

Revert the adapter/helper and its API imports. No migration or data rollback is
required.
