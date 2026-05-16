# Tasks: mcp-go-upgrade-v2

- [ ] 1. Bump mcp-go to v0.54.0 in go.mod — run `go get github.com/mark3labs/mcp-go@v0.54.0 && go mod tidy`;
  commit updated `go.mod` and `go.sum`. DoD: `go list -m github.com/mark3labs/mcp-go` returns
  `v0.54.0`; `go build ./...` exits 0.

- [ ] 2. Audit tool registration API for breaking changes (depends on 1) — diff the mcp-go
  changelog for any changes to `mcp.NewServer`, `mcp.NewTool`, handler function signatures, or
  transport options between v0.31 and v0.54.0. DoD: documented PR comment listing all API changes
  and confirming mctl-api handler code is compatible or identifying required adjustments.

- [ ] 3. Update tool registration code if required (depends on 2) — apply any handler signature
  or option-function changes identified in step 2. DoD: `go build ./...` exits 0; all 24 tool
  registrations compile without errors.

- [ ] 4. Wire OpenTelemetry tracing (depends on 3) — add `mcp.WithServerTracer(tracer)` to the
  server initialisation using the existing OTel tracer (or a no-op tracer if OTel is not
  configured). DoD: when OTel is configured, a span named after the tool appears in the trace
  backend for each MCP tool call; when OTel is absent, the server starts without errors.

- [ ] 5. Audit test harness request payloads for field-name case (depends on 3) — search all
  test fixtures and mock clients for non-lowercase JSON-RPC field names; fix any that would be
  rejected by the new strict dispatcher. DoD: `go test ./...` exits 0 with zero new failures.

- [ ] 6. Run full unit and integration tests (depends on 4, 5) — execute `go test ./...`
  including MCP integration tests. DoD: zero new failures; existing test coverage maintained.

- [ ] 7. Validate all 24 tools via MCP Inspector (depends on 6) — per ADR-0001, run MCP
  Inspector against the staging server; exercise each of the 24 tools with valid and invalid
  inputs; confirm correct schemas and responses. DoD: MCP Inspector reports all 24 tools with
  valid schemas; no unexpected errors; all read tools return expected data; all write tools
  reject requests without proper auth.

- [ ] 8. Load test in staging (depends on 7) — run a 10-minute MCP streaming load test at
  representative concurrency; compare latency and error rate against the v0.31 baseline.
  DoD: p99 latency ≤ baseline; zero panics in logs; OTel spans visible in trace UI.

- [ ] 9. Promote to production (depends on 8) — merge PR, ArgoCD deploys updated image.
  DoD: production pod imports mcp-go v0.54.0 (`go list` in build log); health check green;
  MCP endpoint responds to a smoke-test tool call within 2 seconds.

## Tests

- [ ] T1. **CVE-2026-27896 regression test** — add a test that sends an MCP request with
  `"Method"` (uppercase M) in the JSON-RPC body and asserts the server returns a -32600 error
  rather than silently bypassing validation.

- [ ] T2. **Panic safety test** — send a deliberately malformed MCP JSON payload (truncated,
  missing required fields) and assert the server returns a JSON-RPC error response; confirm no
  goroutine panic appears in logs.

- [ ] T3. **OTel span presence test** — with an in-process OTel exporter, invoke one MCP tool
  and assert a span with the correct tool-name attribute is recorded.

- [ ] T4. **MCP Inspector full sweep** — automated or manual run of all 24 tools; results
  recorded in the PR as a checklist (tool name + pass/fail).

## Rollback
1. Revert `go.mod`, `go.sum` changes: `git revert <commit-sha>`.
2. Rebuild and redeploy the image with mcp-go v0.31.
3. ArgoCD will detect the image change; if health checks fail, trigger `argocd app rollback
   mctl-api` to restore the previous known-good revision.
4. Re-run MCP Inspector against the rolled-back server to confirm all 24 tools are functional.
