# Tasks: mcp-rce-server-hardening

- [ ] 1. Add `config/mcp-tool-permissions.yaml` listing all 13 write tools with required groups — DoD: file exists in repo, CI schema-validation step passes, every registered write tool has an entry, missing entry causes `go test ./...` failure via init-time check
- [ ] 2. Implement `internal/validate` package with `StringMaxLen(field string, value string, max int) error` helper — DoD: unit tests cover boundary (at limit, one over, empty), package exported, no external dependencies
- [ ] 3. Add `MCPAuthzMiddleware` in `internal/mcpauth` that reads permissions from config and checks resolved `TenantGroups` on context (depends on 1) — DoD: unit tests cover allow, deny-wrong-group, deny-missing-tool-entry; middleware registered in server setup; `mcp_write_denied_total` counter incremented on denial
- [ ] 4. Wrap the MCP endpoint handler with `http.MaxBytesReader` at 64 KB and wire `validate.StringMaxLen` into each write-tool handler (depends on 2, 3) — DoD: integration test sends 65 KB payload and receives HTTP 413; oversized string field receives HTTP 422
- [ ] 5. Register a second `httprate` store keyed on `(identity, write)` with 30 req/min default, bypassed for read tools; expose `MCP_WRITE_RATE_LIMIT` env var (depends on 3) — DoD: unit test simulates 31 calls in 60 s from the same identity and asserts the 31st returns HTTP 429 with `Retry-After` header; read tools are unaffected in the same test
- [ ] 6. Write Postgres migration `migrations/NNNN_mcp_write_audit.up.sql` creating `mcp_write_audit` table and indexes (no dependencies) — DoD: migration runs cleanly on a local Postgres instance; rollback migration `*.down.sql` drops the table without error
- [ ] 7. Implement async audit-log writer: buffered channel (512), background goroutine, SHA-256 arg hashing, `mcp_audit_write_error_total` counter on drop (depends on 6) — DoD: unit test verifies a write-tool invocation produces a row in `mcp_write_audit`; test verifies full channel drops event and increments counter rather than blocking
- [ ] 8. Wire audit middleware into the MCP handler chain after authorization (depends on 3, 7) — DoD: denied and allowed write-tool calls both produce audit rows in integration tests; audit row fields match schema (identity, tool_name, args_sha256, http_status, latency_ms)
- [ ] 9. Update `README` / operator runbook with: permission YAML location, rate-limit env var, audit table schema, alert thresholds for `mcp_write_denied_total` and `mcp_audit_write_error_total` (depends on all above) — DoD: PR reviewer confirms runbook is accurate and self-contained

## Tests

- [ ] T1. Unit: `MCPAuthzMiddleware` — allow path, deny path, missing permission config entry causes startup failure
- [ ] T2. Unit: `validate.StringMaxLen` — at limit, one over, empty string, non-ASCII multibyte characters (byte count vs rune count)
- [ ] T3. Unit: write-rate-limiter — 30 allowed, 31st returns 429, read tool on same identity not limited, `MCP_WRITE_RATE_LIMIT=1` env override works
- [ ] T4. Unit: audit-log writer — successful write produces correct row, channel-full path increments counter, SHA-256 of args is deterministic
- [ ] T5. Integration: end-to-end MCP write-tool call with a valid write-group token — HTTP 200, audit row present
- [ ] T6. Integration: end-to-end MCP write-tool call with a read-only token — HTTP 403, audit row present with `denied_reason`
- [ ] T7. Integration: oversized payload (65 KB) to MCP endpoint — HTTP 413, no audit row (rejected before handler)
- [ ] T8. Integration: Postgres migration up/down on clean schema — no errors, idempotent on re-run

## Rollback
1. Revert the `MCPAuthzMiddleware` registration from the handler chain (single-line change in server setup). This restores the previous behaviour where all authenticated callers can invoke all tools.
2. Run the down migration (`migrations/NNNN_mcp_write_audit.down.sql`) to drop the audit table if schema cleanup is needed.
3. Remove the `MaxBytesReader` wrapper if the 64 KB limit is causing unexpected rejections.
4. All three rollback steps are independent and can be applied individually. No ArgoCD sync or Kubernetes node drain required — a standard rolling restart of the mctl-api deployment is sufficient.
