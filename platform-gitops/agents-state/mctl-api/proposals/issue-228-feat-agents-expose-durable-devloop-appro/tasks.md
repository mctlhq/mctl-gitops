# Tasks: issue-228-feat-agents-expose-durable-devloop-appro

- [ ] 1. Add audit logging to `ApproveDevLoopWorkflow` in
      `internal/api/handlers_dev_loop.go`: after `SignalApprove` resolves,
      call `h.logAudit` with `Operation: "dev-loop-approve"`,
      `WorkflowName: workflowID`, `UserID: user.ID`,
      `Parameters: {"approver": body.Approver, "reason": body.Reason}`
      (reason omitted from the map when empty), and `Status` /`Message`
      set per outcome: `"failed"` + `"workflow not found"` on
      `IsNotFound` (before the 404 write), `"failed"` + `"signal failed:
      "+err.Error()` on any other `SignalApprove` error (before the 502
      write), `"succeeded"` with no message on success (before the 200
      write). Use `RiskLevel: string(operations.RiskMedium)` to match the
      standalone `mctl-agents-approve` operation's risk tier — DoD:
      `ApproveDevLoopWorkflow` calls `h.logAudit` exactly once per
      request on every reachable branch after `user` and `workflowID`
      are known, `go vet`/`golangci-lint` clean, `internal/api` still
      compiles with the new `internal/operations` import.

- [ ] 2. Extend `internal/api/handlers_dev_loop_test.go` to assert the
      new audit entries (depends on 1): inject a fake/stub `audit.Log`
      (or reuse `audit.NewLogger()` directly, matching how other
      `Handlers` tests in this package wire `h.opts.AuditLog`) into the
      existing `TestApproveDevLoopWorkflow_*` table and assert, per
      case: `TestApproveDevLoopWorkflow_Success` → one entry,
      `Operation == "dev-loop-approve"`, `WorkflowName ==
      "dev-loop-mctlhq-mctl-telegram-1"`, `Status == "succeeded"`,
      `Parameters["approver"] == "tester"`; `TestApproveDevLoopWorkflow_
      ExplicitApproverAndReasonPassthrough` → `Parameters["approver"] ==
      "mashkovd"`, `Parameters["reason"] == "looks good"`;
      `TestApproveDevLoopWorkflow_UnknownWorkflowIs404` → `Status ==
      "failed"`, message mentions "not found"; `TestApproveDevLoopWorkflow_
      TemporalFailureIs502` → `Status == "failed"`. Also assert
      `TestApproveDevLoopWorkflow_MalformedBodyIs400` and
      `TestApproveDevLoopWorkflow_MissingWorkflowID` record **no** audit
      entry (input never reached the authorization-relevant state) — DoD:
      `go test ./internal/api/...` passes with these new assertions, and
      fails if the audit call in task 1 is reverted.

- [ ] 3. Add `toolApproveDevLoop()` to `internal/mcp/server.go`, placed
      immediately after `toolTriggerIssue()` (depends on nothing new,
      but written against the same file as task 4): register
      `mctl_approve_dev_loop` with `mcplib.WithTitleAnnotation`,
      `mcplib.WithDestructiveHintAnnotation(false)` (it never destroys
      state — it unblocks a workflow that is itself scoped and
      reviewable), a description that explicitly distinguishes this from
      `mctl-agents-approve`'s direct `.status.yaml` mutation (reuse the
      framing already present in `toolTriggerIssue`'s description),
      required string `workflow_id`, optional string `approver`,
      optional string `reason`. Handler builds a
      `map[string]interface{}` from present args only and calls
      `s.apiPostJSON(ctx,
      "/api/v1/agents/dev-loop/"+url.PathEscape(workflowID)+"/approve",
      body)`, returning `mcplib.NewToolResultError` on failure and
      `mcplib.NewToolResultText(string(body))` on success — DoD: function
      compiles, mirrors the error-handling shape of every other tool
      handler in the file (no bespoke error formatting).

- [ ] 4. Register the new tool in `RegisterTools`
      (`internal/mcp/server.go`): add
      `srv.AddTool(s.toolApproveDevLoop())` directly after
      `srv.AddTool(s.toolTriggerIssue())` (depends on 3) — DoD: tool
      appears in `tools/list` output between `mctl_trigger_issue` and
      `mctl_list_recent_agent_runs`.

- [ ] 5. Bump the hardcoded tool count in
      `internal/mcp/server_test.go` from `70` to `71` (depends on 4) —
      DoD: `go test ./internal/mcp/...` passes; per this repo's
      `CLAUDE.md`, this edit is mandatory whenever the tool count
      changes.

- [ ] 6. Add MCP-layer tests in `internal/mcp/server_test.go` (or a
      sibling `_test.go` in the same package) exercising
      `toolApproveDevLoop`'s handler against a stub HTTP server standing
      in for `mctl-api`, mirroring however `toolTriggerIssue`/other
      `apiPostJSON`-based tools are already tested in this package
      (depends on 3, 4): assert the handler (a) POSTs to
      `/api/v1/agents/dev-loop/{workflow_id}/approve` with the escaped
      `workflow_id` in the path and `{approver, reason}` in the JSON
      body when supplied, (b) never issues a request to
      `/api/v1/operations/mctl-agents-approve/execute` or
      `/api/v1/operations/*implement*/execute` under any input — this is
      the test the issue's "does not call standalone mctl-agents-approve
      or implementer execution" criterion maps to at the MCP layer, (c)
      surfaces a tool-level error (not a panic, not a silent success)
      when the stub returns 404/502/503 — DoD: new tests pass and fail
      if `toolApproveDevLoop` is rewritten to hit the operations-execute
      path instead of the dev-loop route.

- [ ] 7. Update `CHANGELOG.md` with a short entry describing the new
      `mctl_approve_dev_loop` MCP tool and the audit-logging fix to
      `ApproveDevLoopWorkflow` (depends on 1, 3) — DoD: entry present,
      consistent with existing changelog entry style in this file.

## Tests

- [ ] T1. `go test ./internal/api/...` — existing `handlers_dev_loop_test.go`
      suite plus the new audit assertions from task 2 all pass.
- [ ] T2. `go test ./internal/mcp/...` — updated tool-count test (task 5)
      and the new `toolApproveDevLoop` tests (task 6) pass.
- [ ] T3. `go build ./...` and `go vet ./...` clean across the repo
      (per `CLAUDE.md`: `go fmt`, `go vet`, `golangci-lint` before
      committing).
- [ ] T4. Manual/E2E validation against
      `dev-loop-mctlhq-mctl-agents-239` (per the issue's validation
      scenario), post-deploy: call `mctl_approve_dev_loop` with that
      `workflow_id` through an actual MCP client, confirm (a) the
      workflow performs its accepted-status write and launches its own
      scoped implementer (not the standalone Tier 2 implementer trigger),
      and (b) a `"dev-loop-approve"`/`"succeeded"` row appears in the
      audit log for that call. This step is environment-dependent and
      cannot run in CI; track it as a manual follow-up after deploy.

## Rollback

- Both changes are additive and independently revertable:
  - The audit-logging addition to `ApproveDevLoopWorkflow` (task 1) is a
    pure addition of `h.logAudit` calls; reverting it drops back to
    today's (already-shipped) unaudited behavior with no functional
    change to the signal path itself. Safe to revert alone if the audit
    entries turn out to be malformed or too noisy.
  - The MCP tool (tasks 3-6) is a new, independently addressable tool;
    disabling or removing it (and reverting the `server_test.go` count
    in task 5 back to `70`) has no effect on the REST endpoint,
    `mctl_trigger_issue`, or any other existing MCP tool. No proposal or
    workflow state is mutated by adding/removing the tool definition
    itself.
  - If a bad approval is signalled in production, this proposal
    introduces no new way to "undo" it beyond what already exists today
    (the workflow itself, or Temporal operator tooling) — rollback here
    means rolling back the code change, not reversing an already-sent
    Temporal signal.
  - Standard path: revert the `mctl-api` commit/PR for this proposal and
    redeploy the prior image tag; no data migration, no gitops
    `.status.yaml` state is touched by either change, so no gitops-side
    rollback is needed.
