# Tasks: mcp-go-upgrade-v0.50

- [ ] 1. Bump `mark3labs/mcp-go` to v0.50.0 in `go.mod` and run `go mod tidy` — DoD: `go.mod` shows `github.com/mark3labs/mcp-go v0.50.0`; `go.sum` is regenerated; `go build ./...` succeeds with no compilation errors.
- [ ] 2. Resolve transitive dependency conflicts introduced by `santhosh-tekuri/jsonschema/v6` (depends on 1) — DoD: `go mod tidy` produces no error; no other direct dependency is removed or downgraded; `go build ./...` succeeds.
- [ ] 3. Audit all 24 tool schema definitions for completeness and correctness (depends on 1) — DoD: a checklist in the PR lists all 24 tools; any schema with missing `required` fields, incorrect types, or incomplete `enum` values is corrected; corrections are documented in the PR description.
- [ ] 4. Enable `WithInputSchemaValidation()` in the MCP server initialisation (depends on 3) — DoD: the server option is added to the server constructor call; `go build ./...` succeeds; mctl-api starts and the health endpoint responds healthy in a local run.
- [ ] 5. Investigate CVE-2026-27896 applicability to mcp-go v0.50.0 (depends on 1) — DoD: the PR description contains a written finding: either (a) the vulnerability is reproducible and a mitigation is implemented, or (b) the vulnerability is not reproducible and the reason is documented. This task is a merge blocker.
- [ ] 6. Run the full unit and integration test suite (depends on 4) — DoD: all existing tests pass with zero new failures; any test that relied on previously unvalidated invalid inputs is updated to expect the new JSON-RPC error response.
- [ ] 7. Run Trivy against the updated module graph (depends on 2) — DoD: no open CVEs for `mark3labs/mcp-go` or `santhosh-tekuri/jsonschema/v6` in the scanner output.
- [ ] 8. Validate all 24 tools through MCP Inspector against a staging deployment (depends on 6) — DoD: a results table in the PR lists all 24 tools with pass/fail status; all 24 pass; no tool returns an unexpected error for a well-formed valid call.
- [ ] 9. Open PR to mctl-gitops with all changes (depends on 5, 7, 8) — DoD: PR references CVE-2026-27896 investigation, ADR-0001, and the MCP Inspector results table; at least one reviewer approves; CI is green.
- [ ] 10. Merge and verify ArgoCD sync for the `admins` tenant (depends on 9) — DoD: ArgoCD shows `mctl-api` synced and healthy; MCP endpoint responds to a `list_tools` call with all 24 tools; no rollback triggered within 30 minutes of deployment.

## Tests

- [ ] T1. Unit tests for MCP server initialisation pass with `WithInputSchemaValidation()` enabled — confirms the option is accepted without panic or error.
- [ ] T2. For each of the 13 write tools: submit a tool call with a missing required argument — the server must return a JSON-RPC error (code -32602 Invalid Params) and the handler must not be invoked.
- [ ] T3. For each of the 13 write tools: submit a valid tool call — the handler must be invoked and return the expected result.
- [ ] T4. For each of the 11 read tools: submit a valid tool call — the handler must return the expected result with no regression.
- [ ] T5. Submit a JSON-RPC request with a smuggled field name (e.g., `"paramſ"`) — the server must either reject it or parse it correctly without confusion; outcome must match the CVE-2026-27896 investigation finding.
- [ ] T6. Trivy scan of the final Docker image reports zero open CVEs for `mark3labs/mcp-go` and its new transitive dependency `santhosh-tekuri/jsonschema/v6`.
- [ ] T7. MCP Inspector: all 24 tools return expected responses for canonical valid inputs (recorded as a pass/fail table in the PR).

## Rollback
Revert `go.mod` to `github.com/mark3labs/mcp-go v0.31`, remove `WithInputSchemaValidation()` from the server constructor, re-run `go mod tidy`, and open a revert PR to mctl-gitops. ArgoCD will re-deploy the previous image on sync. No schema, data, or protocol migration was performed, so no data rollback is required. Any tool schema corrections made during the audit are safe to retain (they are additive constraints), but may be reverted if they caused test failures. Expected rollback time: under 30 minutes.
