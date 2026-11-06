# DevLoop passes its canonical execution_id to the implement run (#717 S5)

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
- WHEN `_implement` returns under the marker, THE SYSTEM SHALL end the canonical execution once, in `Succeeded`
  if the implement result succeeded and `Failed` otherwise, before the abandon check and the merge watch.
- IF the loop exits between the flip and the end of the implement run (abandon, re-approval expiry, release
  resolution failure, exception, cancellation), THEN THE SYSTEM SHALL still end the canonical execution through
  the existing exit paths in `run` (`_canonical_pending_phase` / `_canonical_end_phase` / "Failed").
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
- Any gitops change: `cwft-mctl-agents-implement.yaml` already declares `execution_id` and maps it to
  `WORKFLOW_EXECUTION_ID`.

## Open questions
- After-flip resume semantics. Holding the canonical `we_` open past the flip means mctl-api's attach rule
  (`execution_active`) refuses a new resume execution until the implement run ends, so the after-flip re-approval
  gate (`_await_canonical_reapproval(..., after_flip=True)`, which waits for a NEW execution to be opened) can no
  longer be satisfied by a resume in that window. Proposed interpretation: under the marker the after-flip gate
  binds a fresh grant to the still-open canonical `we_` (the pre-flip behaviour, `execution_id=""`) instead of
  waiting for a new execution. The implementer must confirm this with a test; if mctl-api refuses a second
  `aar_` on that `we_`, record it and keep the existing gate (a resume then simply waits for the implement end).
- Usage attribution: `test_neither_submit_carries_an_execution_id` documents an earlier decision that an
  implementer invocation is not the investigator's `we_` ("would misattribute spend"). The resolved answer
  overrides it for the implement submit; the usage ledger does not read `WORKFLOW_EXECUTION_ID`
  (`orchestrator/usage_ledger.py::_CORRELATION_ENV`), so no spend changes attribution, but reviewers should
  confirm.
