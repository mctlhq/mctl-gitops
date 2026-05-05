# Tasks: mcp-go-v051-upgrade

- [ ] 1. Audit mcp-go v0.31 → v0.51.0 changelog for breaking API changes — DoD: a written list of every breaking change in `proposals/mcp-go-v051-upgrade/changelog-audit.md`; list is reviewed by the team lead; all affected call sites in `mctl-api` are identified.
- [ ] 2. Run `go get mark3labs/mcp-go@v0.51.0 && go mod tidy` (depends on 1) — DoD: `go build ./...` passes; all compilation errors from the upgrade are resolved in a dedicated commit per breaking change.
- [ ] 3. Fix tool registration breakages for read tools (depends on 2) — DoD: all 11 read tools (`get_service_status`, `get_tenant_metrics`, `list_incidents`, `get_workflow_logs`, etc.) compile and their existing unit tests pass.
- [ ] 4. Fix tool registration breakages for write tools (depends on 2) — DoD: all 13 write tools (`trigger_workflow`, identity tools, etc.) compile and their existing unit tests pass.
- [ ] 5. Add and verify output schemas for all 24 tools (depends on 3, 4) — DoD: every tool registration includes an explicit output schema struct/definition compatible with the v0.51 schema validation API; `mcp.WithToolOutputValidation(true)` is enabled; no tool returns a schema validation error on its happy-path test.
- [ ] 6. Configure RFC 9728 OAuth Protected Resource Metadata endpoint (depends on 2) — DoD: `GET https://api.mctl.ai/.well-known/oauth-protected-resource` returns a 200 with a valid RFC 9728 JSON document in a local integration test; values are sourced from `API_BASE_URL` and `DEX_ISSUER` env vars.
- [ ] 7. Configure SchemaCache (depends on 2) — DoD: `mcp.WithSchemaCache(...)` option is set in server initialisation; no functional test regressions; code comment explains why it is needed for multi-replica deployments.
- [ ] 8. Implement `MCP_LOG_TRANSPORT` feature flag for LoggingTransport (depends on 2) — DoD: config field `MCPLogTransport bool` added; when `true`, transport is wrapped in `mcp.NewLoggingTransport`; default is `false`; unit test verifies the flag is off by default.
- [ ] 9. Coordinate CSRF middleware interaction (depends on 4, and on `mcp-csrf-origin-validation` proposal status) — DoD: exactly one of (mcp-go built-in CORS or chi `OriginValidation` middleware) is active for the `/mcp` route; the chosen approach is documented in a comment in `router.go`; the other approach is either removed or explicitly disabled with a comment.
- [ ] 10. Write MCP Inspector CI target (depends on 5) — DoD: `make mcp-inspector-ci` starts the service, runs MCP Inspector headless, asserts 24 tools present and all return non-error on happy-path; target is added to the CI pipeline definition and must pass on the PR.
- [ ] 11. Update ArgoCD Helm values for `admins` tenant (depends on 9, 10) — DoD: `MCP_LOG_TRANSPORT` is absent (defaults to false) in the values file; `MCP_ALLOWED_ORIGINS` is set consistently with the chosen CSRF approach; PR reviewed by a platform engineer.
- [ ] 12. Staging smoke test (depends on 11) — DoD: MCP Inspector run against staging `https://api.mctl.ai/mcp` with all 24 tools passing; RFC 9728 endpoint verified; no spike in error-rate or latency metrics compared to pre-upgrade baseline.

## Tests

- [ ] T1. Unit — all 24 tool handler unit tests pass after compilation fixes (tasks 3, 4).
- [ ] T2. Unit — `TestSchemaValidation_RejectsInvalidResponse`: a tool handler that deliberately returns a wrong shape produces a JSON-RPC error, not a success response.
- [ ] T3. Unit — `TestRFC9728Endpoint`: GET `/.well-known/oauth-protected-resource` returns 200 with correct `resource` and `authorization_servers` fields.
- [ ] T4. Unit — `TestLoggingTransport_DisabledByDefault`: when `MCP_LOG_TRANSPORT` is unset, no `LoggingTransport` wrapper is applied.
- [ ] T5. Integration — `mcp-inspector-ci` Makefile target passes: 24 tools listed, all happy-path calls return non-error JSON-RPC responses.
- [ ] T6. Integration — CSRF behaviour: whichever mechanism is active (library CORS or chi middleware) rejects `Origin: https://evil.example.com` with HTTP 403.
- [ ] T7. Regression — existing REST endpoint tests (non-MCP routes) are unaffected by the upgrade.

## Rollback
1. Revert the `go.mod` / `go.sum` change to mcp-go v0.31 (`go get mark3labs/mcp-go@v0.31`).
2. Revert all tool registration code changes (git revert the upgrade commits).
3. If `mcp-csrf-origin-validation` chi middleware was disabled as part of this upgrade, re-enable it.
4. Merge the revert PR; ArgoCD will redeploy the previous image automatically.
5. The RFC 9728 endpoint will disappear — clients relying on it will fall back to manual OAuth config (no known hard dependency at time of writing).
6. No database migrations were applied; no persistent state rollback required.
