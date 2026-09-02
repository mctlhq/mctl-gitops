# Tasks: issue-235-feat-mcp-mctl-agents-reconcile-and-appro

- [ ] 1. Add `toolTriggerReconcile` to `internal/mcp/server.go`, placed
      after `toolTriggerShepherd` (around `server.go:2487`) — DoD: function
      returns `(mcplib.Tool, server.ToolHandlerFunc)` named
      `mctl_trigger_reconcile`, with `WithTitleAnnotation`,
      `WithDestructiveHintAnnotation(true)`, a description adapted from
      `registry.go:641`'s `Description` field plus Cost/Duration/Result
      lines matching sibling tools, and `WithString("service", ...)` /
      `WithString("dry_run", ...)` parameters whose `Enum` values are
      copied verbatim from `registry.go:648-650`. Handler calls
      `extractStringParams` then `s.apiPost(ctx,
      "/api/v1/operations/mctl-agents-reconcile/execute", params)`,
      returning `mcplib.NewToolResultError` on error and
      `mcplib.NewToolResultText(string(body))` on success.

- [ ] 2. Add `toolTriggerApprove` to `internal/mcp/server.go`, placed
      after `toolTriggerReconcile` (depends on 1) — DoD: function returns
      `(mcplib.Tool, server.ToolHandlerFunc)` named `mctl_trigger_approve`,
      with `WithTitleAnnotation`, `WithDestructiveHintAnnotation(true)`, a
      description adapted from `registry.go:610`'s `Description` field plus
      Cost/Duration/Result lines, and text explicitly distinguishing this
      tool from `mctl_approve_dev_loop` (`server.go:2537`) — state that a
      proposal with a live `DevLoopWorkflow` should be approved via
      `mctl_approve_dev_loop` instead, per the issue's #228 cross-reference.
      `WithString("service", ...)` (required, enum copied from
      `registry.go:621`), `WithString("slug", ...)` (required, no enum),
      `WithString("approver", ...)` (optional, description notes the server
      defaults it to the caller's identity per
      `handlers_write.go:138-144`). Handler calls `extractStringParams` then
      `s.apiPost(ctx, "/api/v1/operations/mctl-agents-approve/execute",
      params)`, same success/error handling as task 1.

- [ ] 3. Register both new tools in `NewMCPServer()`'s "mctl-agents
      triggers" block (`server.go:150-158`) (depends on 1, 2) — DoD:
      `srv.AddTool(s.toolTriggerReconcile())` and
      `srv.AddTool(s.toolTriggerApprove())` added after
      `srv.AddTool(s.toolTriggerShepherd())` and before
      `srv.AddTool(s.toolTriggerIssue())`; `go build ./...` succeeds.

- [ ] 4. Add `TestMCPToolsCoverEveryNonHandlerOnlyOperation` to
      `internal/mcp/server_test.go` (depends on 3) — DoD: test builds
      `reg := operations.NewRegistry()`, calls `srv.NewMCPServer()`, reads
      the registered tool names via a `tools/list` JSON-RPC call through
      `mcpSrv.HandleMessage` (same pattern as
      `TestAllToolsHaveTitleAnnotation`, `server_test.go:142-176`), and for
      every `op := range reg.List()` with `op.HandlerOnly == false` looks up
      `op.Name` in a package-level `operationToTool map[string]string`
      fixture covering every non-`HandlerOnly` registry entry (all nine
      `mctl-agents-*` operations plus `deploy-service`, `create-tenant`,
      `provision-database`, `retire-service`, `delete-tenant`,
      `sync-repos`, `rollback-service`, `preview-deploy`, `preview-delete`,
      `add-custom-domain`, `remove-custom-domain`, `scale-service`, and any
      other non-`HandlerOnly` entries found in `registry.go` by grepping for
      operation `Name` fields without `HandlerOnly: true` nearby); asserts
      the mapped tool name is present in the live tool set, `t.Errorf` on
      any missing map entry or missing live tool, naming the operation.

- [ ] 5. Bump `TestAllToolsHaveTitleAnnotation`'s hardcoded tool-count
      literal in `internal/mcp/server_test.go` from `71` to `73`
      (`server_test.go:169`) (depends on 3) — DoD: `go test ./internal/mcp/...`
      passes with the new count; this is the literal `CLAUDE.md` calls out
      ("MCP tool count must match server_test.go expectation").

- [ ] 6. Verify the parity test actually detects the gap it targets
      (depends on 4) — DoD: temporarily delete the
      `srv.AddTool(s.toolTriggerReconcile())` line (or the
      `srv.AddTool(s.toolTriggerApprove())` line), confirm
      `TestMCPToolsCoverEveryNonHandlerOnlyOperation` fails, then restore
      the line and confirm it passes again. This is the issue's explicit
      "Acceptance: delete either new tool and the parity test must go red"
      check, performed by hand once and not left as a permanent step.

- [ ] 7. Run repo-standard checks (depends on 1-5) — DoD: `go fmt ./...`,
      `go vet ./...`, `golangci-lint run` all clean; `go test ./...` green;
      per `CLAUDE.md`, MCP tool count in `server_test.go` matches the
      registered count.

## Tests

- [ ] T1. `TestMCPToolsCoverEveryNonHandlerOnlyOperation` (new, task 4) —
      fails if any non-`HandlerOnly` `operations.Registry` entry has no
      corresponding registered MCP tool; passes after tasks 1-3.
- [ ] T2. `TestAllToolsHaveTitleAnnotation` (existing, `server_test.go:142`,
      updated in task 5) — count literal bumped to 73; both new tools carry
      a non-empty `WithTitleAnnotation`, satisfying the existing per-tool
      loop unchanged.
- [ ] T3. New unit tests for `toolTriggerReconcile` mirroring the shape of
      `TestToolApproveDevLoop_PostsToDevLoopApprovePath` /
      `TestToolApproveDevLoop_OmitsEmptyOptionalArgs`
      (`server_test.go:353-437`) but targeted at
      `/api/v1/operations/mctl-agents-reconcile/execute`: assert the POST
      path and method, assert `service`/`dry_run` args are forwarded when
      present and omitted when absent, assert errors surface via
      `mcplib.NewToolResultError` without panicking.
- [ ] T4. Equivalent new unit tests for `toolTriggerApprove` targeted at
      `/api/v1/operations/mctl-agents-approve/execute`: assert `service`,
      `slug`, and `approver` are forwarded; assert the tool does not
      hardcode or override `approver` client-side (that defaulting is
      server-side per `handlers_write.go:138-144`, so the MCP layer should
      just pass through whatever the caller supplied, including nothing).
- [ ] T5. Manual smoke check (not automated): with a real or staging API
      token, call `mctl_trigger_reconcile` with `dry_run="true"` and confirm
      a `202`-style response body is returned, matching the issue's own
      manual verification (`mctl-agents-reconcile-e2a3f64f` on 2026-09-02).

## Rollback

- All changes are additive to `internal/mcp/server.go` and
  `internal/mcp/server_test.go` only; no `registry.go`, `handlers_write.go`,
  database, or GitOps schema changes are made, so rollback is a plain
  `git revert` of the commit(s) introducing these two functions, their
  registration, and the new/updated tests.
- Because both underlying operations (`mctl-agents-approve`,
  `mctl-agents-reconcile`) already exist and work server-side (per the
  issue's own successful `curl` invocation), reverting the MCP-layer change
  only removes the new tool surface — it does not affect any in-flight
  Argo Workflow, `.status.yaml` state, or GitOps commit already produced by
  a prior invocation through either the new tools or the pre-existing
  `curl` workaround.
- If `TestAllToolsHaveTitleAnnotation`'s bumped count (task 5) or the new
  parity test (task 4) turns out to be flaky or wrong in CI, the safe
  interim step is to revert only the test changes while keeping the two new
  tools live — the tools are useful for operators immediately, and the
  drift-guard tests can be relanded separately once corrected.
