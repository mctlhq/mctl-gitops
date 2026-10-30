# Design: issue-843-test-mcp-router-wiring-test-for-mcpwrite

## Current state

- `internal/api/router.go`, `NewRouter`, authenticated group (around line 482):
  the middleware order is `opts.AuthMiddleware`, then `surfaceAggregateLimit`,
  then `requestTimeout(30*time.Second, opts.MCPWriteTimeout)` (line 494), then
  `h.surfacePrincipalGate` and the other gates. At the end of the group
  (around line 1046):
  ```go
  if opts.MCPServer != nil {
      opts.MCPServer.SetTenantOwnerChecker(h)
      opts.MCPServer.SetAgentReceiptGate(h, opts.AgentReceiptGateMode)
      opts.MCPServer.SetScopedCallAuditor(h)
      mcpH := opts.MCPServer.NewStreamableHTTPHandler()
      r.Post("/mcp", extendWriteDeadline(opts.MCPWriteTimeout, mcpH).ServeHTTP)
      r.Get("/mcp", mcpH.ServeHTTP)
      r.Delete("/mcp", mcpH.ServeHTTP)
  }
  ```
- `requestTimeout(def, mcp)` (router.go around line 1064) returns
  `middleware.Timeout(def)` when `mcp <= def`. Otherwise it sends
  `POST /mcp` (method and exact path) to `middleware.Timeout(mcp)` and every
  other request to `middleware.Timeout(def)`.
- `Options.MCPServer` is a concrete `*mctlmcp.Server`
  (`internal/mcp/server.go`). Its handler comes from
  `NewStreamableHTTPHandler()`, and its tools reach the API over loopback HTTP,
  so no in-process stub ever sees the request context. Tests in `internal/api`
  build it with `mctlmcp.NewServer("http://127.0.0.1:1", "")`.
- `internal/api/mcp_write_deadline_test.go` has two tests:
  - `TestExtendWriteDeadline` covers the connection write deadline.
  - `TestRequestTimeout` calls `requestTimeout` directly, with a
    `near(got, want)` helper and a 1s tolerance. Nothing goes through
    `NewRouter`.
- Test helper `tokenUsers(map[string]*auth.User)`
  (`internal/api/support_audit_e2e_test.go:160`) is an `AuthMiddleware` that
  maps bearer tokens to users.
- `GET /api/v1/resources/{tenant}` (`h.GetResourceUsage`,
  `internal/api/handlers_read.go:781`) does three things in order:
  1. Requires an admin or tenant member.
  2. Calls `GitReader.GetTenant`.
  3. Calls `QuotaReader.GetNamespaceUsage(r.Context(), tenant)`
     (`internal/api/interfaces.go:33`).

  A stub `QuotaReader` can therefore record the deadline of a non-MCP
  authenticated request.
- `cmd/api/main.go:961` sets `mcpWriteTimeout = supportCfg.Wait + 15*time.Second`
  when support is configured and passes it as `Options.MCPWriteTimeout`.
  `ServerWriteTimeout` is 30s (`internal/api/handlers_roadmap_wave.go:492`).
- `internal/mcp/support.go`, `supportAwait` (lines 566-626): after the poll loop
  and the `context.Canceled` check:
  ```go
  // No poll attempted (the send used the whole budget): ...
  if lastErr != nil {
      reason := "no poll completed within the wait"
      if lastErr != nil {          // always true here
          reason = lastErr.Error()
      }
      return mcplib.NewToolResultError(...)
  }
  return supportResultJSON(supportAnswer{... Note: "still running; ..."}, false), nil
  ```
  The inner check and the `"no poll completed within the wait"` fallback are
  unreachable. The "No poll attempted" comment describes the final
  `supportResultJSON` return (the send reply is the last good read), not the
  error branch it sits above.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/**/values.yaml`: no mctl-api service values file
  was found under `services/` (grep for `mctl-api` only matched other services'
  files), and no `MCP_WRITE_TIMEOUT` / `SUPPORT_WAIT` setting turned up there.
  The repo deploys via its own `helm/` chart. Whether the deployed configuration
  has a support wait was not observed.
- mctl MCP tools were not called. This change touches tests and one
  behaviour-preserving refactor, and no claim in this design depends on
  deployed configuration.

## Proposed solution

### 1. Test seam for the MCP handler (`internal/api/router.go`)

Add an unexported field to `Options`:

```go
// mcpHandler, when set (in-package tests only), replaces
// MCPServer.NewStreamableHTTPHandler() so a test can observe the request
// context /mcp is served with. Production code cannot set it.
mcpHandler http.Handler
```

Restructure the MCP block so that route registration, including
`extendWriteDeadline`, is shared:

```go
var mcpH http.Handler
if opts.MCPServer != nil {
    opts.MCPServer.SetTenantOwnerChecker(h)
    opts.MCPServer.SetAgentReceiptGate(h, opts.AgentReceiptGateMode)
    opts.MCPServer.SetScopedCallAuditor(h)
    mcpH = opts.MCPServer.NewStreamableHTTPHandler()
}
if opts.mcpHandler != nil {
    mcpH = opts.mcpHandler
}
if mcpH != nil {
    r.Post("/mcp", extendWriteDeadline(opts.MCPWriteTimeout, mcpH).ServeHTTP)
    r.Get("/mcp", mcpH.ServeHTTP)
    r.Delete("/mcp", mcpH.ServeHTTP)
}
```

Main never sets the field, because unexported fields cannot be set outside
package `api`. For production the router is the same as before. The stub then
sits in exactly the place the real handler occupies, behind the full
authenticated middleware chain.

### 2. Router wiring test (`internal/api/mcp_write_deadline_test.go`)

Add `TestNewRouterRequestDeadlines`:

- Build
  `NewRouter(Options{AuthMiddleware: tokenUsers({"tok": admin}), MCPWriteTimeout: 75*time.Second, mcpHandler: stub, GitReader: <fake with GetTenant("labs")>, QuotaReader: stub})`.
  - `admin` is a human admin `*auth.User`, built the way existing router tests
    build one.
  - `stub` records `time.Until(deadline)` from `r.Context().Deadline()` and
    fails the test if there is no deadline.
  - The `QuotaReader` stub records the same from the `ctx` it receives.
- Send `POST /mcp` with `Authorization: Bearer tok` through
  `router.ServeHTTP(httptest.NewRecorder(), req)`. Assert the recorded value is
  within 1s of 75s, reusing the `near` semantics from `TestRequestTimeout`.
  Use `httptest.NewRecorder`, not a real server: the
  `extendWriteDeadline` `SetWriteDeadline` failure only logs a warning and
  does not affect the request context.
- Send `GET /api/v1/resources/labs` with the same token and assert the
  recorded value is within 1s of 30s.
- Optionally also assert `GET /mcp` is about 30s. This matches the method
  split in `requestTimeout`.

During implementation, temporarily replace line 494 with
`r.Use(middleware.Timeout(30*time.Second))`, confirm the test fails on the
`POST /mcp` assertion, then revert. Note this in the PR description.

### 3. `supportAwait` cleanup (`internal/mcp/support.go`)

```go
if errors.Is(ctx.Err(), context.Canceled) {
    return nil, ctx.Err()
}
if lastErr != nil {
    return mcplib.NewToolResultError(fmt.Sprintf("task %s is not finished and could not be read (%s); continue with mctl_get_support_task", id, lastErr.Error())), nil
}
// No poll attempted (the send used the whole budget): the send reply is
// the last successful read, so this is an unfinished task, not an error.
return supportResultJSON(supportAnswer{...}, false), nil
```

The output text is unchanged in both branches. The existing `supportAwait`
tests in `internal/mcp` guard this.

## Alternatives

1. **End-to-end through the real MCP server and `mctl_ask_support`.** Set up a
   fake support backend that never finishes and measure how long the tool waits.
   This needs no production seam, but it is slow: it would wait at least 30s to
   tell 30s apart from a longer deadline. It is also indirect, since it measures
   `cfg.Wait` interplay rather than the deadline itself. Dropped.
2. **Extract a helper `authenticatedTimeout(opts)` and unit-test it.** The
   helper itself would be tested, but not its use inside `NewRouter`. Restoring
   `middleware.Timeout(30*time.Second)` at the call site would still pass.
   Dropped: it misses the regression the issue targets.
3. **Make `Options.MCPServer` an interface.** This widens the public API and
   touches every caller and test that sets `MCPServer`, which is too much for a
   P3 test gap. An unexported field is the smallest seam. Dropped.

## Platform impact

- Migrations: none. No API, MCP tool, or config change, and the MCP tool count
  is unchanged.
- Backward compatibility: production routing is the same. The MCP setters are
  still called only when `MCPServer` is set. The seam changes routing only when
  the unexported field is set, which only in-package tests can do.
- Resource impact: none. The new test runs in milliseconds.
- Risks:
  - The restructured MCP block could change registration order or skip the
    setters. Mitigation: existing router tests that pass
    `MCPServer: mctlmcp.NewServer(...)` keep exercising the production path,
    and the diff is reviewed to keep the setter calls inside the
    `MCPServer != nil` branch.
  - Timing flakiness. Mitigation: deadlines are read synchronously, with a 1s
    tolerance, as `TestRequestTimeout` already does.
