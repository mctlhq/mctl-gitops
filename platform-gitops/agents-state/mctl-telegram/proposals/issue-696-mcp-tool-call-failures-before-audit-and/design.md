# Design: issue-696-mcp-tool-call-failures-before-audit-and

## Current state

### How a tool call is served

`Server.HTTPHandler` (`internal/mcp/server.go:227`) wraps
`mcpserver.NewStreamableHTTPServer(s.newMCPServer(), mcpserver.WithHTTPContextFunc(httpContext))`.
`httpContext` (`internal/mcp/server.go:239`) is the only ctx decoration in the
chain: it stores `edgectx.FromRequest(r)` (Cf-Ray, portal/direct route, the
`Mcp-Method` / `Mcp-Name` / `MCP-Protocol-Version` headers) so the audit write
and the slog mirror can correlate a call to the edge.

`newMCPServer` (`internal/mcp/server.go:247`) is the single enumeration of the
tool set — 36 `s.addTool` / `s.addToolUI` pairs. It passes only
`mcpserver.WithToolCapabilities(true)` plus, when `AppsEnabled`, the resource
and extension options. It installs **no** `WithHooks`, **no**
`WithToolHandlerMiddleware`, **no** `WithRecovery`, and neither
`WithInputSchemaValidation` nor `WithOutputSchemaValidation` (verified by grep
across the repo: zero hits). So in `mark3labs/mcp-go@v1.0.0`
`MCPServer.inputValidator` and `outputValidator` are nil and
`s.toolHandlerMiddlewares` is empty.

### Where the recording happens today

Everything funnels through `Server.audit` (`internal/mcp/tools.go:2318`),
which does three things in order:

1. `s.Store.LogToolCall(ctx, uid, tool, peer, status, msg, cp)` — one audit row.
2. When `s.Metrics != nil && !startedAt.IsZero()`, observes
   `ToolInvocationDuration{tool}` and increments
   `ToolInvocationsTotal{tool,status}`.
3. Mirrors to slog: `slog.Info("mcp tool call", …)` on success,
   `slog.Warn("mcp tool call", …, "err", audit.ScrubText(msg))` on failure,
   after appending the `edgectx` correlation fields and copying the same facts
   onto any recording span via `setAuditSpanAttributes`
   (`internal/mcp/audit_span.go:54`).

`auditDetached` (`internal/mcp/tools.go:2399`) is the same call on a
`context.WithoutCancel` ctx bounded by `auditWriteTimeout = 5s`, used where the
caller's ctx may already be dead.

`status` is derived solely from whether the `err` argument is nil. There is no
`reason`.

### The blind spots, precisely

**1. Early returns.** `s.audit` is called from inside each handler, so it only
runs if control reaches it. `toolSearchMessages` is representative:

```go
if err := requireScope(id, "telegram:messages:read"); err != nil {
    return mcplib.NewToolResultError(err.Error()), nil      // no audit
}
...
if query == "" {
    return mcplib.NewToolResultError("query is required"), nil   // no audit
}
if s.Hub != nil { /* mode=="local" */
    return mcplib.NewToolResultError("search_messages is not yet supported for local-bridge accounts"), nil  // no audit
}
```

Counting `s.audit` call sites per tool builder across `tools.go`,
`media_tools.go`, `broadcast_tools.go` and `apps.go`, every tool has at least
one audited branch except three that have none at all:
`get_my_send_status`, `get_my_identity`, `get_my_audit_log`. The last carries
an explicit comment that this is deliberate ("we intentionally do NOT
audit-log this call itself — it would create a recursive audit-of-audit row on
every page fetch").

**2. JSON-RPC errors.** In `mcp-go@v1.0.0`, `handleToolCall`
(`server/server.go:2026`) rejects an unknown tool and a `ToolFilter`-excluded
tool with `requestError{code: mcp.INVALID_PARAMS, err: …ErrToolNotFound}`
*before* resolving a handler. `handleRequest` (`server/request_handler.go:505`)
rejects an unparsable `tools/call` body with `INVALID_REQUEST` +
`*UnparsableMessageError`, and a disabled tools capability with
`METHOD_NOT_FOUND`. All three funnel into
`s.hooks.onError(ctx, id, method, &request, err)` and then
`err.ToJSONRPCError()`. With no hooks registered, `onError` is a no-op and the
failure is invisible to this repository. The response is still HTTP 200 with a
JSON-RPC error body.

**3. Post-audit encode failure.** `jsonResult` (`internal/mcp/tools.go:2308`)
returns `mcplib.NewToolResultError("encode: " + err.Error())` and
`toolSearchMessages` has the same inline `json.MarshalIndent` fallback. Both
run *after* the handler already wrote an `ok` row.

### Why the row cannot simply be amended

`audit_logs` is a tamper-evident hash chain. `LogToolCall`
(`internal/db/store.go:1745`) reads the user's last `entry_hash`, computes
`hashAuditEntry(prev, userID, tool, peer, status, errMsg, callPath, createdAt, edge)`
(`internal/db/audit_chain.go:29`), and inserts `prev_hash` + `entry_hash`.
`Store.VerifyAuditChain` recomputes the whole chain. An `UPDATE` of a written
row would break verification for that user from that row onwards. Any fix that
needs to correct a status therefore has to decide the status **before** the
row is written.

`hashAuditEntry` already shows how to extend the hashed field set without
invalidating history: `call_path` is appended only when `callPath.Valid`, and
the five correlation fields are appended as a block prefixed by
`auditEdgeMarker = 0x01` only when at least one is set. Rows written before
either existed hash exactly as they did then.

### Test surface that constrains the change

`internal/mcp` tests construct `&Server{Store: newToolsTestStore(t)}` against
an in-memory SQLite store, call `tool, handler := srv.toolXxx()` and invoke
`handler(ctx, req)` **directly**, then assert with `latestAudit`
(`internal/mcp/tools_test.go:193`) — e.g. `TestToolSetAccountMode_AuditsRefusals`,
`TestToolProvisionLocalAccount_AuditsSuccessAndRefusal`. Dozens of tests depend
on `s.audit` writing its row synchronously during a direct handler call. There
is also an in-process JSON-RPC harness: `callRPC` in
`internal/mcp/apps_surface_test.go:27` drives `srv.HandleMessage(ctx, raw)`
against `(&Server{…}).newMCPServer()`. slog is captured by swapping
`slog.SetDefault` with a `slog.NewJSONHandler` over a `bytes.Buffer`
(`internal/mcp/audit_edge_test.go:24`).

## Proposed solution

Four pieces, all inside `internal/mcp` except a nullable column and a hash-block
append in `internal/db` and one counter in `internal/metrics`.

### A. A closed reason taxonomy — new `internal/mcp/reasons.go`

Compile-time constants only, never a client string:

| constant | value | raised by |
| --- | --- | --- |
| `ReasonAuthRequired` | `auth_required` | `requireScope` / `requireAnyScope` with nil identity |
| `ReasonScopeDenied` | `scope_denied` | `requireScope` scope miss |
| `ReasonInvalidArgument` | `invalid_argument` | empty/malformed argument checks |
| `ReasonModeUnsupported` | `mode_unsupported` | Local-Bridge mode refusals |
| `ReasonRefused` | `refused` | demo-reviewer and policy refusals |
| `ReasonRateLimited` | `rate_limited` | `audit.RateLimiter` blocks |
| `ReasonNotFound` | `not_found` | unknown device / expired media ref / unknown confirmation |
| `ReasonConfirmationRejected` | `confirmation_rejected` | `internal/mcp/confirm.go` mismatches |
| `ReasonTelegramError` | `telegram_error` | `borrowWithRetry` / MTProto failures |
| `ReasonBridgeError` | `bridge_error` | `bridgeResultErr` failures |
| `ReasonStoreError` | `store_error` | `*db.Store` failures |
| `ReasonEncodeFailed` | `encode_failed` | `jsonResult` marshal failure |
| `ReasonHandlerError` | `handler_error` | handler returned a non-nil Go error |
| `ReasonPanic` | `panic` | recovered panic |
| `ReasonUnknown` | `unknown` | `IsError` result the wrapper could not classify |
| `ReasonToolNotFound` | `tool_not_found` | JSON-RPC, `ErrToolNotFound` |
| `ReasonUnparsableMessage` | `unparsable_message` | JSON-RPC, `*UnparsableMessageError` |
| `ReasonCapabilityDisabled` | `capability_disabled` | JSON-RPC, `ErrUnsupported` |
| `ReasonJSONRPCError` | `jsonrpc_error` | any other JSON-RPC `tools/call` error |

Reasons reach the recorder two ways. Handlers that already build the error can
state it explicitly; anything else is inferred by the wrapper from a small
classifier over the result's first text block (prefix match on the same
literals the handlers produce: `"authentication required"`,
`"identity missing scope "`, `"encode: "`, `" is not yet supported for
local-bridge accounts"`, …), falling back to `ReasonUnknown`. The classifier is
a best-effort narrowing of an otherwise-unlabelled bucket, never an
authorization input, and it is exercised by a table test that enumerates every
literal it matches.

### B. Staged recording with a write-through fallback — `internal/mcp/record.go`

A per-call recorder is placed in ctx by the wrapper:

```go
type callRecord struct {
    tool, peer, status, reason, errMsg, callPath string
    elapsed  time.Duration
    hasElapsed bool
    id       *auth.Identity
}

type callRecorder struct {
    mu      sync.Mutex
    staged  []callRecord   // in the order handlers produced them
}
```

`Server.audit` keeps its exact signature and gains one branch at the top: if
`recorderFrom(ctx)` returns a recorder, it **stages** a `callRecord` (computing
`time.Since(startedAt)` now, so durations stay honest) and returns; if there is
none it writes through immediately, byte-for-byte as today. The write-through
branch is what keeps every existing direct-handler test green — those tests
never install a recorder. `auditDetached` is unchanged and delegates to the same
function.

The wrapper flushes. Flush rules:

1. If the final result is `IsError=true` (or the handler returned an error, or
   panicked) and **at least one** record was staged, the **last** staged
   record's `status` is forced to `error` and its `reason` set — this is the
   `jsonResult` encode case, resolved before the row is written rather than by
   amending a chained row.
2. If the final result is `IsError=true` and **no** record was staged, the
   wrapper synthesises one from `req.Params.Name`, the ctx identity, the
   inferred reason and the wall-clock elapsed since wrapper entry. This is the
   fix for every early return.
3. If the result is successful and no record was staged, the wrapper
   synthesises an `ok` record — except for tools on `auditExemptOnSuccess`
   (`get_my_audit_log`), which keeps that tool's deliberate no-audit-of-audit
   property while still recording its failures.
4. All staged records are written in order through the existing
   `Server.audit` write-through path, on a `context.WithoutCancel` +
   `auditWriteTimeout` context, so a client disconnect can no longer drop the
   row.
5. On an error outcome the wrapper increments
   `mctl_tool_call_errors_total{tool, reason}` exactly once for the call,
   using the canonical `req.Params.Name` (not the suffixed audit name such as
   `send_message:sent`) so the label set matches
   `mctl_tool_invocations_total{tool}`.

Because staging happens through `Server.audit`, the rich per-branch tool names
(`send_message:draft`, `pin_message:blocked`, `send_media:via-bridge`) and
`call_path="local"` survive untouched, as does the existing
`ToolInvocationsTotal` / `ToolInvocationDuration` behaviour.

The wrapper also **absorbs** handler failures: a non-nil Go error or a
recovered panic is recorded and then converted into
`mcplib.NewToolResultError(...)`, so `handleToolCall` never produces an
`INTERNAL_ERROR` for a registered tool. This is deliberate: it puts the failure
into the model's context window (the same reasoning `mcp-go` applies to
validation errors), and — the load-bearing consequence for this design — it
makes the middleware and the JSON-RPC hook **disjoint by construction**. Neither
needs to know about the other, so no shared dedup state has to cross the
ctx boundary between the dispatcher and the handler chain.

### C. Registration — `internal/mcp/server.go`

`newMCPServer` gains two options:

```go
opts := []mcpserver.ServerOption{
    mcpserver.WithToolCapabilities(true),
    mcpserver.WithToolHandlerMiddleware(s.recordToolCall),
    mcpserver.WithHooks(s.jsonrpcHooks()),
}
```

`recordToolCall(next mcpserver.ToolHandlerFunc) mcpserver.ToolHandlerFunc` is
the wrapper from (B). Registering it as a server option rather than wrapping
each `addTool` pair means a tool added later is covered automatically — the
"cannot reintroduce the blind spot" requirement.

`jsonrpcHooks()` returns a `*mcpserver.Hooks` with a single `AddOnError` that
ignores every method except `mcp.MethodToolsCall` and emits:

```go
slog.Warn("mcp jsonrpc error",
    "mcp_method", "tools/call",
    "tool", requestedToolName,       // from the *mcp.CallToolRequest, "" if unparsable
    "jsonrpc_code", code,
    "reason", reason,
    "user_id", uid,                  // 0 when unauthenticated
    "edge_request_id", ec.RequestID,
    "edge_route", ec.Route,
)
```

The JSON-RPC code is obtained without reaching into `mcp-go`'s unexported
`requestError`: that type has an **exported method** `ToJSONRPCError() mcp.JSONRPCError`
(`server/server.go:170`), so an interface assertion works from outside the
package:

```go
type jsonrpcCoder interface{ ToJSONRPCError() mcplib.JSONRPCError }
```

The reason is derived from sentinels `mcpserver.ErrToolNotFound`,
`mcpserver.ErrUnsupported` and `*mcpserver.UnparsableMessageError` via
`errors.Is` / `errors.As`, falling back to `ReasonJSONRPCError`. The hook
increments the same counter. No arguments are logged — only
`request.Params.Name`, which is a tool name the client asked for, not user
data.

Hook ordering is safe: `handleRequest` calls
`s.hooks.beforeCallTool` then `handleToolCall`, and fires `onError` only when
`handleToolCall` returned a `*requestError`. Since (B) guarantees registered
handlers never return one, a `tools/call` produces either the middleware's
record **or** the hook's line, never both.

### D. Persisting `reason`

- `internal/db/db.go`: one line in `Migrate`, next to the existing
  `audit_logs` column adds —
  `addColumnIfMissing(ctx, dbConn, pg, "audit_logs", "reason", "TEXT", "TEXT")`.
  Following the `call_path` precedent, it is **not** added to the
  `sqliteSchema()` / `pgSchema()` CREATE TABLE literals.
- `internal/db/audit_chain.go`: a new terminal block in `hashAuditEntry`,
  written only when `reason != ""`, opened by `auditReasonMarker = 0x02`
  (distinct from `auditEdgeMarker = 0x01`) so `("edge set, reason unset")` and
  `("edge unset, reason set")` cannot serialize identically. Every row written
  before this change has an empty reason and therefore hashes exactly as
  before — `VerifyAuditChain` stays green across the upgrade, which a
  regression test pins.
- `internal/db/store.go`: `LogToolCall` gains a trailing `reason string`
  parameter and writes it with `nullable(reason)`; `AuditEntry` gains
  `Reason string \`json:"reason,omitempty"\``; `ListAuditFor` and
  `VerifyAuditChain` select the new column.
- `internal/mcp/tools.go`: `auditLogResult`'s `outputSchema` reflects the new
  field automatically; `toolGetMyAuditLog`'s description text gains `reason` in
  its documented output field list.

### E. The counter — `internal/metrics/metrics.go`

```go
r.ToolCallErrorsTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
    Name: "mctl_tool_call_errors_total",
    Help: "MCP tool-call failures, labeled by tool and a closed-set reason.",
}, []string{"tool", "reason"})
```

Named `mctl_tool_call_errors_total`, not the issue's
`mctl_telegram_tool_call_errors_total`, because `mctl_telegram_*` in this
repository denotes the MTProto client subsystem
(`mctl_telegram_client_errors_total`, `mctl_telegram_flood_wait_events_total`)
while the MCP tool layer is `mctl_tool_*`. Added to `expectedMetricNames` in
`internal/metrics/metrics_test.go`, to `deploy/grafana/mctl-telegram-beta.json`
as an error-breakdown panel, and documented in `docs/runbook.md` under the
existing tool-availability material. Not pre-created at zero — see Open
questions in requirements.md.

### Redaction invariants

Nothing new is logged. The wrapper never touches `req.GetArguments()`. Peer
values come only from what handlers already passed to `Server.audit` (always
`telegram.RedactPeer(...)`); a synthesised record has an empty peer, because
the wrapper refuses to parse the arguments to find one. Error text keeps
passing through `audit.ScrubText` before it reaches slog. The `reason` label is
a compile-time constant. `internal/audit/redact.go` needs no new field names.

## Alternatives

**1. Add the missing `s.audit` calls to each early return.** Roughly 60 return
sites across `tools.go`, `media_tools.go`, `broadcast_tools.go` and `apps.go`.
It is the smallest conceptual change and needs no `mcp-go` knowledge, but it
fixes only the blind spots that exist today: the next tool, or the next early
return added to an existing tool, reintroduces the bug, and the issue
explicitly asks for "one recording path". It also cannot reach the JSON-RPC
errors or the post-audit encode case at all. Dropped.

**2. Wrap each handler at the `addTool` / `addToolUI` call site instead of
registering server middleware.** Mechanically similar and slightly more
explicit, and it would let a per-tool opt-out be expressed at the registration
line. Dropped because a new tool registered without the wrapper is silently
uncovered — the same class of omission the issue is about — whereas
`WithToolHandlerMiddleware` applies to the whole server, including the
conditionally-registered `prepare_send_message` and the four broadcast tools
added through a loop.

**3. Record from an HTTP middleware around `HTTPHandler`, parsing the JSON-RPC
body.** This is the only option that also sees the pre-dispatch failures
`mcp-go` answers with `createErrorResponse` (outer parse error, bad `jsonrpc`
version, invalid protocol version) — the residual gap listed in Out of scope.
Dropped for this change: it means re-parsing the request body on every call,
re-implementing batch and notification semantics, handling the streamable-HTTP
SSE response shape, and — worst — it has no access to the `*mcplib.CallToolResult`,
so it could not distinguish an `IsError=true` result from a success at all. It
remains the right home for the residual gap if that gap ever becomes
operationally material.

**4. Amend the audit row when a post-audit encode failure occurs.** The most
direct reading of "never audited as ok". Dropped outright: `audit_logs` is a
per-user SHA-256 hash chain (`internal/db/audit_chain.go`), so an `UPDATE`
would make `Store.VerifyAuditChain` report the user's history as tampered from
that row onwards. Staging the record and deciding the status before the write
(B.1) achieves the same outcome with an append-only store.

**5. Defer *all* audit writes to the wrapper with no write-through fallback.**
Cleaner in principle — one writer, no dual mode. Dropped because dozens of
existing tests call handlers directly without a server and assert the row
synchronously via `latestAudit`; they would all need rewriting through
`callRPC`, turning a focused observability fix into a large test migration and
obscuring the actual behaviour change under review.

## Platform impact

**Migration.** One nullable `TEXT` column on `audit_logs`, added by the
existing idempotent `addColumnIfMissing` path in `Migrate` — no separate
migration artefact, no backfill, no downtime, no lock of consequence (Postgres
`ADD COLUMN` with no default is metadata-only). Existing rows keep `reason`
NULL.

**Backward compatibility.**
- *Audit chain*: preserved by construction — the reason block is hashed only
  when non-empty, behind its own marker byte, exactly as `call_path` and the
  correlation block already are. A regression test must write rows with the
  pre-change code path (reason empty), then verify the chain after the change.
- *Rollback*: a binary rolled back after the column exists writes rows with no
  reason and hashes over the pre-change field set — those rows verify under
  both binaries. Forward-rolling again is likewise safe. The column itself is
  never dropped.
- *`get_my_audit_log` output*: gains an optional `reason` field. Additive and
  `omitempty`, so a client reading the documented field list is unaffected;
  the tool's `outputSchema` changes, which `internal/mcp/output_schema_test.go`
  and `output_schema_open_test.go` will notice.
- *Client-visible behaviour*: one deliberate change — a handler that returns a
  Go error previously surfaced as JSON-RPC `INTERNAL_ERROR` and now surfaces
  as an `IsError=true` tool result. No registered handler returns a non-nil
  error today (verified by grep: the only `return nil, err` sites in
  `internal/mcp` are helper functions and `handleReadAppResource`), so this is
  a safety net, not an observable change.

**Resource impact.**
- *Audit volume*: new rows only for calls that previously produced none —
  failing early-return paths (rare), plus successful `get_my_identity` and
  `get_my_send_status` calls (low frequency, self-introspection tools).
  `get_my_audit_log` successes stay unaudited. Expect a low single-digit
  percentage increase in `audit_logs` growth.
- *Metrics*: `mctl_tool_call_errors_total` creates a child series only on first
  occurrence of a `(tool, reason)` pair. Realistic steady state is tens of
  series; theoretical ceiling ~650 (36 tools x 18 reasons), all from
  compile-time constants.
- *Latency*: one mutex-guarded slice append per `s.audit` plus one prefix-match
  classification per erroring call. Negligible against a Telegram round trip.
  The flush writes the same number of rows as today in the common case.

**Risks and mitigations.**
- *Double-recording.* Mitigated structurally: `Server.audit` stages instead of
  writing when a recorder is present, and the middleware/hook split is disjoint
  because the middleware absorbs handler errors. Pinned by an explicit
  "exactly one row, exactly one line" test on the success path and on each
  error path.
- *Misclassified reason.* String-prefix inference is inherently brittle. Bounded
  by: handlers may state their reason explicitly where it matters, the fallback
  is the honest `unknown` rather than a wrong label, and a table test
  enumerates every literal the classifier matches so a reworded handler message
  fails CI instead of silently degrading to `unknown`.
- *Flush skipped on panic.* The wrapper's `recover` runs in a `defer` that also
  performs the flush, so a panicking handler still produces its record.
- *Detached write masks a real cancellation.* Already the established pattern
  (`auditDetached`, `auditWriteTimeout = 5s`); the bound is unchanged.
- *Silent audit-write failure.* `LogToolCall` still swallows `BeginTx` /
  `INSERT` / `Commit` errors, so a DB outage keeps the blind spot for the row
  itself. The slog line and the counter are emitted independently of the DB
  write, so the call remains visible in Loki and VictoriaMetrics even then —
  which is the operational property #696 actually needs. Making `LogToolCall`
  report its own failures is listed as out of scope and should get its own
  issue.
- *`mcp-go` internals drift.* The design depends on three facts about
  `mark3labs/mcp-go@v1.0.0`: middleware wraps only resolved handlers,
  `onError` fires for every `tools/call` dispatcher error, and `requestError`
  exposes `ToJSONRPCError()`. A version bump could change any of them. Pinned
  by end-to-end tests through `srv.HandleMessage` (the `callRPC` harness),
  which fail loudly rather than degrading silently.
