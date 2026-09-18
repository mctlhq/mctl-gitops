# Design: #617 current-state OTel adapter

## Current state

The correlation contract is already implemented.

`internal/mcp.httpContext` captures the request once with
`edgectx.FromRequest(r)` and stores it in context. `Server.audit` reads that
same `edgectx.Context`, writes the existing audit row through the DB layer and
mirrors the correlation facts to slog.

The relevant current code comment in `internal/mcp/tools.go` already states
the intended boundary: this repository has no tracer wired, so span attributes
wait for whoever introduces tracing.

The issue history has since made that owner explicit:
mctlhq/.github#55 is the vendor-neutral observability epic. Therefore #617 must
not introduce its own provider/exporter/middleware stack.

## Proposed change

Add one small adapter adjacent to the existing audit correlation block.

Conceptually:

```go
func setAuditSpanAttributes(
    ctx context.Context,
    ec edgectx.Context,
    tool string,
    status string,
    userID int64,
) {
    span := trace.SpanFromContext(ctx)
    if !span.IsRecording() {
        return
    }

    attrs := auditSpanAttributes(ec, tool, status, userID)
    if len(attrs) != 0 {
        span.SetAttributes(attrs...)
    }
}
```

`auditSpanAttributes` is a pure helper that omits empty optional fields. This
keeps the important behavior testable without installing an SDK/provider in
production code.

The helper is called by `Server.audit` after the same
`ec := edgectx.From(ctx)` lookup used for slog. There is no second header
capture and no new correlation identifier.

## Attribute contract

| Span attribute | Existing source |
| --- | --- |
| `mctl.edge.request_id` | `edgectx.Context.RequestID` |
| `mctl.edge.route` | `edgectx.Context.Route` |
| `mcp.method` | `edgectx.Context.MCPMethod` |
| `mcp.name` | `edgectx.Context.MCPName` |
| `mcp.protocol_version` | `edgectx.Context.ProtocolVersion` |
| `mctl.tool.name` | existing audited tool name |
| `mctl.tool.status` | existing audited status |
| `mctl.user.id` | authenticated mctl user id |

No arguments, peer strings, message bodies, handles or authorization values are
eligible attributes.

## Dependency shape

mctl-telegram may move the already-present OpenTelemetry API modules from
`// indirect` to direct dependencies if required by Go module resolution,
because this adapter imports the API. It must not add the OpenTelemetry SDK,
OTLP exporter, batch processor, sampler, resource bootstrap, global propagator
or tracing middleware.

That distinction is deliberate:

```text
mctlhq/.github#55
   owns provider / exporter / propagation / sampling
             |
             v
request context contains canonical recording span
             |
             v
mctl-telegram #617 adapter
   reads existing edgectx once
             |
             +--> existing audit row
             +--> existing slog line
             +--> span attributes
```

With no recording span the adapter returns immediately, so this change can ship
before #55 reaches mctl-telegram.

## Detached audit

The existing detached-audit path uses `context.WithoutCancel`. That preserves
context values while removing cancellation/deadline, so the active span value is
still available to the adapter. No separate span is created for detached audit.

## Tests

Test the pure `auditSpanAttributes` helper for exact keys, values and omission
of empty fields. Add a no-recording-span regression that calls the adapter with
`context.Background()` and proves it is a no-op/panic-free. Do not pull an
OpenTelemetry SDK/provider into production merely to test this adapter.

If/when #55 supplies the canonical tracer, that work owns the end-to-end test
that proves an actual exported server span carries these attributes.

## Security and privacy

The adapter only copies values already admitted to the audit/slog correlation
contract. It introduces no new header parsing. Edge facts stay evidentiary and
must never gate identity, authentication, authorization or policy.

## Rollback

Revert the adapter call and helper. There is no DB migration, hash-format
change, exporter state or generated correlation id to unwind. Existing audit
rows and slog output are unaffected.
