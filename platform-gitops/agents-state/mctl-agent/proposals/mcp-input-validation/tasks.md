# Tasks: mcp-input-validation

- [ ] 1. Create `internal/mcp/validation` package with `Schema`, `ValidationError`, and `SchemaRegistry` types — implement the core data structures: `Schema` (per-tool field definitions with regexp, length limits, and enum allowlists), `ValidationError` (structured error with tool name, field, and reason), and `SchemaRegistry` (`map[string]Schema` populated at init). — DoD: package compiles; `go vet ./internal/mcp/validation/...` is clean; package has no external dependencies beyond stdlib.

- [ ] 2. Implement `Validate(toolName string, arguments map[string]any) error` (depends on 1) — the central validation function: (a) looks up the tool schema in `SchemaRegistry`; (b) returns an error for unknown tool names (reject-by-default); (c) iterates over schema field definitions and applies type check, regexp match, length limit, and enum check as applicable; (d) collects all field errors and returns a combined `ValidationError`. — DoD: function returns nil for valid inputs; returns a non-nil `ValidationError` with the correct field name and reason for each invalid case; `go test ./internal/mcp/validation/...` passes with 100% statement coverage on the validation logic.

- [ ] 3. Define per-tool schemas for all 6 MCP tools (depends on 1) — populate `SchemaRegistry` with schemas for: `create_pr`, `list_tickets`, `get_ticket`, `silence_alert`, `query_alerts`, `update_ticket_state`. Each schema entry must cover every accepted field with its type constraint, regexp (where applicable), length limit, and enum allowlist (where applicable). — DoD: `SchemaRegistry` contains exactly 6 entries; each entry matches the field definitions in design.md; schemas are expressed as Go constants or `init`-time values so they are visible to the test suite.

- [ ] 4. Add startup schema registry validation (depends on 3) — at process startup (e.g., in `main.go` or the MCP handler constructor), verify that `SchemaRegistry` contains an entry for every tool name declared in the MCP tool-listing response (`tools/list`). If any tool is missing a schema, the process must log a FATAL error and exit. — DoD: the service fails to start if a tool is declared without a schema; the test suite includes a test that verifies the registry covers the full tool list.

- [ ] 5. Integrate `validation.Validate` into the `POST /mcp` handler (depends on 2, 3) — update `internal/mcp/handler.go` (or equivalent) to call `validation.Validate(toolName, arguments)` immediately after JSON-RPC request unmarshalling and before any tool dispatch. On a non-nil error, write a JSON-RPC response with code `-32602` and the error message; do not call the tool implementation. — DoD: the handler returns `-32602` for all invalid inputs; no downstream API call is made for a rejected request; `go test ./internal/mcp/...` passes.

- [ ] 6. Add structured rejection logging (depends on 5) — on each validation rejection, emit `slog.Warn("mcp.validation.rejected", "tool", toolName, "field", fieldName, "reason", reason, "sanitized_value", sanitizedValue)`. Sanitization rule: if the rejected value is longer than 64 characters or matches a secret-like pattern (contains `token`, `key`, `secret`, `password` case-insensitively), replace with `[REDACTED]`; otherwise use the first 64 chars of the raw value. — DoD: a table-driven test verifies that the log entry is emitted for each rejection scenario and that `[REDACTED]` is used correctly.

- [ ] 7. Update MCP handler tests and integration tests (depends on 5, 6) — review and update the existing `POST /mcp` handler tests to assert that (a) valid tool calls still succeed end-to-end, and (b) injection-pattern inputs for each of the 6 tools are rejected with `-32602`. — DoD: `go test ./...` is green; no existing test is deleted; test count is the same or higher.

- [ ] 8. Open PR and pass CI (depends on 7) — submit all changes in one PR titled "security: add per-tool input validation for POST /mcp (6 tools)". — DoD: CI is green; PR description references the 2026-04-15 MCP advisories and lists all 6 tools covered; at least one reviewer approves.

- [ ] 9. Post-deploy verification (depends on 8, after ArgoCD sync) — send a set of synthetic valid and invalid MCP tool calls against the deployed endpoint and verify correct responses and log output. — DoD: valid calls return the expected tool result; invalid calls return `-32602`; WARN log entries appear for each rejection in the pod logs.

## Tests

All tests in this proposal are table-driven per the Go project rule (see architecture.md "All Go skills — table-driven tests").

- [ ] T1. `TestValidate_AllTools` in `internal/mcp/validation/validate_test.go` — table-driven test with rows for each of the 6 tools; each tool has at minimum: one fully-valid input row (expect nil error), one row per field with an over-length value (expect error), one row with a shell-metacharacter injection attempt in string fields (expect error), and one row with a disallowed enum value (expect error where applicable). — DoD: >= 6 tools x >= 4 rows = >= 24 table rows; all pass; 100% statement coverage on `Validate`.

- [ ] T2. `TestValidate_UnknownTool` — single table-driven test asserting that `Validate("unknown_tool", map[string]any{})` returns a non-nil error. — DoD: test passes; confirms the reject-by-default policy.

- [ ] T3. `TestSchemaRegistry_CoversAllTools` — loads the live `SchemaRegistry` and the live `tools/list` tool names; asserts every declared tool has a schema entry. — DoD: test fails if a tool is added to the MCP tool list without a corresponding schema, providing a compile-time-equivalent guardrail.

- [ ] T4. `TestMCPHandler_RejectsInjectionPayloads` in `internal/mcp/handler_test.go` — table-driven HTTP handler test (using `httptest.NewRecorder`) with injection-payload rows for each of the 6 tools: SQL injection string, shell command substitution (`$(id)`), overlong string, null bytes. Asserts HTTP 200 with JSON-RPC body containing `"code": -32602`. — DoD: all injection rows return `-32602`; no row causes a downstream API call (verified by asserting mock downstream call count is 0).

- [ ] T5. `TestValidationLog_SanitizesSecrets` — table-driven test covering the sanitization logic in the rejection logger: row with a value containing "token" (expect `[REDACTED]`), row with a value > 64 chars (expect `[REDACTED]`), row with a short benign value (expect raw value truncated to 64 chars). — DoD: all rows assert the correct sanitized_value in the captured log output.

- [ ] T6. Regression test — run `go test ./...` on the full mctl-agent test suite and assert that the existing test count has not decreased. — DoD: test output shows same or higher test count; zero tests skipped or deleted.

## Rollback
1. Revert the PR (GitHub "Revert" button) — this removes the `internal/mcp/validation` package and the handler integration in a single commit.
2. Trigger an ArgoCD sync to redeploy the previous image tag.
3. Confirm the pod is running the pre-validation image by checking the image tag in `kubectl describe pod`.
4. The rollback restores the previous (unvalidated) behaviour; treat the MCP endpoint as elevated-risk until the fix is re-applied.
5. No database migrations are involved; rollback is purely a binary swap.
6. File a follow-up issue describing the regression before re-attempting the implementation. Do not leave the MCP endpoint without validation longer than necessary given the public 2026-04-15 advisories.
