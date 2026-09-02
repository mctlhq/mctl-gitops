# Tasks: issue-238-two-verified-gaps-from-agy-s-review-of-2

- [ ] 1. Add `h.logAudit` call on the `TemporalClient.StartDevLoopWorkflow`
      generic-error (502) branch in `internal/api/handlers_dev_loop.go`
      (inside the `if err != nil` block, after the `ErrInvalidIssueURL`
      check, before `writeError(w, http.StatusBadGateway, ...)` or right
      after it). Use `Operation: "dev-loop-start"`,
      `Parameters: map[string]string{"issue_url": body.IssueURL}`,
      `WorkflowName: ""`, `Status: "failed"`,
      `RiskLevel: string(operations.RiskMedium)`,
      `Message: "failed to start dev-loop workflow: " + err.Error()`.
      — DoD: code compiles; the branch is covered by task 3's test.

- [ ] 2. Add `h.logAudit` call on `StartDevLoopWorkflow`'s success path in
      `internal/api/handlers_dev_loop.go`, after the
      `h.opts.TemporalClient.StartDevLoopWorkflow` call returns
      `workflowID, runID, nil` and before/alongside the `writeJSON(w,
      http.StatusAccepted, ...)` call. Use `Operation: "dev-loop-start"`,
      `Parameters: map[string]string{"issue_url": body.IssueURL}`,
      `WorkflowName: workflowID`, `Status: "succeeded"`,
      `RiskLevel: string(operations.RiskMedium)`. — DoD: code compiles; the
      entry's `WorkflowName` is populated from the value actually returned
      by `StartDevLoopWorkflow`, not a placeholder; covered by task 3's
      test.

- [ ] 3. (depends on 1, 2) Add/extend tests in
      `internal/api/handlers_dev_loop_test.go` asserting the new audit
      behavior, following `TestApproveDevLoopWorkflow_Success`'s pattern
      (construct `audit.NewLogger()`, pass it via `Options{..., AuditLog: logger}`,
      assert on `logger.List(10)` afterward):
      - Extend `TestStartDevLoopWorkflow_TemporalFailureIs502` (or add a
        sibling test) to construct an `audit.Logger`, wire it into `Options`,
        and assert exactly one entry with `Operation: "dev-loop-start"`,
        `Status: "failed"`, `WorkflowName: ""`, and
        `Parameters["issue_url"]` equal to the request's issue URL.
      - Extend `TestStartDevLoopWorkflow_Success` (or add a sibling test)
        the same way, asserting `Status: "succeeded"` and
        `WorkflowName` equal to `fake.workflowID`.
      - Extend `TestStartDevLoopWorkflow_MissingIssueURL` and
        `TestStartDevLoopWorkflow_InvalidIssueURLIs400` to also wire in an
        `audit.Logger` and assert `len(logger.List(10)) == 0` — the "400
        paths must assert no entry" requirement from the issue.
      — DoD: `go test ./internal/api/...` passes; each of the four
      assertions above is a distinct, named test case (not folded into one
      giant test), matching the existing one-behavior-per-test style in
      this file.

- [ ] 4. Add a `callToolTriggerIssue` test helper to
      `internal/mcp/server_test.go`, modeled on `callToolApproveDevLoop`
      (around line 341): build `NewServer(apiURL, "test-token")`, resolve
      `srv.toolTriggerIssue()`, invoke its handler with a
      `mcplib.CallToolRequest{Params: mcplib.CallToolParams{Name:
      "mctl_trigger_issue", Arguments: args}}`. — DoD: helper compiles and
      is used by task 5's tests.

- [ ] 5. (depends on 4) Add three tests to `internal/mcp/server_test.go`:
      - `TestToolTriggerIssue_UseTemporalTruePostsToDevLoopStart`: stub
        `httptest.Server` backend records method/path/body; call with
        `{"issue_url": "https://github.com/mctlhq/mctl-telegram/issues/1",
        "use_temporal": true}`; assert `POST /api/v1/agents/dev-loop/start`
        with decoded JSON body `{"issue_url": "..."}` matching the input,
        and fail the test (via `t.Errorf` inside the backend handler, same
        style as `TestToolApproveDevLoop_NeverHitsOperationsExecute`) if any
        request path contains `/api/v1/operations/`.
      - `TestToolTriggerIssue_UseTemporalAbsentPostsToOperationsExecute`:
        same backend-assertion style, called with only `{"issue_url": "..."}`
        (no `use_temporal` key at all); assert
        `POST /api/v1/operations/mctl-agents-investigate/execute`, and fail
        if any request path is `/api/v1/agents/dev-loop/start`.
      - `TestToolTriggerIssue_UseTemporalFalsePostsToOperationsExecute`:
        identical assertions to the previous test, but called with
        `{"issue_url": "...", "use_temporal": false}` explicit — this is
        the "both directions matter" case the issue calls out by name.
      — DoD: `go test ./internal/mcp/...` passes; each test fails loudly
      (not silently passes) if `toolTriggerIssue`'s branch condition is
      inverted or the flag extraction is broken (verify by temporarily
      flipping the `ok && useTemporal` condition locally and confirming the
      relevant test(s) fail, then revert).

- [ ] 6. Run `go fmt ./...`, `go vet ./...`, and `golangci-lint run` per
      `CLAUDE.md`'s stated pre-commit conventions; run the full
      `go test ./...` and confirm the MCP tool count assertion in
      `internal/mcp/server_test.go` is unaffected (no tool was added or
      removed, only tests). — DoD: all three commands exit clean; full test
      suite green.

## Tests

- [ ] T1. `TestStartDevLoopWorkflow_TemporalFailureIs502` (extended) —
      asserts exactly one `dev-loop-start`/`failed` audit entry with empty
      `WorkflowName` on a generic Temporal RPC error.
- [ ] T2. `TestStartDevLoopWorkflow_Success` (extended) — asserts exactly
      one `dev-loop-start`/`succeeded` audit entry with `WorkflowName`
      equal to the workflow ID returned by the fake client.
- [ ] T3. `TestStartDevLoopWorkflow_MissingIssueURL` (extended) — asserts
      zero audit entries on the missing-`issue_url` 400.
- [ ] T4. `TestStartDevLoopWorkflow_InvalidIssueURLIs400` (extended) —
      asserts zero audit entries on the `ErrInvalidIssueURL` 400.
- [ ] T5. `TestToolTriggerIssue_UseTemporalTruePostsToDevLoopStart` — new;
      asserts the Temporal-start POST shape and that the operations-execute
      path is never hit.
- [ ] T6. `TestToolTriggerIssue_UseTemporalAbsentPostsToOperationsExecute`
      — new; asserts the default/absent-flag routing and that
      dev-loop/start is never hit.
- [ ] T7. `TestToolTriggerIssue_UseTemporalFalsePostsToOperationsExecute`
      — new; asserts explicit-`false` routing matches the absent case and
      that dev-loop/start is never hit.

## Rollback

All changes are additive (more `logAudit` calls, more test functions) with
no schema, API-contract, or config changes. If the audit-logging change
causes unexpected issues in production (e.g. audit-log volume, or a bug in
the new `logAudit` call sites), revert the single commit touching
`internal/api/handlers_dev_loop.go`'s `StartDevLoopWorkflow` function — the
handler's request/response behavior is otherwise untouched, so reverting
only removes the two new `logAudit` calls and drops back to the pre-fix
(unaudited) state with no other side effects. The new tests
(`handlers_dev_loop_test.go`, `server_test.go`) can be reverted independently
of the production code change if needed, since they assert behavior rather
than implement it. No database migration or feature flag is involved, so
rollback is a plain `git revert` of the PR.
