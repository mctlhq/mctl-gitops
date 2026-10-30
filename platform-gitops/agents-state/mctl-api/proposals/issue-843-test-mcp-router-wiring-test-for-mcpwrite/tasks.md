# Tasks: issue-843-test-mcp-router-wiring-test-for-mcpwrite

- [ ] 1. Add the unexported `mcpHandler http.Handler` field to `Options` in
  `internal/api/router.go`. Restructure the `/mcp` registration block at the
  end of the authenticated group:
  - Setters and `NewStreamableHTTPHandler()` run only when `MCPServer != nil`.
  - `mcpHandler`, when set, overrides the handler.
  - The POST/GET/DELETE routes, including
    `extendWriteDeadline(opts.MCPWriteTimeout, ...)` on POST, are registered
    once when a handler exists.

  DoD: `go build ./...` passes; existing tests that set `MCPServer` pass
  unchanged; main.go is untouched.
- [ ] 2. (depends on 1) Add `TestNewRouterRequestDeadlines` to
  `internal/api/mcp_write_deadline_test.go`:
  - Router: built with `tokenUsers` auth for an admin user,
    `MCPWriteTimeout: 75*time.Second`, a stub `mcpHandler`, a fake `GitReader`
    whose `GetTenant("labs")` succeeds, and a stub `QuotaReader`. Both stubs
    record the remaining time until the context deadline.
  - Assertions:
    - Authenticated `POST /mcp` is within 1s of 75s.
    - `GET /api/v1/resources/labs` is within 1s of 30s.
    - Optionally `GET /mcp` is within 1s of 30s.

  DoD: the test passes, and it fails when line 494 is temporarily changed to
  `r.Use(middleware.Timeout(30*time.Second))`. That check is done by hand,
  reverted, and noted in the PR description.
- [ ] 3. Simplify the post-loop tail of `supportAwait` in
  `internal/mcp/support.go`:
  - Drop the inner `if lastErr != nil` and the unreachable
    `"no poll completed within the wait"` fallback.
  - Use `lastErr.Error()` directly in the error message.
  - Move the "No poll attempted" comment above the final `supportResultJSON`
    return.

  DoD: tool output strings are byte-for-byte unchanged, and the existing
  `internal/mcp` support tests pass.
- [ ] 4. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run`, and
  `go test ./...`. DoD: all clean, and the MCP tool count in `server_test.go`
  is unchanged.

## Tests

- [ ] T1. `TestNewRouterRequestDeadlines`: POST /mcp deadline is about
  `MCPWriteTimeout` (75s) through the full `NewRouter` middleware chain.
- [ ] T2. Same test: the non-MCP authenticated route
  `GET /api/v1/resources/{tenant}` has a deadline of about 30s.
- [ ] T3. Manual mutation check: with `middleware.Timeout(30*time.Second)`
  restored in `NewRouter`, T1 fails. Revert afterwards.
- [ ] T4. Existing `TestRequestTimeout`, `TestExtendWriteDeadline`, and the
  `supportAwait` / `mctl_ask_support` tests in `internal/mcp` still pass.

## Rollback

Revert the PR. All changes are test-only or behaviour-preserving: a test seam
that only in-package tests can set, and dead-code removal. Nothing is deployed
or migrated, so a plain `git revert` restores the previous state.
