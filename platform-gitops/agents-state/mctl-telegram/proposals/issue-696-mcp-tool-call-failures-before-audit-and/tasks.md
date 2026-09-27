# Tasks: issue-696-mcp-tool-call-failures-before-audit-and

- [ ] 1. Add the `reason` column to `audit_logs`, outside the hash chain.
  Add `addColumnIfMissing(ctx, dbConn, pg, "audit_logs", "reason", "TEXT", "TEXT")`
  to `Migrate` in `internal/db/db.go`, next to the existing `call_path` and
  correlation-column adds; do **not** add it to `sqliteSchema()` / `pgSchema()`.
  Do **not** touch `internal/db/audit_chain.go`: `reason` is not hashed.
  — DoD: `db.Migrate` is idempotent on a fresh and on a pre-existing SQLite and
  Postgres database; `git diff` shows no change to `audit_chain.go`.

- [ ] 2. Thread `reason` through the store (depends on 1). Add a trailing
  `reason string` parameter to `Store.LogToolCall` (`internal/db/store.go:1745`),
  write it with `nullable(reason)` in the `INSERT` column list only — do not
  pass it to `hashAuditEntry`. Leave `db.AuditEntry`, `ListAuditFor` and
  `VerifyAuditChain` unchanged.
  — DoD: `go build ./...` passes; every existing `LogToolCall` caller compiles
  (pass `""` from non-MCP callers in `internal/oauth` and `internal/agentapi`);
  a row written with a reason stores it in `audit_logs.reason` (asserted by a
  direct SQL read in the test), and old rows read back NULL.

- [ ] 3. Add the `mctl_tool_call_errors_total{tool,reason}` counter. Declare
  `ToolCallErrorsTotal *prometheus.CounterVec` on `metrics.Registry`, construct
  it in `New()` beside `ToolInvocationsTotal`
  (`internal/metrics/metrics.go:406`), register it in the `MustRegister` block,
  and add the name to `expectedMetricNames` in
  `internal/metrics/metrics_test.go`. Do not pre-create label combinations.
  — DoD: `TestNew_RegistersAllMetrics` passes; a test pins the metric type and
  the exact label names `{tool, reason}`, following the
  `TestNew_RegistersIssue580Metrics` pattern.

- [ ] 4. Define the reason taxonomy in a new `internal/mcp/reasons.go`.
  Export the closed constant set from design.md section A, plus
  `classifyToolResultReason(res *mcplib.CallToolResult) string` which prefix-matches
  the literal error strings the handlers produce and returns `ReasonUnknown`
  otherwise. No client-supplied string may ever become a reason.
  — DoD: a table test enumerates every literal the classifier matches, taken
  verbatim from the handler that produces it, and asserts `ReasonUnknown` for an
  unrecognised message.

- [ ] 5. Add the staged recorder in a new `internal/mcp/record.go` (depends on 2, 4).
  Implement `callRecord`, `callRecorder`, `withRecorder(ctx)` / `recorderFrom(ctx)`,
  and the flush that writes staged records in order through the existing
  write-through path on a `context.WithoutCancel` + `auditWriteTimeout` context.
  — DoD: unit-tested in isolation — staging preserves order, flush reconciles the
  last record's status to `error` when told to, flush is a no-op when nothing was
  staged and the outcome was a success on an exempt tool.

- [ ] 6. Make `Server.audit` stage when a recorder is present (depends on 5).
  Add the branch at the top of `Server.audit` (`internal/mcp/tools.go:2318`);
  keep the existing body as the write-through path, now taking a `reason`
  argument to forward to `LogToolCall`. `auditDetached` is unchanged.
  — DoD: every existing `internal/mcp` and `internal/db` test still passes
  unmodified — direct handler calls with no recorder behave exactly as before,
  including row content, `ToolInvocationsTotal` / `ToolInvocationDuration`
  samples, and the INFO/WARN slog split.

- [ ] 7. Implement `Server.recordToolCall` middleware (depends on 5, 6).
  `func (s *Server) recordToolCall(next mcpserver.ToolHandlerFunc) mcpserver.ToolHandlerFunc`:
  install the recorder, capture `startedAt`, `defer` the recover-and-flush,
  absorb a non-nil handler error and a recovered panic into an `IsError` result,
  apply the four flush rules from design.md section B, and increment
  `ToolCallErrorsTotal{req.Params.Name, reason}` exactly once per erroring call.
  Define `auditExemptOnSuccess` with `get_my_audit_log`, `get_my_identity`
  and `get_my_send_status`, with a comment citing the existing rationale in
  `toolGetMyAuditLog` for the first and "success volume unchanged; decided at
  review 2026-09-27" for the other two.
  — DoD: the wrapper never reads `req.GetArguments()`; a synthesised record
  carries an empty peer; `go vet` and `golangci-lint` clean.

- [ ] 8. Implement the JSON-RPC error hook (depends on 3, 4).
  `func (s *Server) jsonrpcHooks() *mcpserver.Hooks` with one `AddOnError` that
  returns early unless `method == mcplib.MethodToolsCall`, extracts the code via
  the local `interface{ ToJSONRPCError() mcplib.JSONRPCError }` assertion,
  derives the reason from `mcpserver.ErrToolNotFound` / `mcpserver.ErrUnsupported`
  / `*mcpserver.UnparsableMessageError`, emits `slog.Warn("mcp jsonrpc error", …)`
  with `mcp_method`, `tool`, `jsonrpc_code`, `reason`, `user_id`,
  `edge_request_id`, `edge_route`, and increments the counter.
  — DoD: no arguments are logged; an unauthenticated request logs `user_id=0`
  rather than omitting the field; the code is the real JSON-RPC code, not a
  hardcoded constant.

- [ ] 9. Register both in `newMCPServer` (depends on 7, 8).
  Add `mcpserver.WithToolHandlerMiddleware(s.recordToolCall)` and
  `mcpserver.WithHooks(s.jsonrpcHooks())` to the `opts` slice in
  `internal/mcp/server.go:252`.
  — DoD: `TestPortalAllowlist*` and the `newMCPServer()`-based schema tests still
  pass; the registered tool list is unchanged.

- [ ] 10. ~~Surface `reason` in `get_my_audit_log`.~~ Dropped at review
  (2026-09-27): `reason` stays operator-only. — DoD: `get_my_audit_log`'s
  description and `outputSchema` are unchanged;
  `internal/mcp/output_schema_test.go` and `output_schema_open_test.go` pass
  without fixture changes.

- [ ] 11. Documentation and dashboard (depends on 3).
  Add `mctl_tool_call_errors_total` to `docs/runbook.md` under the
  tool-availability material — a short "Tool-call error breakdown" subsection
  with an example `sum by (tool, reason) (rate(mctl_tool_call_errors_total[5m]))`
  query, the `mcp tool call` / `mcp jsonrpc error` Loki lines, and an explicit
  note that the counter is not pre-created at zero so `increase()` misses the
  first sample of a new `(tool, reason)` pair. Add an error-breakdown panel to
  `deploy/grafana/mctl-telegram-beta.json`. Mention the new `reason` field in
  the audit-log section of `docs/` wherever the `audit_logs` columns are
  enumerated.
  — DoD: `docs/runbook_test.go`, `docs/troubleshooting_test.go` and
  `deploy/alerts/runbook_links_test.go` pass; any new `<a id="…"></a>` anchor
  resolves.

## Tests

- [ ] T1. Chain independence (`internal/db/audit_chain_test.go`): write rows
  with and without a reason, mixed with rows that have `call_path` and edge
  columns set, and assert `VerifyAuditChain` reports `OK`; assert that the
  `entry_hash` of a row written with reason `X` equals the hash of the same
  row written with an empty reason — proving `reason` is outside the chain.

- [ ] T2. Write-through unchanged (`internal/mcp/tools_test.go`): keep an
  existing direct-handler audit test (for example
  `TestToolProvisionLocalAccount_AuditsSuccessAndRefusal`) passing unmodified,
  and add one asserting that with no recorder in ctx the row is written before
  the handler returns.

- [ ] T3. Scope-denied regression (new `internal/mcp/record_test.go`): drive
  `search_messages` end-to-end through the `callRPC` / `srv.HandleMessage`
  harness (`internal/mcp/apps_surface_test.go:27`) with an identity lacking
  `telegram:messages:read`. Assert exactly one `audit_logs` row with
  `status="error"`, `reason="scope_denied"`, exactly one WARN `mcp tool call`
  slog record, and `mctl_tool_call_errors_total{search_messages,scope_denied} == 1`.
  Must fail if the middleware registration in `newMCPServer` is reverted.

- [ ] T4. Empty-query regression: same harness, `search_messages` with
  `query=""` and a valid scope. Assert one error row with
  `reason="invalid_argument"`.

- [ ] T5. Local-bridge-mode regression: same harness, `search_messages` for an
  account whose `GetAccountMode` returns `"local"` with a non-nil `Hub`. Assert
  one error row with `reason="mode_unsupported"`.

- [ ] T6. Unknown-tool regression: `callRPC` a `tools/call` for
  `"no_such_tool"`. Assert zero new `audit_logs` rows (no handler ran, so there
  is no user-scoped call to record), exactly one WARN `mcp jsonrpc error` record
  carrying `mcp_method="tools/call"`, `tool="no_such_tool"`, the JSON-RPC code
  and `reason="tool_not_found"`, and one counter increment.

- [ ] T7. Invalid-params regression: `callRPC` a `tools/call` whose `params`
  cannot unmarshal into `mcp.CallToolRequest`. Assert one WARN
  `mcp jsonrpc error` with `reason="unparsable_message"` and the
  `INVALID_REQUEST` code.

- [ ] T8. Encode-failure reconciliation: inject a value that
  `json.MarshalIndent` rejects into a tool's result path (a purpose-built test
  tool registered on a bare `mcpserver.MCPServer` with the same middleware, or a
  seam in `jsonResult`), after the handler has already audited `ok`. Assert the
  call produces exactly one row and that its status is `error` with
  `reason="encode_failed"` — never an `ok` row.

- [ ] T9. Success path unchanged: drive a successful `list_dialogs` through the
  harness. Assert exactly one `audit_logs` row with `status="ok"` and an empty
  reason, exactly one INFO `mcp tool call` record, no WARN, no
  `mctl_tool_call_errors_total` sample, and one
  `mctl_tool_invocations_total{list_dialogs,ok}` increment.

- [ ] T10. Audit-exempt tools: a successful `get_my_audit_log`,
  `get_my_identity` or `get_my_send_status` adds no row; a failing
  `get_my_audit_log` (bad `before` timestamp) adds exactly one row with
  `reason="invalid_argument"`, and the tool's JSON output for that row has no
  `reason` field.

- [ ] T11. Handler error and panic absorption: register a test tool that returns
  `(nil, errors.New("boom"))` and one that panics. Assert each yields an
  `IsError` tool result (not a JSON-RPC error), one row with
  `reason="handler_error"` / `"panic"`, and that the `onError` hook did **not**
  also fire — the no-double-recording invariant.

- [ ] T12. Redaction: assert that no test's captured slog buffer or audit row
  contains a raw argument value, an unredacted `@handle`, or message text — the
  `internal/mcp/audit_edge_test.go:68` `strings.Contains` absence-assertion
  pattern.

- [ ] T13. Reason classifier table test (from task 4), asserting every matched
  literal is copied verbatim from the handler that emits it.

- [ ] T14. Full suite: `go build ./... && go vet ./... && golangci-lint run &&
  go test ./...`, plus `go test ./internal/db/...` against Postgres if the
  Postgres-backed suite is part of CI.

## Rollback

The change is additive and splits cleanly into an observability layer and a
schema addition, which roll back independently.

1. **Fastest revert (observability only).** Remove the two options from the
   `opts` slice in `newMCPServer` (`internal/mcp/server.go:252`) and redeploy.
   With no recorder in ctx, `Server.audit` takes its write-through branch and
   behaviour returns to exactly today's, with the `reason` argument passed as
   `""`. No data change, no migration touched, no chain impact. This is the
   one-line escape hatch if the wrapper misbehaves in production.
2. **Full binary rollback.** Roll the image back with
   `mctl_rollback_service` to the prior tag. The `audit_logs.reason` column
   stays in place and is simply not written. Because `reason` is not hashed,
   every row written by the new binary verifies under the old binary's
   `VerifyAuditChain` — the rollback is safe at any point.
3. **Leave the column in place.** `reason` is nullable and harmless when
   unused; dropping it is unnecessary and would only lose operator data.
4. **Metric removal.** `mctl_tool_call_errors_total` simply stops being
   reported; any dashboard panel referencing it renders empty. Remove the panel
   from `deploy/grafana/mctl-telegram-beta.json` only if the rollback is
   permanent.
