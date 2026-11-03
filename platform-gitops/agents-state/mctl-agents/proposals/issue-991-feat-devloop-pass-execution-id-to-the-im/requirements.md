# DevLoop passes execution_id to the implement run so its run token can bind (#717 S5)

## Context
Slice S5 of mctlhq/mctl-agents#717 runs the `mctl-agents-implement` CWFT with
`MCTL_RUN_TOKEN_MODE=observe`. The run-token exchange for that template needs a
non-empty `execution_id`. mctl-api refuses an empty one with
`workflow_without_execution`, and in `enforce` mode
`orchestrator/run_implementer.py::_setup_run_token` exits 2 when
`WORKFLOW_EXECUTION_ID` is empty. `DevLoopWorkflow` builds `implement_params`
in `orchestrator/temporal/workflows/dev_loop.py` (~:4194-4205) from
`service`/`slug`/`agent_*` plus `_launch_correlation()`, and never adds
`execution_id`. Today every DevLoop implement run therefore logs
`workflow_without_execution`, and would fail under `enforce`.

The investigate submit already passes the loop's execution identity
(`dispatched.execution_id` or `self._canonical_execution_id()`, ~:3605-3617).
The implement submit must use the same source. There is a complication the
issue does not mention. The canonical `we_` is ended by
`_end_canonical_execution` right after the approve flip (~:4160), before the
implementer is resolved or submitted. That method's docstring says mctl-api
"only ... mints a run token for ... a NON-TERMINAL execution". If the id is
just copied into the implement params, the exchange most likely still fails,
only with a different refusal, and the S5 acceptance would not be met. This
proposal therefore also keeps that same `we_` open until the implement run
finishes, behind one new `workflow.patched` marker.

## User stories
- AS the platform operator rolling out run tokens I WANT every DevLoop implement run to carry the loop's execution id SO THAT the S5 observe proof can show a successful exchange and revoke before anyone flips to `enforce`.
- AS an operator of long-running DevLoop executions I WANT histories recorded before this change to replay unchanged SO THAT deploying the worker cannot cause non-determinism errors.
- AS a reviewer of the S5 rollout I WANT the sweep, manual and shepherd paths left visibly without an execution id SO THAT their semantics are decided later, on evidence, and not hidden.

## Acceptance criteria (EARS)
- WHEN a DevLoopWorkflow whose history records the new marker `implement-execution-id` submits `mctl-agents-implement` THE SYSTEM SHALL include `execution_id` equal to `self._canonical_execution_id()` (the dispatched `we_` for a dispatched loop, else the loop's own ensured `we_`): the same value the investigate submit carried.
- WHILE the implement run of such a loop is in flight (including every pre-start requeue attempt in `_implement`) THE SYSTEM SHALL keep that `we_` non-terminal, and end it, once, after `_implement` returns or on any exit path.
- WHEN such a loop ends its canonical `we_` after implement THE SYSTEM SHALL end it `Succeeded` if the implement run succeeded and `Failed` otherwise (an investigator failure still ends it `Failed`, as today).
- IF the marker is recorded but no canonical execution id can be resolved (empty `_canonical_execution_id()`, for example a loop started before `canonical-approval` that reaches the implement step on new code) THEN THE SYSTEM SHALL omit the `execution_id` key, never send an empty or invented value, and log a warning naming the workflow id and the reason `no canonical execution`, the same omission rule the investigate path follows.
- WHILE an execution's history predates the marker THE SYSTEM SHALL submit exactly the implement params it submitted before, and end the canonical `we_` at the approve flip as before.
- THE SYSTEM SHALL NOT add `execution_id` to the in-loop shepherd tick (`tick_params`), to `_launch_correlation()`, to `ImplementSweepWorkflow`/`SweptImplementWorkflow`, or to any manual trigger path.
- WHEN the recorded fixture `tests/fixtures/histories/dev_loop_full.prepatch.json` (and every other recorded DevLoop history) is replayed against the new code THE SYSTEM SHALL replay without non-determinism.

## Out of scope
- `ImplementSweepWorkflow` / `SweptImplementWorkflow` (`orchestrator/temporal/workflows/implement_sweep.py` ~:167-176): they keep submitting without `execution_id`.
- Manual triggers (`mctl_trigger_implementer`, operator `argo submit`, generic `/operations/.../execute`).
- The in-loop shepherd tick, the shepherd subprocess path and `MCTL_RUN_TOKEN_MODE` on the shepherd CWFT.
- `ClaimClient` bearer, mctl-api scope/handler reconciliation, the gitops `enforce` flip, claims going live, `LIFECYCLE_ROLLOUT_MODE`.
- Any change to mctl-gitops (the implement CWFT already declares `execution_id` and maps it to `WORKFLOW_EXECUTION_ID`).

## Open questions
- Blocking-level (filed as the one clarification question): which execution should the implement run bind to, given the canonical `we_` is terminal at implement time today? This proposal defaults to (a), holding the same `we_` open through implement. The alternatives are (b) passing the already-terminal id unchanged, which is the issue's literal scope but probably refused by the exchange, and (c) opening a second execution on the same WorkItem for the implement run.
- Holding the `we_` open longer means mctl-api refuses new execution requests for that WorkItem (`execution_active`) between the flip and the end of implement. Today a resume can land in that window, and `_await_canonical_reapproval(after_flip=True)` handles it. With this change such a request is refused by mctl-api until implement ends. That is arguably correct, since the loop is still working, but it changes behaviour.
- Could not observe: the mctl-api source and deployed version (4.154.0 per the issue). Whether the exchange refuses a terminal execution is taken from the `_end_canonical_execution` docstring, not verified against mctl-api.
- The issue allows either "fail loudly" or "follow the investigate behaviour" when no execution resolves. This proposal follows investigate (omit the key) plus a warning log, so a legacy loop is not killed during `observe`. Failing the loop instead is a one-line change if preferred.
