# Router wiring test for MCPWriteTimeout and supportAwait dead-branch cleanup

## Context

PR #841 (mctl-api#814) made POST /mcp get a longer request deadline than the
30s default. The authenticated group in `NewRouter` (`internal/api/router.go`)
now uses `r.Use(requestTimeout(30*time.Second, opts.MCPWriteTimeout))` where it
used `middleware.Timeout(30*time.Second)` before. `TestRequestTimeout`
(`internal/api/mcp_write_deadline_test.go`) tests the `requestTimeout`
middleware on its own. No test checks that `NewRouter` actually installs it with
`opts.MCPWriteTimeout`. If someone restored `middleware.Timeout(30*time.Second)`,
or passed the wrong duration, every test would still pass. The
`mctl_ask_support` wait would then be cut back to 30s in production without
anyone noticing.

The review of #841 also found dead code in `supportAwait`
(`internal/mcp/support.go`). After the loop, the `if lastErr != nil` branch
contains a second `if lastErr != nil` check, which is always true there. The
"No poll attempted" comment also sits above the wrong branch. Both items are
P3 follow-ups deferred from the #841 review.

## User stories

- AS a mctl-api maintainer I WANT a router-level test that pins the POST /mcp
  request deadline to `Options.MCPWriteTimeout` SO THAT a regression in the
  wiring of `NewRouter` fails CI instead of silently shortening
  `mctl_ask_support` waits.
- AS a mctl-api maintainer I WANT `supportAwait` free of unreachable branches
  and with its comments next to the code they describe SO THAT the function is
  easier to read and change safely.

## Acceptance criteria (EARS)

- WHEN a test builds `NewRouter` with `MCPWriteTimeout` greater than 30s
  (e.g. 75s) and a stub MCP handler, and sends an authenticated `POST /mcp`,
  THE SYSTEM SHALL give the stub a request context deadline within one second
  of `MCPWriteTimeout` from now.
- WHEN the same router serves another authenticated route (e.g.
  `GET /api/v1/resources/{tenant}`), THE SYSTEM SHALL give a request context
  deadline within one second of 30s from now.
- IF the authenticated group's timeout middleware in `NewRouter` is replaced by
  `middleware.Timeout(30*time.Second)` THEN the new router test SHALL fail.
  This is checked by hand once during implementation and is not committed.
- WHILE `Options.MCPServer` is set and the test seam is unset, THE SYSTEM SHALL
  register the same /mcp routes and call the same `MCPServer` setters as today.
  Production behaviour does not change.
- WHEN `supportAwait` exits the poll loop with `lastErr != nil` after a client
  cancellation check, THE SYSTEM SHALL return the same tool error text as today:
  `task <id> is not finished and could not be read (<lastErr>); continue with
  mctl_get_support_task`.
- WHEN `supportAwait` exits the poll loop with `lastErr == nil`, THE SYSTEM SHALL
  return the same "still running" `supportResultJSON` as today. The
  "No poll attempted" comment SHALL sit next to that return.
- WHILE the change is applied, THE SYSTEM SHALL keep the MCP tool count
  unchanged, so `server_test.go` needs no update.

## Out of scope

- Changing the value of the 30s default or how `MCPWriteTimeout` is derived in
  `cmd/api/main.go` (`supportCfg.Wait + 15*time.Second`).
- Testing the connection write deadline (`extendWriteDeadline`) through the
  router. `TestExtendWriteDeadline` already covers it, and this issue only asks
  about the request context deadline.
- Any other behaviour change in `supportAwait` or the support tools.
- Helm or GitOps changes.

## Open questions

- `Options.MCPServer` is a concrete `*mctlmcp.Server`, and no existing hook
  lets a test observe the request context inside the MCP handler. This proposal
  adds an unexported `Options` field, `mcpHandler http.Handler`, that only
  in-package tests can set. It replaces `MCPServer.NewStreamableHTTPHandler()`
  when set. If reviewers prefer no production seam at all, the alternative is a
  slower end-to-end test through `mctl_ask_support` (see design.md,
  Alternatives).
- Which non-MCP authenticated route to use for the 30s check: this proposal
  uses `GET /api/v1/resources/{tenant}` because it passes `r.Context()` to the
  `QuotaReader` stub. Any route whose dependency receives `r.Context()` would
  work.
