# Tasks: issue-287-mctl-trigger-issue-with-use-temporal-tru

- [ ] 1. In `internal/temporalclient/client.go`, factor the
  `enumspb.WORKFLOW_EXECUTION_STATUS_*` switch out of `DescribeDevLoop` into a
  private `statusName(enumspb.WorkflowExecutionStatus) string`, and add
  `DevLoopExecution{Status, RunID, StartTime}` plus
  `DescribeDevLoopExecution(ctx, workflowID) (*DevLoopExecution, error)` reading
  `resp.GetWorkflowExecutionInfo().GetExecution().GetRunId()`. Re-express
  `DescribeDevLoop` as a wrapper over it — DoD: `DescribeDevLoop`'s signature,
  every returned string including the `"Unknown"` default arm, and
  `internal/temporalclient/client_test.go` are unchanged and green;
  `StartDevLoopWorkflow` and its `REJECT_DUPLICATE`/`USE_EXISTING` policies are
  not touched.

- [ ] 2. Add `DescribeDevLoopExecution` to the `DevLoopClient` interface in
  `internal/api/interfaces.go` and implement it on `fakeDevLoopClient` in
  `internal/api/handlers_dev_loop_test.go` (fields: `describeExec`,
  `describeExecErr`) (depends on 1) — DoD: `go build ./...` and
  `go test ./internal/api/...` compile with no other test file edited.

- [ ] 3. In `internal/api/handlers_dev_loop.go`, add the shared outcome
  constants (`devLoopOutcomeStarted`, `-AlreadyRunning`, `-AlreadyExists`,
  `-Failed`), the `devLoopStartResult` struct, the `devLoopDescribeTimeout`
  bound, and
  `startDevLoop(ctx, c DevLoopClient, issueURL, workflowID string) devLoopStartResult`
  implementing describe -> classify -> start, including the
  `wf != workflowID` guard (depends on 2) — DoD: the function is pure of HTTP
  concerns (no `http.ResponseWriter`), unit-testable against
  `fakeDevLoopClient`, and documents the describe/start TOCTOU window.

- [ ] 4. Rewrite `Handlers.StartDevLoopWorkflow` to derive the workflow id with
  `temporalclient.WorkflowIDForIssueURL` (400 on `ErrInvalidIssueURL`), call
  `startDevLoop`, and emit the status/body table from `design.md` — 202 for
  `started`, 200 for `already_running`/`already_exists`, 502 for `failed` —
  with `workflow_id`, `run_id`, `message` preserved and
  `started`/`outcome`/`status` added; `startDevLoopRequest` is unchanged
  (depends on 3) — DoD: auth, 503-not-configured and 400-validation branches
  are byte-identical to today; `handlers_dev_loop_test.go`'s existing Start
  tests still pass except where they assert the old message.

- [ ] 5. Extend the audit entry in that handler: one entry per request,
  `Parameters["outcome"]` always set and `Message` naming a no-op explicitly;
  the risk level is unchanged (depends on 4) — DoD: a test asserts the audit
  entry for an `already_running` response contains `outcome=already_running`
  and a message that does not claim a start.

- [ ] 6. In `internal/api/handlers_roadmap_wave.go`, redefine
  `waveOutcomeStarted`/`-AlreadyRunning`/`-AlreadyExists`/`-Failed` as aliases
  of the new constants and replace the per-item describe/start switch in
  `ExecuteRoadmapWave` with a `startDevLoop(...)` call inside the existing
  `call()` timeout wrapper (depends on 3) — DoD:
  `internal/api/handlers_roadmap_wave_test.go` passes with zero edits, proving
  the outcome strings and behaviour are unchanged.

- [ ] 7. In `internal/mcp/server.go`, extend the `toolTriggerIssue`
  description with the idempotency/`started:false` paragraph; add no input
  (depends on 4) — DoD: `go test ./internal/mcp/...` passes,
  `TestToolTriggerIssue_UseTemporalTruePostsToDevLoopStart` and both
  `...PostsToOperationsExecute` tests still pass, and the tool-count assertion
  in `server_test.go` is unchanged because no tool was added or removed.

- [ ] 8. Update `internal/openapi/openapi.yaml` at
  `/api/v1/agents/dev-loop/start`: a `200` response for the not-started
  outcomes and `started`/`outcome`/`status` on the `202` schema; the request
  schema is unchanged (depends on 4) — DoD: the spec lints and every field the
  handler can emit is described.

- [ ] 9. Open a follow-up issue in `mctlhq/mctl-agents` for issue #287 item 2
  — DevLoopWorkflow should end rather than keep ticking its shepherd once its
  proposal reaches a terminal state (`needs-triage`, `review-stuck`) — linking
  back to mctl-api#287 (no dependency) — DoD: issue filed and referenced in the
  mctl-api PR body as the out-of-scope half. Reference mctl-api#404 (explicit
  restart follow-up) in the same PR body; do not implement it here.

- [ ] 10. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run` and
  `go test ./...` (depends on 1-8) — DoD: all clean, per `CLAUDE.md`.

## Tests

- [ ] T1. `internal/temporalclient`: `DescribeDevLoopExecution` returns the run
  id and the mapped status for each `WORKFLOW_EXECUTION_STATUS_*` value, and
  `DescribeDevLoop` returns exactly the same status string it did before the
  refactor (table test over all seven statuses plus the unknown default).
- [ ] T2. `internal/api`: **the regression test for #287** — describe reports
  `Running`, and the handler responds `200` with `started:false`,
  `outcome:"already_running"`, the existing `run_id`, a message that does not
  contain "DevLoopWorkflow started", and `StartDevLoopWorkflow` is never called
  on the fake.
- [ ] T3. `internal/api`: describe returns NotFound -> `202`, `started:true`,
  `outcome:"started"`, the new run id, and exactly one start call.
- [ ] T4. `internal/api`: describe returns a closed status (`Failed`) ->
  `200`, `outcome:"already_exists"`, `status:"Failed"`, no start call.
- [ ] T5. `internal/api`: describe fails with a non-NotFound error -> `502`,
  no start call, body mentions that the existing DevLoop could not be read.
- [ ] T6. `internal/api`: audit assertions — `already_running` yields one
  `dev-loop-start` entry with `outcome=already_running` and a non-start
  message; `started` yields `outcome=started`.
- [ ] T7. `internal/api`: unchanged branches still hold — nil
  `TemporalClient` -> 503, non-admin -> 403, empty `issue_url` -> 400,
  malformed `issue_url` -> 400 with no Temporal call.
- [ ] T8. `internal/api`: the whole of
  `handlers_roadmap_wave_test.go` passes unedited after task 6.
- [ ] T9. `internal/mcp`: with `use_temporal:true` the tool posts
  `{"issue_url":...}` (no other keys) to `/api/v1/agents/dev-loop/start` and
  returns the body, including `started`/`outcome`, as tool text.

## Rollback

Every change is additive to mctl-api and carries no persisted state — no
migration, no gitops write, no Helm value — so rollback is a single revert of
the PR followed by the normal release: `mctl_rollback_service(team=platform,
component=mctl-api, target_tag=<previous>)`, or a `git revert` plus the
auto-deploy on push to main. The pre-revert behaviour returns immediately: the
`REJECT_DUPLICATE`/`USE_EXISTING` policies on `StartDevLoopWorkflow` are never
modified, and no execution is terminated or restarted by this change, so no
execution started under the new code behaves differently under the old.
