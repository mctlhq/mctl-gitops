# dev-loop abandon: deferred P3 follow-ups from the #450 review

## Context
Issue #454 lists three non-blocking P3 findings from the final review of #450, the PR that shipped
`POST /api/v1/agents/dev-loop/{workflow_id}/abandon` in 4.61.0. All three are in
`internal/api/handlers_dev_loop.go`:

1. When the abandon signal is delivered, the `succeeded` audit entry records `abandoned_by` and
   `reason` but not the run ID that was signalled. Commit 238cdad pinned the signal to the
   described run, so the audit entry should name that run too.
2. The comment in `GetDevLoopWorkflow` quotes the old code using the new `devLoopStatusRunning`
   name. The code beneath it still compares against a bare `"Unknown"` string even though the
   `devLoopStatusUnknown` constant exists.
3. If DevLoopWorkflow ever continues-as-new, abandon returns a 409 "replaced by a new run". That
   outcome is correct, but nothing in the code says so. The signal call also has no deadline of
   its own, which is the same as approve. Both facts should be documented in comments so an
   operator does not go looking for a restart.

The changes are small and lower the cost of operating and auditing the abandon path. Apart from
the audit entry, behaviour does not change.

## User stories
- AS a platform operator reading the audit log I WANT a signalled abandon entry to name the
  Temporal run it was delivered to SO THAT I can tie the audit record to the exact run that
  ended, without matching on timestamps.
- AS a maintainer of `handlers_dev_loop.go` I WANT status comparisons to use the named constants
  and comments to quote real code SO THAT the code and its explanation do not drift apart.
- AS an operator who receives a 409 from abandon I WANT the code to explain that a
  continue-as-new run produces this answer on purpose SO THAT I re-issue the request instead of
  hunting for an unexpected restart.

## Acceptance criteria (EARS)
- WHEN `AbandonDevLoopWorkflow` successfully delivers the abandon signal to a Running execution
  THE SYSTEM SHALL write exactly one `dev-loop-abandon` audit entry with `Status: "succeeded"`.
  Its `Parameters` SHALL contain `abandoned_by`, `reason` and `run_id`, where `run_id` equals the
  `RunID` passed to `SignalAbandon`. Its `Message` SHALL name that run.
- WHEN the abandon signal is delivered THE SYSTEM SHALL keep the HTTP response body exactly as
  it is today (`workflow_id`, `run_id`, `status`, `outcome: "signalled"`, `signalled: "abandon"`,
  `message`).
- WHILE the abandon request ends on any path other than a delivered signal (already finished,
  404, 409, 502) THE SYSTEM SHALL keep its audit parameters, messages and HTTP responses
  unchanged.
- WHEN `GetDevLoopWorkflow` derives `shepherd_in_loop_known` THE SYSTEM SHALL compare `status`
  against `devLoopStatusUnknown` rather than the literal `"Unknown"`, and SHALL return the same
  values as today for every status.
- THE SYSTEM SHALL write the old expression quoted in the `shepherd_in_loop_known` comment as
  the literal `status == "Running"`, which is the code as it was historically written, not under
  the renamed constant.
- THE SYSTEM SHALL document, in a comment on the 409 branch of `AbandonDevLoopWorkflow`, that a
  DevLoopWorkflow continue-as-new also leads to this branch, that the 409 is the intended
  outcome, and that the caller only has to re-issue the request.
- THE SYSTEM SHALL document, in a comment next to the `SignalAbandon` call, that the signal has
  no deadline of its own and is bounded only by the request context, as `SignalApprove` is.

## Out of scope
- Giving `SignalAbandon` or `SignalApprove` their own `context.WithTimeout` deadline. The issue
  only notes this ("Minor ... same as approve"). Adding a deadline changes behaviour and should
  be done for both signals together in a separate change.
- Changing how continue-as-new is handled (for example, following the chain and signalling the
  new run automatically). The issue says the current outcome is correct.
- Adding `run_id` to the failed-path audit entries, and changing the `already_finished` audit
  entry, which already names the run in its `Message`.
- Any change to the MCP tool `mctl_abandon_dev_loop`, its schema, or the tool count.

## Open questions
- The issue allows the run to be recorded "as a `Message` or a `run_id` param". This proposal
  does both: a `run_id` param that can be read by machine, and a `Message` in the same form as
  the `already_finished` entry. If reviewers want only one, drop the `Message`.
- Whether the signal call should get its own deadline is deferred (see Out of scope). The
  proposal only documents the current behaviour.
