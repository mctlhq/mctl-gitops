# DevLoop passes its canonical execution_id to the implement run (#717 S5)

## Amendment 2026-11-03
This amendment supersedes the version approved earlier on 2026-11-03 (grant `aar_9a49222610984cfc86599faffdae5c25`).
It needs a fresh approval and a new content digest. What changed and why:
- Facts corrected (found while reviewing PR mctl-agents#992 against mctl-agents#993): the loop only ever writes
  `Succeeded` or `Failed` to a `we_`, never `Error` (mctl-api's orphan sweeper, mctlhq/mctl-api#931, is the only
  writer of `Error`). Under #992 a failed, cancelled or timed-out implement raises out of `_implement`, so
  `run`'s exception path ends the `we_` `Failed`; the `Succeeded if ... else Failed` line after `_implement` is
  reachable on success only. Cancel and Timeout are indistinguishable from Failed to mctl-api.
- New requirement (owner decision 7 on mctl-agents#993): a pending end-advance of the canonical `we_` after the
  implement run is retried during the merge watch, so an open `we_` cannot block queued requests for up to 14 days.
- The "after-flip resume semantics" open question is resolved. With the mctl-api queue switch on
  (mctlhq/mctl-api#931) a resume made while the `we_` is open is stored `pending` and is not claimable until the
  `we_` closes, so no delivery reaches the loop between the flip and the end of implement. What a deferred resume
  does after the `we_` closes is NOT defined here: it is the deferred-resume contract of mctl-agents#993, which
  gets its own proposal and is only referenced from this one.
- Deployed state: `EXECUTION_REQUEST_DISPATCHER: "true"` is already set in production
  (`platform-gitops/services/admins/mctl-agents-worker/values.yaml:139`, commit f1fc08233), so the dispatcher is
  not a rollout switch. The gates are the mctl-api queue switch, `IMPLEMENT_EXECUTION_PATCH` and the worker image
  bump, in that order (see Rollout gate).
- Explicit rollout gate, test-order rule, rollback ordering and a corrected docstring task were added.
Everything else, including the empty-canonical-id rule, is unchanged.

## Context
Slice S5 of #717 runs `mctl-agents-implement` with `MCTL_RUN_TOKEN_MODE=observe`. The run-token exchange
for that template is bound to an execution: mctl-api refuses an empty `execution_id` with
`workflow_without_execution`, and `orchestrator/run_implementer.py::_setup_run_token` exits 2 under `enforce`
when `WORKFLOW_EXECUTION_ID` is empty. Today `DevLoopWorkflow` builds `implement_params`
(`orchestrator/temporal/workflows/dev_loop.py`, ~:4194-4205) with `service`, `slug`, agent image/version and
`_launch_correlation()` (`temporal_workflow_id`, `temporal_run_id`, `work_item_id`), but never `execution_id`.

A second gap makes simply adding the id insufficient: the loop's canonical `we_` is ended right after the
approve flip (`_end_canonical_execution` at ~:4160), before the implement submit, and mctl-api only mints run
tokens for a NON-TERMINAL execution. The issue author resolved this (clarification hir-42a9712465540dc5,
option a): the implement run names the SAME canonical `we_`, which is kept non-terminal until the implement run
finishes. This proposal implements both halves behind one new `workflow.patched` marker so histories recorded
before it replay unchanged.

## User stories
- AS the platform operator I WANT every DevLoop implement run to carry the loop's canonical execution id SO THAT
  its run-token exchange binds and S5 can be proven in `observe` before `enforce` is planned.
- AS the platform operator I WANT the canonical execution to stay non-terminal until the implement run ends SO
  THAT mctl-api accepts the exchange for the whole implement run.
- AS a maintainer of running DevLoops I WANT pre-patch histories to keep their recorded command sequence SO THAT
  a worker deploy causes no non-determinism errors.

## Acceptance criteria (EARS)
- WHEN a DevLoop new enough to record the new marker (`IMPLEMENT_EXECUTION_PATCH`, "implement-execution-id")
  and `CANONICAL_APPROVAL_PATCH` submits `mctl-agents-implement`, THE SYSTEM SHALL include
  `execution_id = self._canonical_execution_id()` in the submitted parameters (for a dispatched loop this equals
  `dispatched.execution_id`, the same source the investigate submit uses at ~:3614-3617).
- WHEN `_implement` requeues a pre-start failure, THE SYSTEM SHALL resubmit with the same `execution_id`.
- WHILE the marker is recorded, THE SYSTEM SHALL NOT end the canonical execution at the approve flip, and SHALL
  keep it non-terminal from the flip until `_implement` returns.
- WHEN `_implement` returns under the marker, THE SYSTEM SHALL end the canonical execution once, in `Succeeded`,
  before the abandon check and the merge watch. (`_implement` returns only for a succeeded run; the
  `Succeeded if implement_result.succeeded else Failed` expression is kept as a defensive guard and is not the
  path that records a failed implement.)
- IF `_implement` raises (a failed, cancelled or timed-out implement run, or a non-retryable error), THEN THE
  SYSTEM SHALL end the canonical execution `Failed` from `run`'s exception path, and SHALL NOT end it from the
  line after `_implement`. THE SYSTEM SHALL only ever write `Succeeded` or `Failed` to the `we_`; `Error` belongs
  to mctl-api's orphan sweeper.
- IF the loop exits between the flip and the end of the implement run (abandon, re-approval expiry, release
  resolution failure, exception, cancellation), THEN THE SYSTEM SHALL still end the canonical execution through
  the existing exit paths in `run` (`_canonical_pending_phase` / `_canonical_end_phase` / "Failed").
- IF the post-implement end-advance does not land (the `we_` is still open and `_canonical_pending_phase` is set),
  THEN THE SYSTEM SHALL retry it on every merge-watch poll, with its own marker `IMPLEMENT_END_RETRY_PATCH`
  ("implement-end-retry"), not only at loop exit, and SHALL stop retrying as soon as it lands.
- WHILE the merge watch hops via continue-as-new, THE SYSTEM SHALL NOT drop an end-advance that has not landed:
  it SHALL make a last attempt before the hop and, if it still has not landed, carry the pending phase and the
  open `we_` identity into the continued run, which keeps retrying.
- WHILE a history records `IMPLEMENT_EXECUTION_PATCH` but not `IMPLEMENT_END_RETRY_PATCH`, THE SYSTEM SHALL
  replay it with no retry command in the merge watch.
- WHILE the marker is recorded, THE SYSTEM SHALL bind the re-approval gate between the flip and the implement
  submit with `after_flip=False` (grant on the canonical `we_`, `execution_id=""`); `after_flip=True` is kept
  only for histories without the marker and for a legacy `resume` signal (no sender in production).
- IF the marker is recorded and the canonical execution id resolves empty at the implement submit, THEN THE
  SYSTEM SHALL fail the loop with a non-retryable `ApplicationError` naming the missing execution, and SHALL NOT
  submit `mctl-agents-implement` without one.
- WHILE a history predates the marker, THE SYSTEM SHALL replay it with the old command sequence: canonical end at
  the flip, implement submitted without `execution_id`.
- WHILE the in-loop shepherd tick runs, THE SYSTEM SHALL keep submitting it without `execution_id` (the
  `_launch_correlation()` result is unchanged; the id is added only to `implement_params`).
- WHEN the change is deployed and the first real DevLoop implement runs, THE SYSTEM SHALL produce an Argo
  Workflow with `workflowTemplateRef.name=mctl-agents-implement`, `clusterScope: true`, a non-empty
  `execution_id` argument, and a run-token exchange and revoke with no `workflow_without_execution`.

## Out of scope
- `ImplementSweepWorkflow` / `SweptImplementWorkflow` (`implement_sweep.py` ~:167-176): keeps submitting without
  `execution_id`; stays documented as unresolved.
- Manual triggers (`mctl_trigger_implementer`, operator `argo submit`, generic `/operations/.../execute`).
- The in-loop shepherd tick, the shepherd subprocess path and `MCTL_RUN_TOKEN_MODE` on the shepherd CWFT.
- `ClaimClient` bearer, mctl-api scope/handler reconciliation, the gitops `enforce` flip, claims going live,
  `LIFECYCLE_ROLLOUT_MODE`.
- Any gitops change to the CWFT: `cwft-mctl-agents-implement.yaml` already declares `execution_id` and maps it to
  `WORKFLOW_EXECUTION_ID`.
- The deferred-resume contract (what a queued resume does after the `we_` closes) and orphaned-execution recovery:
  mctl-agents#993, own proposal.

## Rollout gate
- PR mctl-agents#992 stays in draft, and `IMPLEMENT_EXECUTION_PATCH` must not run in production, until ALL of:
  1. mctlhq/mctl-api#931 is released with its queue switch ON, and that is observed (not assumed);
  2. the deferred-resume behaviour of mctl-agents#993 exists and its integration tests pass;
  3. this amendment is approved with a new content digest.
- Order: the mctl-api queue switch, then the worker image bump that carries `IMPLEMENT_EXECUTION_PATCH`. The
  dispatcher is already on (`EXECUTION_REQUEST_DISPATCHER: "true"`), so it is not a step.
- Failure modes the order prevents: (a) a #992 worker with an old mctl-api (queue switch off) widens the window in
  which an execution request is refused and dropped from "investigate to approval" to the whole implement run;
  (b) a new mctl-api (switch on) with a worker that predates #993 delivers queued resumes into a loop whose
  `_deliver` lands `Succeeded` with no work done (a silent no-op).
- Test order: mutation-discriminating regression and end-to-end tests for the new behaviour MUST exist before any
  existing expectation is rewritten. The 21 tests that fail on #992 (`test_execution_request_resume.py` 17,
  `test_execution_request_dispatch.py` 1, `test_execution_request_replay.py` 3) are rewritten to the #993 contract
  only after that behaviour exists, never fitted to a lost request.

## Open questions
- Resolved (was: after-flip resume semantics). With the queue switch on, a resume made while the canonical `we_`
  is open is stored `pending` by mctl-api and is not claimable until the `we_` closes, so no delivery reaches the
  loop between the flip and the end of implement. `after_flip=False` is therefore used under the marker, and
  `after_flip=True` remains only for the legacy `resume` signal. mctl-api verifies the second-grant behaviour with
  `TestDevLoopApprove_SecondGrantOnOpenExecutionAfterFlip` (mctlhq/mctl-api#931). What a deferred resume does
  once the `we_` has closed (merge watch with open PR, merged PR, failed/cancelled/timed-out implement,
  intent-less resume) is defined by mctl-agents#993 and gets its own proposal; releasing or enabling #992 is
  gated on it.
- Usage attribution: `test_neither_submit_carries_an_execution_id` documents an earlier decision that an
  implementer invocation is not the investigator's `we_` ("would misattribute spend"). The resolved answer
  overrides it for the implement submit; the usage ledger does not read `WORKFLOW_EXECUTION_ID`
  (`orchestrator/usage_ledger.py::_CORRELATION_ENV`), so no spend changes attribution, but reviewers should
  confirm.
