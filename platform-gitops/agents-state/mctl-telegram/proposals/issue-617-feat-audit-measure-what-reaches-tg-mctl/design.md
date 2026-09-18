# Design: issue-617-feat-audit-measure-what-reaches-tg-mctl

## Current state

Read in the clone at `d9a3f7f`.

**Capture.** `internal/mcp/server.go:183` builds the MCP handler as
`mcpserver.NewStreamableHTTPServer(s.newMCPServer(), mcpserver.WithHTTPContextFunc(httpContext))`
(`github.com/mark3labs/mcp-go v1.0.0`). `httpContext` at
`internal/mcp/server.go:190` is the single place every tool call's context is
built:

```go
func httpContext(_ context.Context, r *http.Request) context.Context {
	return edgectx.With(r.Context(), edgectx.FromRequest(r))
}
```

**The captured facts.** `internal/edgectx/edgectx.go` defines
`Context{RequestID, Route, MCPMethod, MCPName, ProtocolVersion}`.
`FromRequest` reads `Cf-Ray`, decides `RoutePortal` vs `RouteDirect` from the
presence of `Cf-Worker`, and reads `Mcp-Method`, `Mcp-Name`,
`MCP-Protocol-Version`. `sanitize` (`edgectx.go:98`) drops values longer than
200 bytes or containing non-printable ASCII outright, because a mangled opaque
identifier invites a false join. The package doc records the Slice 1 result
measured on 2026-09-12: `Cf-Ray` arrives on both routes (the zone is proxied,
so it identifies a request, not a route), `Cf-Worker` is the route
discriminator, and the Portal additionally forwards `Mcp-Method`/`Mcp-Name`. It
also records explicitly that whether Cloudflare strips a client-supplied
`Cf-Worker` was **not** measured.

**Persistence.** `internal/db/store.go:1502` (`LogToolCall`) reads
`edgectx.From(ctx)` rather than taking a parameter, so the ~25 existing call
sites were untouched, and inserts the five values (via `nullable`) into
`audit_logs(edge_request_id, edge_route, mcp_method, mcp_name, protocol_version)`.
`internal/db/db.go:138-161` adds those columns with `addColumnIfMissing`,
nullable and with no DEFAULT — a non-NULL default would retroactively change
the canonical hash input of every older row — plus the partial index
`idx_audit_logs_edge_request_id`.

**Tamper evidence.** `internal/db/audit_chain.go:29` `hashAuditEntry` folds the
correlation block into the per-user SHA-256 chain only when at least one field
is set, opened by `auditEdgeMarker = 0x01` and written as length-prefixed
fields. Rows created before the columns existed hash exactly as they did, and
`VerifyAuditChain` (`internal/db/store.go:1580`) re-reads and re-hashes the same
set.

**Read paths.** `db.AuditEntry` (`internal/db/store.go:1227`) carries the five
fields with `,omitempty` JSON tags; `ListAuditFor` selects them. They therefore
appear in `get_my_audit_log` (`internal/mcp/tools.go:998`), its admin
counterpart `get_user_audit_log` (`internal/mcp/tools.go:1499`), and
`GET /api/account/audit` (`internal/web/account.go:138`).
`internal/mcp/audit_edge_test.go:95` guards that both tool descriptions mention
every returned field, by reflecting over `db.AuditEntry`'s JSON tags.

**Logs.** `Server.audit` (`internal/mcp/tools.go:2190`) mirrors the five facts
to `slog` as `edge_route`, `edge_request_id`, `mcp_method`, `mcp_name`,
`protocol_version`, omitting empty ones so a Loki query need not filter them,
and states at `tools.go:2224`:

> This repository has no tracer wired -- opentelemetry is an indirect
> dependency only -- so slog is where these belong today; span attributes wait
> for whoever introduces tracing.

`go.mod` confirms: `go.opentelemetry.io/otel v1.44.0`, `otel/metric`,
`otel/trace` are all `// indirect` (pulled in by `gotd/td`).

**Operator documentation.** `docs/runbook.md:1819` ("Following one call across
the layers") already gives the SQL joins on `edge_request_id` and the
portal/direct split, and states the two cautions: headers as received are
evidence not identity, and one Portal tool call is two upstream requests each
with its own ray.

**What is therefore missing for #617 to close.**

1. No durable, dated, in-repo header table for both routes with a per-candidate
   verdict. The evidence exists only as a three-bullet summary in a Go doc
   comment, and there is no recorded verdict at all for `traceparent`,
   `tracestate` or `CF-Connecting-IP`, which the issue names as candidates.
2. No repeatable way to redo the measurement. `cmd/mcpprobe` measures protocol
   conformance from the client side (`docs/cloudflare-portal-compat.md`); it
   cannot see what the ingress received.
3. No trace leg. Branch A acceptance requires the identifier "as OTel span
   attributes on the tool call"; there is no tracer, no span, and no `trace_id`
   in the audit row, so audit-to-trace joining has no key.
4. No worked example artifact, which is the deliverable
   `mctlhq/.github#35` is waiting on.

## Proposed solution

Four additive changes. Nothing existing is renamed, removed or re-shaped; the
default runtime behaviour without new configuration is byte-for-byte what it is
today.

### 1. `internal/edgectx`: a survey mode for repeatable measurement

Add to the existing package (it is already the one place that knows what a
request-identity fact is):

```go
// HeaderShape describes one inbound header without revealing its value.
type HeaderShape struct {
	Name    string `json:"name"`     // canonical name as received
	Len     int    `json:"len"`      // byte length of the value
	Class   string `json:"class"`    // "hex", "ascii", "opaque", "empty"
	Digest  string `json:"digest"`   // first 8 hex chars of SHA-256(value+salt)
	Secret  bool   `json:"secret"`   // true => Len/Class/Digest omitted
}

func Survey(r *http.Request) []HeaderShape
```

`Survey` walks `r.Header` in sorted order. For `Authorization`, `Cookie`,
`Proxy-Authorization` and `Set-Cookie` it records name and `Secret: true` only.
For everything else it records length, character class, and a truncated digest
under a per-process random salt, which is what makes "is this identifier stable
across three calls?" answerable without ever printing the identifier. This is
the mechanised form of the exact question Slice 1 asked.

`internal/mcp.httpContext` gains one guarded branch: when
`cfg.EdgeHeaderSurvey` is on, emit `slog.Info("edge header survey", "headers",
Survey(r), "route", ctx.Route)` through a token-bucket limiter
(`golang.org/x/time/rate`, already a direct dependency, and
`internal/audit/ratelimit.go` is the in-repo precedent) capped at a few records
per minute. Off by default via a new `EDGE_HEADER_SURVEY` boolean in
`internal/config/config.go` and `.env.example`; when off, `httpContext` is the
one-line function it is today.

The redaction handler in `internal/audit/redact.go` is extended to treat the
survey record as structured data whose values are already shape-only, and a
test asserts no raw header value can reach the handler.

### 2. `internal/tracing`: a real, optional tracer

New package `internal/tracing` with a single entry point:

```go
func Init(ctx context.Context, cfg Config) (shutdown func(context.Context) error, err error)
```

- Promotes `go.opentelemetry.io/otel` and `otel/trace` from indirect to direct
  and adds `go.opentelemetry.io/otel/sdk` plus
  `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp`.
- When `cfg.OTLPEndpoint == ""`, installs nothing: the global tracer stays the
  no-op tracer the OTel API ships, `shutdown` is a no-op, and there is no
  exporter goroutine. This is the default, so the change is inert on a cluster
  with no collector.
- When set, builds a `sdktrace.TracerProvider` with a batch span processor, a
  parent-based sampler over a configurable ratio (default 1.0), and a resource
  carrying `service.name=mctl-telegram` and the build version already passed to
  `mcpserver.NewMCPServer` (`internal/mcp/server.go:205`).
- Sets the global propagator to `propagation.TraceContext{}` so `traceparent`
  and `tracestate` are honoured if the Portal forwards them, and produced on
  outbound calls later without further wiring.

`cmd/server/main.go` calls `tracing.Init` next to the existing metrics
registry setup and defers `shutdown` alongside the server's own shutdown path.

### 3. The span on the tool call, and `trace_id` in audit

`cmd/server/main.go:578` currently builds the MCP chain as

```go
mcpHandler := auth.Middleware(...)(limiter.Middleware()(mcpSrv.HTTPHandler()))
```

Insert `tracing.Middleware()` immediately outside `mcpSrv.HTTPHandler()` — that
is, inside auth, so the span exists for the whole tool dispatch but the
unauthenticated 401 path is not traced. The middleware extracts the inbound W3C
context with the global propagator, starts a server span named from the request
(`MCP <Mcp-Method>` when the header is present, `MCP` otherwise), and ends it
when the handler returns.

`internal/mcp.httpContext` then fills two new string fields on
`edgectx.Context`:

```go
TraceID string // 32-hex w3c trace id, when the span context is valid and sampled
SpanID  string // 16-hex, same condition
```

They are filled in `httpContext` from `trace.SpanContextFromContext(r.Context())`
rather than in `FromRequest`, which stays a pure header reader with no OTel
dependency. `TraceID` is recorded only when the span context is valid **and**
sampled: an unsampled trace id would point the auditor at a trace no backend
holds, which is worse than an empty field, and matches the package's existing
rule that an absent value is a fact and a mangled one invites a false join.

`internal/mcp.Server.audit` (`tools.go:2190`) gains, after its existing slog
block, an attribute set on the current span:

```go
if span := trace.SpanFromContext(ctx); span.IsRecording() {
	span.SetAttributes(
		attribute.String("mctl.tool.name", tool),
		attribute.String("mctl.tool.status", status),
		attribute.Int64("mctl.user.id", uid),
		attribute.String("mctl.edge.request_id", ec.RequestID),
		attribute.String("mctl.edge.route", ec.Route),
		attribute.String("mcp.method", ec.MCPMethod),
		attribute.String("mcp.name", ec.MCPName),
		attribute.String("mcp.protocol_version", ec.ProtocolVersion),
	)
}
```

The attribute names mirror the audit column names one-for-one and are read from
`edgectx.From(ctx)`, the same source the slog block uses — there is no second
capture that could drift from the row.

Empty values are skipped on the same rule the slog block already applies. Only
values already vetted for `audit_logs` are used — never args, peers or bodies.
`auditDetached` keeps working unchanged: `context.WithoutCancel` preserves the
span.

Persistence mirrors the existing pattern exactly:

- `internal/db/db.go`: extend the existing `for _, col := range []string{...}`
  loop with `trace_id` (nullable `TEXT`, no DEFAULT) and add a partial index
  `idx_audit_logs_trace_id ... WHERE trace_id IS NOT NULL`.
- `internal/db/audit_chain.go`: add `TraceID` to `auditEdge`, but write it under
  a **second** marker, `auditTraceMarker = 0x02`, appended after the existing
  `0x01` block and only when non-empty. This is the load-bearing detail: adding
  the field inside the `0x01` block would change the hash input of every
  already-written correlated row and make `VerifyAuditChain` report the whole
  chain as tampered. With a separate marker, every existing row — correlated or
  not — hashes to exactly the same bytes.
- `internal/db/store.go`: `LogToolCall` reads `ec.TraceID`, inserts it via
  `nullable`; `AuditEntry` gains `TraceID string \`json:"trace_id,omitempty"\``;
  `ListAuditFor` and `VerifyAuditChain` select and scan it.

Because `get_my_audit_log`, `get_user_audit_log` and `GET /api/account/audit`
all project `db.AuditEntry`, the field surfaces on all three with no handler
change — and `internal/mcp/audit_edge_test.go:95` will fail until both tool
descriptions document `trace_id`, which is the intended forcing function.

Two existing guards constrain how the field is added, and both were written
because the five current correlation fields broke something once:

- `internal/mcp/output_schema.go:33-84` reflects the result type and then
  strips every `additionalProperties: false` (`openAdditiveFields`). Its doc
  comment records that the Cloudflare portal's frozen tool catalogue rejected
  audit responses with `data/entries/0 must NOT have additional properties`
  after the correlation fields landed (#631/#637). `trace_id` goes through the
  same reflected path, and `TestOutputSchemasStayOpenToAdditiveFields`
  (`internal/mcp/output_schema_open_test.go`) is the proof.
- `internal/audit/redact.go`'s `sensitiveKeys` map is the slog key denylist,
  and AGENTS.md requires new sensitive field names be added to it. `trace_id`
  and the survey record are deliberately *not* added, and the file's existing
  convention — the written-out rationale for `device_pubkey`,
  `credential_domain_id` and `cost_usd` being excluded on purpose — is followed
  with the same kind of comment: a trace id is a random 128-bit identifier that
  discloses nothing, and redacting it would defeat the join the field exists
  for.

### 4. Route visibility and the two documents

`internal/metrics`: add one low-cardinality counter,
`mcp_tool_calls_by_route_total{route}` with `route` in
`{portal, direct, none}`, incremented in `Server.audit` next to the existing
`ToolInvocationsTotal`. `edge_route` is deliberately **not** added as a label to
the existing per-tool counter, which would multiply its cardinality by three.
This counter is what makes a direct-URL bypass of the Portal visible as a rate
rather than as a query somebody has to remember to run — the input
`mctl-telegram#616` asked for.

`docs/reports/edge-headers-617.md`: the Slice 1 artifact. Full observed header
table for both routes with exact names as received, dated, produced by the
survey above; a per-candidate verdict table covering `Cf-Ray`,
`CF-Connecting-IP`, `Cf-Worker`, `traceparent`, `tracestate`, `Mcp-Method`,
`Mcp-Name`, `MCP-Protocol-Version` and everything else observed, each as
`arrives` / `does not arrive` / `arrives but is not stable across calls` /
`not measured (reason)`; at least three repeated Portal calls so a per-request
identifier is distinguished from a constant; and an explicit scope statement
limiting every claim to the measured route and date. It follows the discipline
`docs/cloudflare-portal-compat.md` already sets, where an unrun cell says
`PENDING-OPERATOR` rather than `PASS`.

`docs/reports/correlation-example-617.md`: the worked example. One read-only
tool call by one user through `mcp.mctl.ai`, shown as Portal/Access evidence,
the `get_my_audit_log` JSON entry, and the span with its attributes; the join
keys named explicitly (`trace_id` deterministic between audit and trace,
`edge_request_id` between audit and Portal evidence); the caveats restated from
`docs/runbook.md:1819` (a ray is per request and one Portal tool call is more
than one upstream request; `Cf-Ray` arrives on both routes); and the direct-path
case shown alongside as the bypass signature for `mctl-telegram#616`. A short
pointer from `docs/runbook.md` links it.

## Alternatives

**Skip OTel; record `traceparent` as received and stop there.** Cheapest: one
more captured header, no new dependency, no exporter. Dropped because the
audit row would then reference a trace that `mctl-telegram` never contributes a
span to, so the "trace" leg of the worked example would be somebody else's
data. #617 Branch A asks for span attributes on the tool call, and the example
must show three real layers.

**Emit the span from inside `Server.audit` only, with no HTTP middleware.**
Tempting because `audit` is the one place that already has every fact. Dropped
because `audit` runs at the end of the call: the span would have no duration,
no parent linkage to an inbound `traceparent`, and would miss calls that fail
before dispatch (the protocol-header refusals documented in
`docs/cloudflare-portal-compat.md`). A server span in middleware plus
attributes in `audit` keeps one span per request and one attribute-setting site.

**Put `trace_id` inside the existing `0x01` correlation hash block.** Simpler
code, one marker. Dropped because it would silently invalidate the hash of
every audit row already written with correlation data — `VerifyAuditChain`
would report the chain as tampered, which is precisely the failure mode
`internal/db/db.go:125-137` and `audit_chain.go:40-55` were written to avoid.

**Add `edge_route` as a label on `ToolInvocationsTotal`.** No new metric.
Dropped: it triples the cardinality of a per-tool, per-status vector across
~30 tools for a signal that is one dimension, and route is useful as a
standalone rate.

**A debug endpoint that echoes inbound headers.** Fastest measurement path.
Dropped: an endpoint that reflects arbitrary inbound headers is an exfiltration
primitive for `Authorization` and `Cookie`, and it would have to be reachable
from outside to be useful. The shape-only, rate-limited, default-off log record
answers the same question without ever holding a value in a response body.

## Platform impact

**Migrations.** One nullable `TEXT` column (`audit_logs.trace_id`) plus one
partial index, added through the existing idempotent `addColumnIfMissing` loop
in `internal/db/db.go`, on both SQLite and Postgres. No backfill, no DEFAULT, no
rewrite of existing rows.

**Backward compatibility.** Additive only. Existing audit rows hash identically
because the new field lives under its own marker block written only when
non-empty; `VerifyAuditChain` on an untouched database returns exactly what it
returns today. Response shapes gain one `,omitempty` field, so a consumer that
ignores unknown keys — which is every consumer, given the five fields added by
the current implementation — is unaffected. `docs/portal-allowlist.json` and
`internal/mcp/output_schema.go` need the new field reflected; the existing
`output_schema_test.go` and `portal_allowlist_test.go` guards will say so.

**Resource impact.** With tracing unconfigured: no exporter, no batch
processor, no goroutine, no allocation beyond a nil-check per audited call.
With tracing configured at ratio 1.0: one span per MCP HTTP request, batched
over OTLP/HTTP. MCP tool-call volume in this service is low (see the SLO
recording rules in `docs/slo.md`), so the export volume is small; the ratio is
configurable if that stops being true. The survey adds nothing while disabled,
and one rate-limited log record per few seconds while enabled.

**Risks and mitigations.**

- *A header survey leaks a credential.* Mitigated by an explicit secret-header
  set recorded as name-only, by shape-and-digest instead of value for
  everything else, by default-off, and by a test that feeds an
  `Authorization: Bearer ...` request through `Survey` and asserts the token
  cannot be recovered from the output.
- *Trace ids become an authorization or trust signal.* Mitigated by keeping the
  `edgectx` doctrine verbatim: every one of these fields is evidence, never an
  authorization input. The admin tool description already carries the
  "EVIDENCE, NOT AS IDENTITY" warning asserted by
  `internal/mcp/audit_edge_test.go`; `trace_id` joins that sentence.
- *A sampled-out trace id misleads an auditor.* Mitigated by writing `trace_id`
  only when the span context is valid and sampled, and by defaulting the ratio
  to 1.0.
- *The OTLP exporter blocks or backs up.* Mitigated by the batch processor's
  bounded queue (spans are dropped, never blocking the request), by a bounded
  `shutdown` timeout, and by tracing being off by default.
- *Cf-Worker is forgeable by a direct caller.* Unchanged from today and
  explicitly unmeasured; mitigated by the evidence document recording it as an
  open `not measured` row with a re-measurement step, and by nothing in mctl
  granting on `Route`.
- *The tracer bootstrap turns out to be owned by a platform-wide roadmap
  child.* Mitigated by keeping `internal/tracing` a thin, single-entry-point
  package and by naming the span attributes to the already-circulated mapping:
  if a platform tracer arrives, `tracing.Init` and the middleware are deleted
  and the attribute block in `Server.audit` plus the `trace_id` column stand
  unchanged.
- *Coordination with `mctl-telegram#568`.* `protocol_version` is already the
  shared column and this proposal does not touch its semantics; the new
  `trace_id` is orthogonal. Nothing here blocks or duplicates #568.
