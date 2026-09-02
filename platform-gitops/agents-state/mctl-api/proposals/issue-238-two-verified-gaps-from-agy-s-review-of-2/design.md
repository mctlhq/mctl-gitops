# Design: issue-238-two-verified-gaps-from-agy-s-review-of-2

## Current state

`internal/api/handlers_dev_loop.go` holds the three dev-loop HTTP handlers.
All three share `requireTemporalAdmin` (line 42) for auth/availability
gating, and all three are backed by the `DevLoopClient` interface (see
`internal/api/interfaces.go`) which `internal/api/handlers_dev_loop_test.go`
fakes with `fakeDevLoopClient` for handler-level tests that don't need a live
Temporal server.

`StartDevLoopWorkflow` (lines 69-103) handles
`POST /api/v1/agents/dev-loop/start`:
1. `requireTemporalAdmin` — 503/401/403 early-outs, none audited (by design;
   these are pre-authentication/availability checks, and `ApproveDevLoopWorkflow`
   does not audit its equivalent early-outs either).
2. Decode JSON body → 400 on decode error.
3. Check `body.IssueURL == ""` → 400.
4. Call `h.opts.TemporalClient.StartDevLoopWorkflow(ctx, issueURL)` →
   `temporalclient.ErrInvalidIssueURL` maps to 400, any other error maps to
   502.
5. On success, `writeJSON(w, http.StatusAccepted, ...)` with `workflow_id`,
   `run_id`, `message`. **No `h.logAudit` call anywhere in this function.**

`ApproveDevLoopWorkflow` (lines 116-185), by contrast, calls `h.logAudit`
on all three of its outcomes reachable past validation: not-found (148),
generic signal failure (160), success (173). Each entry sets
`Operation: "dev-loop-approve"`, `Parameters` (built from the request body),
`WorkflowName: workflowID` (known up front here, since it comes from the URL
path param, not a return value), `Status`, `RiskLevel: string(operations.RiskMedium)`,
and `Message` on failure. `h.logAudit` itself (`internal/api/clientmeta.go:171`)
is a thin wrapper: no-ops if `h.opts.AuditLog == nil`, else enriches the
entry with client IP/user-agent/request-ID from context and calls
`h.opts.AuditLog.Log(entry)`. `audit.Entry` and the `audit.Log` interface
live in `internal/audit/logger.go`; `audit.NewLogger()` gives an in-memory
implementation already used throughout `handlers_dev_loop_test.go`
(e.g. `TestApproveDevLoopWorkflow_Success`, line 270) to assert on
`logger.List(10)`.

On the MCP side, `internal/mcp/server.go`'s `toolTriggerIssue` (lines
2489-2535) defines the `mctl_trigger_issue` tool with two params:
`issue_url` (required string) and `use_temporal` (optional bool). Its
handler (2517-2533):
```go
if useTemporal, ok := req.GetArguments()["use_temporal"].(bool); ok && useTemporal {
    body, err := s.apiPostJSON(ctx, "/api/v1/agents/dev-loop/start", map[string]interface{}{
        "issue_url": stringArg(req, "issue_url"),
    })
    ...
    return mcplib.NewToolResultText(string(body)), nil
}
params := extractStringParams(req.GetArguments())
body, err := s.apiPost(ctx, "/api/v1/operations/mctl-agents-investigate/execute", params)
...
```
`git grep use_temporal -- '*_test.go'` (re-verified during this
investigation) confirms zero matches in `internal/mcp/server_test.go` or
anywhere else — no test exercises either branch of this `if`.

`internal/mcp/server_test.go` already has the exact pattern to copy for the
sibling tool: `callToolApproveDevLoop` (line 341) builds a `NewServer`
against an `httptest.NewServer` backend and invokes the raw handler
returned by `srv.toolApproveDevLoop()` directly (bypassing the MCP
transport), then the backend handler captures `r.URL.Path`,
`r.Method`, and the decoded JSON body. `TestToolApproveDevLoop_PostsToDevLoopApprovePath`
(353) and `TestToolApproveDevLoop_NeverHitsOperationsExecute` (438) are the
two shapes of assertion this proposal mirrors for `toolTriggerIssue`.

## Proposed solution

### 1. Audit `StartDevLoopWorkflow`

Add `h.logAudit` calls to `StartDevLoopWorkflow`, matching
`ApproveDevLoopWorkflow`'s shape exactly, with these outcomes:

- **Decode-JSON-error 400** and **missing-`issue_url` 400**: no audit call.
  These are the same class of "malformed/incomplete caller input never
  reached policy or Temporal" rejection that `ApproveDevLoopWorkflow`'s own
  `missing workflow_id path parameter` and malformed-body checks (lines
  123-126, 128-132) do not audit today. This keeps the boundary the issue
  asks for ("same boundary #236 drew") consistent across both handlers.
- **`temporalclient.ErrInvalidIssueURL` 400**: no audit call, for the same
  reason — caller input, not a platform state change, never reached
  Temporal successfully enough to be worth a durable record. (This is an
  explicit design choice; see Alternatives for the rejected "audit every
  branch" option.)
- **Other `TemporalClient.StartDevLoopWorkflow` error → 502**: call
  `h.logAudit` with `Operation: "dev-loop-start"`,
  `Parameters: map[string]string{"issue_url": body.IssueURL}`,
  `WorkflowName: ""` (not known — the call failed before returning one),
  `Status: "failed"`, `RiskLevel: string(operations.RiskMedium)`,
  `Message: "failed to start dev-loop workflow: " + err.Error()`.
- **Success → 202**: call `h.logAudit` with `Operation: "dev-loop-start"`,
  `Parameters: map[string]string{"issue_url": body.IssueURL}`,
  `WorkflowName: workflowID` (the value just returned by
  `StartDevLoopWorkflow`), `Status: "succeeded"`,
  `RiskLevel: string(operations.RiskMedium)`, called after the Temporal
  call returns and before (or interleaved with, order does not matter
  functionally) the `writeJSON` response — exactly as the issue specifies
  ("the entry must be written after the call, not before the write of the
  response").

No new imports are needed beyond what `ApproveDevLoopWorkflow` already
pulls into this file (`audit`, `operations`) — both packages are already
imported in `handlers_dev_loop.go` (lines 27, 29).

### 2. Test `use_temporal` routing in `toolTriggerIssue`

Add a new test block to `internal/mcp/server_test.go`, following the
existing `callToolApproveDevLoop` helper pattern, with a
`callToolTriggerIssue(t, apiURL, args)` helper that resolves
`srv.toolTriggerIssue()` and invokes its handler directly. Three test
cases:

- `TestToolTriggerIssue_UseTemporalTruePostsToDevLoopStart`: stub backend
  asserts `r.Method == POST`, `r.URL.Path == "/api/v1/agents/dev-loop/start"`,
  and the decoded JSON body has `issue_url` matching the input, when called
  with `use_temporal: true`.
- `TestToolTriggerIssue_UseTemporalAbsentPostsToOperationsExecute`: stub
  backend asserts the path is `/api/v1/operations/mctl-agents-investigate/execute`
  when `use_temporal` is omitted from the args map entirely.
- `TestToolTriggerIssue_UseTemporalFalsePostsToOperationsExecute`: same
  assertion as above, but with `use_temporal: false` explicit in the args —
  covers the issue's explicit requirement that "a test that only covers
  `true` does not catch a branch that fires unconditionally" by checking
  both the absent and the explicit-false input.

Each of the three also asserts (via a `t.Errorf` inside the backend
handler, same style as `TestToolApproveDevLoop_NeverHitsOperationsExecute`)
that the *other* endpoint is never hit — i.e. the temporal-path tests fail
loudly if a request lands on `/api/v1/operations/...`, and the
operations-path tests fail loudly if a request lands on
`/api/v1/agents/dev-loop/start`. This directly guards the issue's stated
risk: "a regression in either the extraction of the flag or the routing
would ship silently."

### Why this shape

Both fixes copy an existing, already-reviewed pattern in the same files
rather than inventing a new one: the audit shape from
`ApproveDevLoopWorkflow`, and the MCP stub-server test shape from
`TestToolApproveDevLoop_*`. This keeps the two handlers/tools consistent
with each other, which is exactly the asymmetry the issue is about.

## Alternatives

1. **Audit every `StartDevLoopWorkflow` branch, including the 400s.**
   Rejected: the issue explicitly says the fix should mirror #236's shape,
   and `ApproveDevLoopWorkflow`'s own 400-class validation failures
   (missing `workflow_id`, malformed JSON body) are not audited either —
   only outcomes that reached the `TemporalClient` call are. Auditing pure
   input-validation 400s would be a wider behavior change than the issue
   asks for, would break the "400 paths... same boundary #236 drew" framing
   the issue is explicit about, and would need its own justification the
   issue doesn't provide.
2. **Write the audit entry before calling `TemporalClient.StartDevLoopWorkflow`,
   then `UpdateStatus` it afterward (matching the pattern `audit.Logger.UpdateStatus`
   supports for async Argo-workflow completion).** Rejected: that pattern
   exists for genuinely async operations where the outcome is discovered
   later via webhook. `StartDevLoopWorkflow`'s Temporal call is synchronous
   from the handler's point of view — the outcome (workflow ID or error) is
   known before the HTTP response is written, so a single terminal
   `logAudit` call after the fact is simpler and matches
   `ApproveDevLoopWorkflow`'s own synchronous shape.
3. **Test `toolTriggerIssue` end-to-end through the real MCP transport
   (`server.ServeStdio` or similar) instead of calling the handler function
   directly.** Rejected: `TestToolApproveDevLoop_*` already establishes the
   convention of calling the tool's handler closure directly against an
   `httptest.Server` stub, which is faster, has zero MCP-protocol
   boilerplate, and is exactly what the issue's own reference point
   (`TestToolApproveDevLoop_*`) does.

## Platform impact

- **Migrations**: none. `audit.Entry` and `audit.Logger` are unchanged;
  this only adds more `Log()` calls with existing field types.
- **Backward compatibility**: no API contract changes — request/response
  shapes for `StartDevLoopWorkflow` and `mctl_trigger_issue` are untouched.
  Purely additive observability plus test coverage.
- **Resource impact**: negligible — one more in-memory (or Postgres, in
  production per the doc comment on `audit.Logger`) audit row per
  `StartDevLoopWorkflow` call, same order of magnitude as
  `ApproveDevLoopWorkflow` already produces.
- **Risks**:
  - Risk: forgetting to audit the "other/502" branch while adding the
    success branch (easy to miss since it's the branch the issue's prose
    discusses least). Mitigation: task list below requires a dedicated
    test (`TestStartDevLoopWorkflow_TemporalFailureIs502` extended, or a
    new `_AuditsFailure` test) asserting an audit entry with `Status: "failed"`
    exists on that path specifically, not just the success path.
  - Risk: `Parameters` map key drift (e.g. `"issue_url"` vs `"issueUrl"`)
    making the audit entry harder to query alongside `dev-loop-approve`
    entries. Mitigation: use the same `map[string]string` literal style
    already in `ApproveDevLoopWorkflow` and name the key `issue_url` to
    match the JSON field name in `startDevLoopRequest`.
  - Risk: the two new/changed test files (`handlers_dev_loop_test.go`,
    `server_test.go`) could silently diverge from `CLAUDE.md`'s stated
    convention "MCP tool count must match `server_test.go` expectation" if
    a reviewer assumes new tests imply a new tool. Mitigation: this
    proposal adds no new MCP tool (only test coverage for the existing
    `mctl_trigger_issue` tool), so the tool-count constant in
    `server_test.go` does not change — call this out explicitly in the PR
    description so it isn't mistaken for an oversight.
