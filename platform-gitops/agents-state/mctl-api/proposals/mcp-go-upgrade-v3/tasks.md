# Tasks: mcp-go-upgrade-v3

- [ ] 1. Mark `proposals/mcp-go-upgrade-v2` as superseded by this proposal in review notes — DoD:
      cross-reference added in both proposals; no duplicate parallel merge risk on `go.mod`.
- [ ] 2. Bump mcp-go to v1.1.0 in go.mod — run
      `go get github.com/mark3labs/mcp-go@v1.1.0 && go mod tidy`; commit updated `go.mod` and
      `go.sum`. DoD: `go list -m github.com/mark3labs/mcp-go` returns `v1.1.0`; `go build ./...`
      exits 0.
- [ ] 3. Audit tool registration and transport API for breaking changes across v0.31→v1.1.0
      (depends on 2) — diff the mcp-go changelog/release notes for `mcp.NewServer`, `mcp.NewTool`,
      handler function signatures, transport options, and the 0.x→1.x stabilization changes. DoD:
      documented PR comment listing all API changes and confirming mctl-api handler code is
      compatible or identifying required adjustments.
- [ ] 4. Update tool registration code if required (depends on 3) — apply any handler signature or
      option-function changes identified in step 3. DoD: `go build ./...` exits 0; all 24 tool
      registrations compile without errors.
- [ ] 5. Verify Host-header handling for CVE-2026-81092 (depends on 2) — confirm
      `server/http_localhost.go`'s Host validation is active for `StreamableHTTPServer` /
      `SSEServer`; add an explicit Host allow-list (`api.mctl.ai`) at the ingress/router layer as
      defense-in-depth. DoD: a request with a spoofed/rebound Host header targeting a
      loopback-bound listener is rejected; a request with the correct Host header succeeds.
- [ ] 6. Audit test harness request payloads for JSON field-name case (depends on 4) — search all
      test fixtures and mock clients for non-lowercase JSON-RPC field names; fix any that would be
      rejected by the strict dispatcher (CVE-2026-27896 fix). DoD: `go test ./...` exits 0 with
      zero new failures.
- [ ] 7. Run full unit and integration tests (depends on 5, 6) — execute `go test ./...` including
      MCP integration tests. DoD: zero new failures; existing test coverage maintained.
- [ ] 8. Validate all 24 tools via MCP Inspector (depends on 7) — per ADR-0001, run MCP Inspector
      against the staging server; exercise each of the 24 tools with valid and invalid inputs.
      DoD: MCP Inspector reports all 24 tools with valid schemas; no unexpected errors; all read
      tools return expected data; all write tools reject requests without proper auth.
- [ ] 9. Load test in staging (depends on 8) — run a 10-minute MCP streaming load test at
      representative concurrency; compare latency and error rate against the v0.31 baseline. DoD:
      p99 latency ≤ baseline; zero panics in logs.
- [ ] 10. Promote to production (depends on 9) — merge PR, ArgoCD deploys updated image. DoD:
      production pod imports mcp-go v1.1.0 (`go list` in build log); health check green; MCP
      endpoint responds to a smoke-test tool call within 2 seconds; `current-version.md` updated.

## Tests
- [ ] T1. **CVE-2026-81092 regression test** — send an MCP request to `StreamableHTTPServer`/
      `SSEServer` with a spoofed/DNS-rebound Host header from a loopback-bound test listener and
      assert the request is rejected.
- [ ] T2. **CVE-2026-27896 regression test** — send an MCP request with `"Method"` (uppercase M) in
      the JSON-RPC body and assert the server returns a -32600 error rather than silently bypassing
      validation.
- [ ] T3. **Panic safety test** — send a deliberately malformed MCP JSON payload (truncated,
      missing required fields) and assert the server returns a JSON-RPC error response; confirm no
      goroutine panic appears in logs.
- [ ] T4. **MCP Inspector full sweep** — automated or manual run of all 24 tools; results recorded
      in the PR as a checklist (tool name + pass/fail).

## Rollback
1. Revert `go.mod`, `go.sum` changes (and any ingress Host allow-list change): `git revert
   <commit-sha>`.
2. Rebuild and redeploy the image with mcp-go v0.31.
3. ArgoCD will detect the image change; if health checks fail, trigger `argocd app rollback
   mctl-api` to restore the previous known-good revision.
4. Re-run MCP Inspector against the rolled-back server to confirm all 24 tools are functional.
5. Note: rolling back re-exposes CVE-2026-81092 and CVE-2026-27896 — treat as a temporary state
   only, and re-open this proposal (or a follow-up) immediately if rollback is required.
