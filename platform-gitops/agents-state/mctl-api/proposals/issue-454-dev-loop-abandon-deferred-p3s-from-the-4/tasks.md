# Tasks: issue-454-dev-loop-abandon-deferred-p3s-from-the-4

- [ ] 1. In `internal/api/handlers_dev_loop.go` `AbandonDevLoopWorkflow`, change the signalled
  success audit entry to use a new params map
  `{"abandoned_by", "reason", "run_id": exec.RunID}` and set
  `Message: "signalled: abandon (run " + exec.RunID + ")"`. Leave `auditParams` and the HTTP
  response untouched. — DoD: the signalled audit entry names the run; all other paths emit
  identical entries.
- [ ] 2. In `GetDevLoopWorkflow`, replace `status != "Unknown"` with
  `status != devLoopStatusUnknown`. Update the comment so it quotes the current code with the
  constant, and quotes the historical expression as the literal `status == "Running"`.
  — DoD: no bare `"Unknown"` or `"Running"` comparisons remain in `handlers_dev_loop.go`
  (`grep -n '== "Running"\|!= "Unknown"'` matches only the comment quote); behaviour unchanged.
- [ ] 3. Add a comment on the `after.RunID != exec.RunID` 409 branch. It explains that a
  continue-as-new also lands there, that the 409 is the intended outcome, and that the caller
  only re-issues the request. Optionally add one sentence to the function doc comment.
  — DoD: the comment is present and accurate against `statusName`'s `"ContinuedAsNew"` arm.
- [ ] 4. Add a comment on the `SignalAbandon` call. It notes that the signal has no deadline of
  its own (only `r.Context()`), the same as `SignalApprove` in `ApproveDevLoopWorkflow`.
  — DoD: the comment is present; no code change.
- [ ] 5. (depends on 1, 2) Update the tests as listed below, then run `go fmt ./...`,
  `go vet ./...`, `golangci-lint run` and `go test ./internal/api/...`. — DoD: all pass.

## Tests
- [ ] T1. Extend `TestAbandonDevLoopWorkflow_RunningIsSignalledWithCallerAsActor`
  (`internal/api/handlers_dev_loop_abandon_test.go`) to assert
  `e.Parameters["run_id"] == "run-1"` and `strings.Contains(e.Message, "run-1")`, and to keep
  the existing `abandoned_by` and `reason` assertions.
- [ ] T2. In `TestAbandonDevLoopWorkflow_FinishedExecutionIsReportedNotSignalled`, assert that
  the audit entry has no `run_id` parameter (the shared map was not mutated).
- [ ] T3. In `TestAbandonDevLoopWorkflow_SignalNotFoundIsAnsweredFromASecondDescribe`
  (the 409 / new-run case), assert that the failed audit entry has no `run_id` parameter and
  that its message is unchanged.
- [ ] T4. A `GetDevLoopWorkflow` table test: describe status `"Unknown"` gives
  `shepherd_in_loop_known=false`; `"Completed"` gives `true`; `"Running"` with a successful
  query gives `true`. Extend the existing test if one already covers this.

## Rollback
Revert the single commit. The change is limited to one audit entry's params and message, a
constant swap that does not change behaviour, and comments. There is no state, schema, or
config to unwind. Audit entries already written with `run_id` stay valid, because
`Parameters` is a free-form string map.
