# Tasks: issue-287-mctl-trigger-issue-with-use-temporal-tru

- [ ] 1. In `internal/temporalclient/client.go`, factor the
  `enumspb.WORKFLOW_EXECUTION_STATUS_*` switch out of `DescribeDevLoop` into a
  private `statusName(enumspb.WorkflowExecutionStatus) string`, and add
  `DevLoopExecution{Status, RunID, StartTime}` plus
  `DescribeDevLoopExecution(ctx, workflowID) (*DevLoopExecution, error)` reading
  `resp.GetWorkflowExecutionInfo().GetExecution().GetRunId()`. Re-express
  `DescribeDevLoop` as a wrapper over it — DoD: `DescribeDevLoop`'s signature,
  every returned string including the `"Unknown"` default arm, and
  `internal/temporalclient/client_test.go` are unchanged and green.

- [ ] 2. In `internal/temporalclient/client.go`, extract the shared
  `ExecuteWorkflow` call into a private
  `start(ctx, issueURL, reuse, conflict)` and add `RestartDevLoopWorkflow`
  using `WORKFLOW_ID_REUSE_POLICY_ALLOW_DUPLICATE` +
  `WORKFLOW_ID_CONFLICT_POLICY_TERMINATE_EXISTING`, with a doc comment stating
  why `REJECT_DUPLICATE` cannot be reused (a terminated run is a closed run)
  (depends on 1) — DoD: `StartDevLoopWorkflow` still sends
  `REJECT_DUPLICATE`/`USE_EXISTING` and its existing mock-based test passes
  untouched; a new mock test asserts the restart policy pair.

- [ ] 3. Add `DescribeDevLoopExecution` and `RestartDevLoopWorkflow` to the
  `DevLoopClient` interface in `internal/api/interfaces.go` and implement both
  on `fakeDevLoopClient` in `internal/api/handlers_dev_loop_test.go`
  (fields: `describeExec`, `describeExecErr`, `restartErr`,
  `restartWorkflowID`, `restartRunID`, `restartCalls`) (depends on 2) — DoD:
  `go build ./...` and `go test ./internal/api/...` compile with no other test
  file edited.

- [ ] 4. In `internal/api/handlers_dev_loop.go`, add the shared outcome
  constants (`devLoopOutcomeStarted`, `-AlreadyRunning`, `-AlreadyExists`,
  `-Restarted`, `-Failed`), the `devLoopStartResult` struct, the
  `devLoopDescribeTimeout` bound, and
  `startDevLoop(ctx, c DevLoopClient, issueURL, workflowID string, restart bool) devLoopStartResult`
  implementing describe -> classify -> start, including the
  `wf != workflowID` guard (depends on 3) — DoD: the function is pure of HTTP
  concerns (no `http.ResponseWriter`), unit-testable against
  `fakeDevLoopClient`, and documents the describe/start TOCTOU window.

- [ ] 5. Rewrite `Handlers.StartDevLoopWorkflow` to add
  `Restart bool \`json:"restart"\`` to `startDevLoopRequest`, derive the
  workflow id with `temporalclient.WorkflowIDForIssueURL` (400 on
  `ErrInvalidIssueURL`), call `startDevLoop`, and emit the status/body table
  from `design.md` — 202 for `started`/`restarted`, 200 for
  `already_running`/`already_exists`, 502 for `failed` — with
  `workflow_id`, `run_id`, `message` preserved and
  `started`/`outcome`/`status`/`terminated_run_id` added (depends on 4) —
  DoD: auth, 503-not-configured and 400-validation branches are byte-identical
  to today; `handlers_dev_loop_test.go`'s existing Start tests still pass
  except where they assert the old message.

- [ ] 6. Extend the audit entry in that handler: one entry per request,
  `Parameters["outcome"]` always set, `Parameters["restart"]="true"` and
  `Parameters["terminated_run_id"]` when applicable, `Message` naming a no-op
  explicitly, and `RiskLevel` = `string(operations.RiskHigh)` for a restart
  (depends on 5) — DoD: a test asserts the audit entry for an
  `already_running` response contains `outcome=already_running` and a message
  that does not claim a start.

- [ ] 7. In `internal/api/handlers_roadmap_wave.go`, redefine
  `waveOutcomeStarted`/`-AlreadyRunning`/`-AlreadyExists`/`-Failed` as aliases
  of the new constants and replace the per-item describe/start switch in
  `ExecuteRoadmapWave` with a `startDevLoop(..., restart=false)` call inside
  the existing `call()` timeout wrapper (depends on 4) — DoD:
  `internal/api/handlers_roadmap_wave_test.go` passes with zero edits, proving
  the outcome strings and behaviour are unchanged.

- [ ] 8. In `internal/mcp/server.go`, add the `restart` boolean input to
  `toolTriggerIssue`, forward it in the `use_temporal=true` `apiPostJSON` body,
  return a tool error when `restart` is supplied without `use_temporal`, and
  extend the tool description with the idempotency/`started:false`/`restart`
  paragraph (depends on 5) — DoD: `go test ./internal/mcp/...` passes,
  `TestToolTriggerIssue_UseTemporalTruePostsToDevLoopStart` and both
  `...PostsToOperationsExecute` tests still pass, and the tool-count assertion
  in `server_test.go` is unchanged because no tool was added or removed.

- [ ] 9. Update `internal/openapi/openapi.yaml` at
  `/api/v1/agents/dev-loop/start`: `restart` in the request schema, a `200`
  response for the not-started outcomes, and
  `started`/`outcome`/`status`/`terminated_run_id` on the `202` schema
  (depends on 5) — DoD: the spec lints and every field the handler can emit is
  described.

- [ ] 10. Open a follow-up issue in `mctlhq/mctl-agents` for issue #287 item 2
  — DevLoopWorkflow should end rather than keep ticking its shepherd once its
  proposal reaches a terminal state (`needs-triage`, `review-stuck`) — linking
  back to mctl-api#287 (no dependency) — DoD: issue filed and referenced in the
  mctl-api PR body as the out-of-scope half.

- [ ] 11. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run` and
  `go test ./...` (depends on 1-9) — DoD: all clean, per `CLAUDE.md`.

## Tests

- [ ] T1. `internal/temporalclient`: `DescribeDevLoopExecution` returns the run
  id and the mapped status for each `WORKFLOW_EXECUTION_STATUS_*` value, and
  `DescribeDevLoop` returns exactly the same status string it did before the
  refactor (table test over all seven statuses plus the unknown default).
- [ ] T2. `internal/temporalclient`: `RestartDevLoopWorkflow` calls
  `ExecuteWorkflow` with `ALLOW_DUPLICATE` + `TERMINATE_EXISTING` and the same
  task queue, workflow type and `issueRef` payload as `StartDevLoopWorkflow`;
  `StartDevLoopWorkflow` still calls it with `REJECT_DUPLICATE` +
  `USE_EXISTING`.
- [ ] T3. `internal/api`: **the regression test for #287** — describe reports
  `Running`, and the handler responds `200` with `started:false`,
  `outcome:"already_running"`, the existing `run_id`, a message that does not
  contain "DevLoopWorkflow started", and `StartDevLoopWorkflow` is never called
  on the fake.
- [ ] T4. `internal/api`: describe returns NotFound -> `202`, `started:true`,
  `outcome:"started"`, the new run id, and exactly one start call.
- [ ] T5. `internal/api`: describe returns a closed status (`Failed`) ->
  `200`, `outcome:"already_exists"`, `status:"Failed"`, no start call.
- [ ] T6. `internal/api`: describe fails with a non-NotFound error -> `502`,
  no start call, body mentions that the existing DevLoop could not be read.
- [ ] T7. `internal/api`: `restart:true` over a `Running` execution -> `202`,
  `outcome:"restarted"`, `terminated_run_id` equal to the described run id,
  `RestartDevLoopWorkflow` called once and `StartDevLoopWorkflow` not at all.
- [ ] T8. `internal/api`: `restart:true` with no existing execution ->
  `202`, `outcome:"started"`, empty `terminated_run_id`.
- [ ] T9. `internal/api`: audit assertions — `already_running` yields one
  `dev-loop-start` entry with `outcome=already_running` and a non-start
  message; a restart yields `RiskHigh` and `restart=true`.
- [ ] T10. `internal/api`: unchanged branches still hold — nil
  `TemporalClient` -> 503, non-admin -> 403, empty `issue_url` -> 400,
  malformed `issue_url` -> 400 with no Temporal call.
- [ ] T11. `internal/api`: the whole of
  `handlers_roadmap_wave_test.go` passes unedited after task 7.
- [ ] T12. `internal/mcp`: `restart:true` with `use_temporal:true` posts
  `{"issue_url":..., "restart":true}` to `/api/v1/agents/dev-loop/start`;
  `restart` without `use_temporal` returns a tool error and issues no HTTP
  request.

## Rollback

Every change is additive to mctl-api and carries no persisted state — no
migration, no gitops write, no Helm value — so rollback is a single revert of
the PR followed by the normal release: `mctl_rollback_service(team=platform,
component=mctl-api, target_tag=<previous>)`, or a `git revert` plus the
auto-deploy on push to main. The pre-revert behaviour returns immediately: the
`REJECT_DUPLICATE`/`USE_EXISTING` policies on `StartDevLoopWorkflow` are never
modified, so no execution started under the new code behaves differently under
the old.

Partial rollback, if only the restart flag proves troublesome: drop tasks 2, 7,
8's `restart` input and the `restart` branch of task 5, keeping the
describe-then-start reporting fix. The two halves are independent — the
reporting fix needs only `DescribeDevLoopExecution`.

Already-restarted issues are not rolled back by either path: a terminated
DevLoopWorkflow stays terminated, and its replacement run continues. The
`terminated_run_id` in the audit log is the record of what was discarded.
