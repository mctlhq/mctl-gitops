# Design: issue-813-feat-audit-audit-reads-made-under-the-su

## Current state

Support scope:
- `internal/auth/agent_scope.go` defines `AgentScopeSupport` (`BoundTenant: true`, `MintByTenantMember: true`, TTL 10m/1h). It also defines `supportTools`, `supportTenantTools`, the REST route list and `AgentScope.Allows` / `AllowsToolCall`.
- `internal/auth/agent.go`: `NewAgentUser` carries `execID`, `workItemID`, `runID`, `agentScope`, `boundTenant` and `runRequestedBy`. Accessors are `ExecutionID()`, `WorkItemID()`, `AgentRunID()`, `BoundTenant()` and `AgentRunRequestedBy()`.

Enforcement points:
- REST: `Handlers.agentScopeGate` (`internal/api/agent_scope_gate.go`) is mounted in `internal/api/router.go` (`r.Use(h.agentScopeGate)`, ~line 503). It runs after auth and before `agentPrincipalGate`. On refusal it increments `mctl_agent_scope_decisions_total` and writes one audit entry (`Operation: "agent_scope.denied"`, `Status: "denied"`, params with agent, scope, route, execution_id, bound_tenant). Admitted requests call `next` and write no audit row.
- MCP: `Server.agentScopeMiddleware` (`internal/mcp/agent_scope.go`) is registered in `NewMCPServer` (`internal/mcp/server.go` ~line 224) inside the tracing and receipt middlewares. A refusal returns `agent_scope_denied` and only logs with `slog.Warn`. The MCP package has no audit sink. The only MCP-to-audit path today is `SetAgentReceiptGate(h, mode)`, where `Handlers` implements the verifier and audits through `logAuditCtx` (`internal/api/agent_receipt_gate.go` ~line 205).
- MCP tools reach data through loopback REST calls with the caller's token (`Server.apiGet` / `doRequest`, `internal/mcp/server.go` ~2429-2495), using `tracingTransport` (`internal/mcp/tracing.go`). That transport already copies a context value (`ShadowAgentScopeFromContext`) onto a loopback header. As a result, one MCP tool call today passes through both the MCP scope check and the REST gate.

Audit storage:
- `internal/audit/logger.go`: `Entry` already has `PrincipalID`, `ViaPrincipalID`, `ViaExecutionID` (database-only, `json:"-"`). `Log` is the interface (`Log`, `List`, `LookupByWorkflow`, `UpdateStatus`, `ListByStatus`). The in-memory `Logger` is the fallback.
- `internal/audit/postgres.go`: the `audit_events` schema has the columns `user_principal_id`, `via_principal_id` and `via_execution_id`. The `via_execution_id` comment says "Write-only: nothing reads it back yet". `PostgresLogger.Log` inserts synchronously with a 5s timeout. On failure it only calls `slog.Error("audit postgres: insert failed")`, with no metric. Indexes are created `CONCURRENTLY` in a separate loop, and a failure there only logs a warning.
- `internal/api/clientmeta.go` `logAuditCtx` stamps client IP, UA and request id. It fills `PrincipalID` / `ViaPrincipalID` / `ViaExecutionID` from the context user when `u.ID == entry.UserID` and the fields are empty. For an agent user `ViaPrincipalID()` is "", so `via_principal_id` stays empty today.
- `internal/api/handlers_read.go` `ListAudit` (`GET /api/v1/audit`, router ~571) returns `List(50)` filtered by tenant access. `mctl_list_recent_operations` reads it.
- `cmd/api/main.go` ~398: `AUDIT_DB_URL` selects `PostgresLogger`; otherwise, or on init failure, the in-memory `Logger` is used.
- `internal/api/support_scope_test.go` already builds a support run (`supportRun`) and a stub router behind `agentScopeGate` with `audit.NewLogger()`. It is the natural home for the new tests.
- `isLoopbackRemote(r)` (`internal/api/router.go`) identifies in-process callers by `RemoteAddr`.

Deployed state checked:
- `mctl_list_services(team=admins)`: lists mctl-agents-worker*, mctl-design, mctl-docs, mctl-web and umami. mctl-api is not a catalogue tenant service, so its deployed config (env, replicas, whether `AUDIT_DB_URL` is set) could not be observed through this tool.
- `$MCTL_GITOPS_ROOT/services/admins/`: no `mctl-api` directory. A grep for `mctl-api` under services/ and tenants/ found only references from other services' values. The deployed mctl-api configuration was not observed. The gap is recorded under requirements.md Open questions. `helm/values.yaml` in the clone references `AUDIT_DB_URL` (CNPG CA comment, line ~113), which suggests the PostgreSQL logger is the production path.

## Proposed solution

### 1. Scope flag
Add `AuditRequests bool` to `auth.AgentScope` and set it on `AgentScopeSupport` only. The audit hooks key on this flag, not on the scope name, so a future scope can opt in. Add the helper `(*auth.User).AuditedAgentScope() (*AgentScope, bool)`.

### 2. Audit entry shape
Add a `Tenant string` field to `audit.Entry` (`json:"tenant,omitempty"`) and a column `tenant TEXT NOT NULL DEFAULT ''` (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`). Add two partial indexes, created `CONCURRENTLY` in the existing index loop:
- `audit_events_support_tenant ON audit_events (tenant, timestamp DESC) WHERE tenant <> ''`
- `audit_events_via_execution ON audit_events (via_execution_id, timestamp DESC) WHERE via_execution_id <> ''`

A support row:
- `Operation: "support.request"` (const `audit.OperationSupportRequest`); `RiskLevel: low`.
- `Status`: `succeeded` (HTTP < 400 / tool result not IsError), `failed` (otherwise), `denied` (scope refusal).
- `UserID: user.ID`, `PrincipalID: user.AgentRunRequestedBy()` (the tenant member the run acts for), `ViaPrincipalID: user.PrincipalID()` (the agent's own principal, platform convention: see requirements.md Open questions), `ViaExecutionID: user.ExecutionID()`, `Tenant: boundTenant`. These are set explicitly, so `logAuditCtx` does not overwrite them. It only fills fields that are empty.
- `Parameters`: `layer` (`rest`|`mcp`), `route` (`METHOD /path`, no query string) or `tool`, `http_status` (REST), `agent`, `scope`, `agent_run_id`, `work_item_id`, and for MCP `loopback` (up to 10 `METHOD /path STATUS` items joined by `; `, plus `loopback_truncated=true` when the list was cut). The row never holds request bodies, response bodies, tool results or argument values.

The existing REST refusal row (`agent_scope.denied`) is extended for audited scopes only: it gains `Tenant`, the same `PrincipalID` / `ViaPrincipalID` assignment as a `support.request` row, and `ViaExecutionID`, so the admin read finds refusals by tenant and execution. Its operation name and params are unchanged, so existing consumers and tests keep working.

### 3. REST hook (`agentScopeGate`)
In the `user.IsAgent()` branch, after `allowed` is decided and when `scope.AuditRequests`:
- Refused: write the extended `agent_scope.denied` row (as today plus the new fields), then return 403.
- Admitted: if the request is a loopback child of an open MCP tool call (see 5), call `next` without writing a row. Otherwise wrap `w` with `middleware.NewWrapResponseWriter`, call `next`, then write one `support.request` row with `ww.Status()` (0 is treated as 200). A `defer` writes the row even if a downstream panic is recovered by `middleware.Recoverer`, recorded as status 500 / `failed`.

### 4. MCP hook (`agentScopeMiddleware`)
Add an injected sink, mirroring `SetAgentReceiptGate`:
```go
type ScopedCallAuditor interface {
    AuditScopedToolCall(ctx context.Context, rec ScopedToolCallRecord)
}
func (s *Server) SetScopedCallAuditor(a ScopedCallAuditor)
```
`ScopedToolCallRecord` carries the entry id, tool, verdict (allowed/denied), result (`succeeded`/`failed`) and loopback list. `Handlers` implements it with `logAuditCtx` and is wired in `router.go` next to `SetAgentReceiptGate`.

In the middleware, for a scope with `AuditRequests`:
- If no auditor is set, refuse the call (`agent_scope_denied: audit unavailable`) and count it as `deny`. This fails closed, and it is also what makes the test fail when the hook is removed.
- Refused: call the auditor with a `denied` record (this replaces the bare `slog.Warn`, which is kept as well).
- Admitted: create an entry id (uuid). Register it in `s.auditParents` (a `sync.Map` from id to agent run id) and put a `*loopbackCollector` (mutex-guarded slice) on the context. Call `next`, then unregister and write one row. `err != nil` or `res.IsError` gives `failed`.

### 5. Folding loopback calls into one row
`tracingTransport.RoundTrip` reads the collector from the context. If one is present it sets `X-Mctl-Audit-Parent: <entry id>` on the loopback request and appends `METHOD path status` to the collector after the response. It does this in the same place the shadow-scope header is set today.

On the REST side, a request is treated as a folded child only if all three conditions hold:
1. `X-Mctl-Audit-Parent` is present.
2. `isLoopbackRemote(r)` is true.
3. `h.opts.MCPServer.OpenAuditParent(id)` returns the run id of the authenticated agent user.

If any condition fails, the header is ignored and a normal row is written. A forged or stale header therefore never suppresses a row: the id is a random uuid that is only valid inside this process while that run's tool call is open.

### 6. Write-failure visibility
Add `mctl_audit_write_failures_total{operation}` (Prometheus counter, registered in `internal/audit`). To keep label cardinality bounded, the label is either `support.request` or `other`. `PostgresLogger.Log` increments it and logs `slog.Error("audit postgres: insert failed", "operation", ..., "request_id", ..., "error", err)`. JSON marshal errors on params, ignored today, are treated the same way. The `Log` interface is unchanged.

### 7. Admin read
- New optional interface in `internal/audit`, implemented by `PostgresLogger` and `Logger`:
  ```go
  type SupportFilter struct { Tenant, ExecutionID string; Limit int; Before time.Time }
  type SupportReader interface { ListSupport(ctx context.Context, f SupportFilter) ([]Entry, error) }
  ```
  The query is `WHERE (operation = 'support.request' OR (operation = 'agent_scope.denied' AND tenant <> ''))`, `AND tenant = $1` and/or `AND via_execution_id = $2`, `ORDER BY timestamp DESC LIMIT n`. A query error is returned as an error, never as an empty page, following the `ListByStatus` convention.
- The handler `Handlers.ListSupportAudit` serves `GET /api/v1/audit/support?tenant=&execution_id=&limit=&before=`, registered next to `/audit` in `router.go`. It is admin-only (`user.IsAdmin()`, otherwise 403). It needs at least one filter (400), `limit` defaults to 100 with a maximum of 500, and it returns 503 when the configured log is not a `SupportReader`. Rows go through `audit.RedactEntry`. The response DTO explicitly exposes `tenant`, `userPrincipalId`, `viaPrincipalId` and `viaExecutionId`, because those fields are `json:"-"` on `Entry`. A support token cannot reach the route because it is not in the support route list.
- `PostgresLogger.List` and `Logger.List` exclude `operation = 'support.request'`, so the 50-row `/audit` feed keeps showing operations.

## Alternatives
1. **Audit only at the REST gate.** Every MCP read becomes a loopback REST call, so one hook looks sufficient. It was dropped for three reasons. It loses the tool name. It writes no row for tools that never call REST (`whoami`, `list_operations`, `read_platform_skill` may be served in-process). And a tool that fans out into several REST calls produces several rows, which breaks "exactly one row per read".
2. **Audit at both layers with no correlation.** This is the simplest code, but each tool call would produce 1+N rows, and the admin read would have to deduplicate heuristically. Dropped.
3. **A separate `support_audit_events` table.** This gives cleaner indexing and retention, but a second schema and store duplicate the principal, client-meta and redaction plumbing that `audit_events` and `logAuditCtx` already have. The issue also asks for rows in mctl-api's audit trail. Dropped in favour of one nullable-default column and partial indexes.
4. **An OTel span to audit pipeline.** Spans are sampled and not a durable record, and the issue explicitly says spans are insufficient. Dropped.

## Platform impact
- **Migration:** additive only (`ADD COLUMN IF NOT EXISTS tenant ... DEFAULT ''` and two `CREATE INDEX CONCURRENTLY IF NOT EXISTS`). Adding a column with a constant default is metadata-only in PostgreSQL 11+. Old pods ignore the column. An index build failure only logs a warning.
- **Backward compatibility:** no change for non-support tokens. `agent_scope.denied` keeps its operation and params and only gains columns. `/api/v1/audit` drops `support.request` rows, which never appeared there before. No MCP tool is added, so the tool count in `server_test.go` is unchanged.
- **Latency/resource:** one synchronous INSERT (5s timeout) per support request, on the request path after the handler. Support tokens are short-lived (10m) and low-volume, and the index cost is limited to rows with a tenant set. Risk: if the audit DB is slow, support reads get slower. Mitigation: the failure metric plus the existing timeout. Making writes asynchronous would weaken "exactly one row" guarantees and is not done.
- **Data sensitivity:** rows hold paths (which include tenant and app names) but no bodies, query strings or argument values. `RedactEntry` still applies on read. The admin read is admin-only.
- **Correlation trust:** child suppression needs loopback `RemoteAddr`, a live in-process parent id and a matching run id. A failure of any check writes an extra row, never a missing row.
- **Fail-closed MCP:** if the auditor is not wired, support tool calls are refused. This is correct in production (router always wires it), but it is a risk for any test or alternate entrypoint that builds `mcp.Server` without the router. Mitigation: a clear error code plus a unit test.
- **Observability:** add an alert on `rate(mctl_audit_write_failures_total[10m]) > 0`. The alert rule lives in gitops and is a follow-up outside this repo.
