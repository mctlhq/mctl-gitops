# Design: issue-454-dev-loop-abandon-deferred-p3s-from-the-4

## Current state
All three findings are in `internal/api/handlers_dev_loop.go` (clone at `bec4909`).

**Abandon handler (`AbandonDevLoopWorkflow`, ~lines 433-573).**
- `auditParams := map[string]string{"abandoned_by": user.ID, "reason": reason}` is built once
  and shared by the `fail` closure, the `finished` closure and the success entry.
- The `finished` closure already names the run in its `Message`:
  `"not signalled: already finished (run " + exec.RunID + ", status " + exec.Status + ")"`.
- After `describe("workflow not found")` returns a Running execution, the handler calls
  `h.opts.TemporalClient.SignalAbandon(r.Context(), workflowID, exec.RunID, payload)`. That call
  is pinned to the described run (`internal/temporalclient/client.go`, `SignalAbandon` passes
  `runID` to `SignalWorkflow`).
- Unlike the describe calls, the signal uses `r.Context()` directly with no
  `context.WithTimeout`. The describe calls use `devLoopDescribeTimeout`, a 10s constant at
  line 44.
- `ApproveDevLoopWorkflow` (~line 356) calls `SignalApprove(r.Context(), ...)` the same way,
  with no deadline of its own.
- If the signal answers NotFound, a second describe runs. If that describe shows a Running
  execution with a different `RunID`, the handler returns 409 with "a new run ... is running
  under the same workflow id; it was not abandoned. Re-issue the request" (~lines 540-548).
  Continue-as-new is one of the ways to reach this point. `DescribeWorkflowExecution(ctx, id, "")`
  resolves to the latest run, so the closed predecessor (`statusName` maps it to
  `"ContinuedAsNew"`) is never the run seen there. The code never states this.
- The success audit entry (~lines 557-564) has `Parameters: auditParams`, no `Message`, and no
  run ID. The HTTP response does include `"run_id": exec.RunID`.

**Liveness read (`GetDevLoopWorkflow`, ~lines 580-650).**
- Line 627 comment: "`status != "Unknown"` rather than an unconditional true ...".
- Lines 630-632 comment: "The old `status == devLoopStatusRunning` covered that case by
  accident". This quotes historical code using the constant name, which did not exist when that
  code was written.
- Line 633: `shepherdInLoopKnown := status != "Unknown"`. Line 634 already uses
  `status == devLoopStatusRunning`.
- Both constants are defined in `internal/api/handlers_lifecycle_conflict.go:199-204`
  (`devLoopStatusUnknown = "Unknown"`, `devLoopStatusRunning = "Running"`) and are already used
  at line 508 and line 522 of the abandon handler.

**Tests.** `internal/api/handlers_dev_loop_abandon_test.go`
`TestAbandonDevLoopWorkflow_RunningIsSignalledWithCallerAsActor` checks the success audit
entry's `Operation`, `Status`, `WorkflowName`, `abandoned_by` and `reason`, but not the run. It
uses `fakeDevLoopClient{describeExec: {Status: "Running", RunID: "run-1"}}` and
`audit.NewLogger()` / `logger.List(10)`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/`: lists tenants `admins`, `karabu`, `labs` and `ovk`. No
  `services/*/mctl-api/values.yaml` exists in this checkout, so the deployed config of mctl-api
  could not be observed there. This change touches only handler code paths and comments; it
  adds no env vars, config or resources, so no deployed setting is relied on.
- No mctl MCP tools were called. The change has no dependency on runtime configuration.

## Proposed solution
The work is three edits to one file, plus a test update.

1. **Run ID on the signalled audit entry.** In the success path after `SignalAbandon` returns
   nil, build a copy of `auditParams` with `run_id` added, and set a `Message`:
   ```go
   signalledParams := map[string]string{
       "abandoned_by": user.ID, "reason": reason, "run_id": exec.RunID,
   }
   h.logAudit(r, audit.Entry{
       ... Parameters: signalledParams,
       Status: "succeeded",
       Message: "signalled: abandon (run " + exec.RunID + ")",
   })
   ```
   A fresh map, rather than mutating `auditParams`, keeps the other paths byte-for-byte
   unchanged. The `Message` uses the same format as the `finished` entry, so both `succeeded`
   outcomes read the same way in the log. The HTTP response is untouched.

2. **Use the constants and fix the quote.** Change line 633 to
   `shepherdInLoopKnown := status != devLoopStatusUnknown`. Change the line 627 comment to quote
   the current code (`status != devLoopStatusUnknown`) and say that it is the `"Unknown"` default
   arm of `statusName`. Change the line 631 quote back to the historical literal:
   ``The old `status == "Running"` covered that case by accident``. No behaviour changes,
   because the constant's value is `"Unknown"`.

3. **Comments on the 409 branch and the signal deadline.**
   - On the `after.RunID != exec.RunID` branch, add a comment. It explains that a DevLoopWorkflow
     continue-as-new also lands here: the pinned run closes as `ContinuedAsNew`, its successor
     is Running under the same workflow id, and the second describe sees the successor. The 409
     is the intended answer (the run the caller looked at was not the one signalled). The
     caller only re-issues the request, and the 409 is not evidence of an unexpected restart.
   - On the `SignalAbandon` call, add a comment. It says the signal has no deadline of its own
     and is bounded by the request context, the same as `SignalApprove` in
     `ApproveDevLoopWorkflow`, and that any change should be made to both signals together.
   - Optionally add one sentence to the function doc comment (lines 427-432) mentioning the
     continue-as-new case.

4. **Tests.** Extend `TestAbandonDevLoopWorkflow_RunningIsSignalledWithCallerAsActor` to assert
   `e.Parameters["run_id"] == "run-1"` and that `e.Message` contains `run-1`. Add assertions
   that the `finished` and 409 entries have no `run_id` param, which proves the shared map was
   not mutated. Add or extend a `GetDevLoopWorkflow` test showing that
   `shepherd_in_loop_known` is false for `"Unknown"` and true for `"Completed"`, if no such test
   exists yet.

## Alternatives
- **Add `run_id` to `auditParams` at creation time (all paths).** Dropped. On the 409 and
  NotFound paths more than one run is involved, and a single `run_id` would be ambiguous. Those
  messages already name the runs. The issue scopes the gap to the signalled path.
- **Message only, no param.** Workable, but a param can be filtered on in the audit store
  without parsing text. The issue allows either, so the proposal uses both.
- **Give the signal its own `context.WithTimeout` now.** Dropped from this proposal. The issue
  marks it "minor, same as approve", and fixing one signal but not the other would create the
  kind of inconsistency this issue is cleaning up. It is listed as a follow-up.

## Platform impact
- No migrations, config, env vars, routes, or MCP tool changes. `server_test.go`'s tool count
  is unaffected.
- Backward compatibility: the audit entry gains one parameter key and a `Message`. Consumers of
  `audit.Entry.Parameters` read it as a `map[string]string`, so an extra key is additive. The
  HTTP API contract is unchanged.
- Risk: accidentally changing audit params on other paths. Mitigation: use a separate map, and
  add tests asserting the other paths do not carry `run_id`.
- Resource impact: none.
