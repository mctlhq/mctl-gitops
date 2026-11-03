# Design: issue-991-feat-devloop-pass-execution-id-to-the-im

## Current state

All paths are in the mctl-agents clone unless stated otherwise.

- `orchestrator/temporal/workflows/dev_loop.py`
  - `_canonical_execution_id()` (~:2391) returns `self._canonical_execution`. That is the dispatched `we_` (~:3553, `self._canonical_execution = dispatched.execution_id`) or the one `_ensure_canonical_execution` attached (~:3301-3343, which also sets `self._canonical_open = True`).
  - Investigate submit (~:3605-3617): when `dispatched is not None or self._canonical_open`, sets `investigate_params["work_item_id"]` and `investigate_params["execution_id"] = dispatched.execution_id if dispatched is not None else self._canonical_execution_id()`. Otherwise the keys are omitted. No marker is used there, because activity input is not compared on replay (`tests/test_workflow_replay.py`).
  - `_end_canonical_execution(phase)` (~:3488-3506): a no-op unless `_canonical_open`. Its docstring says the `we_` is "Held non-terminal from the start through the approval because mctl-api only binds an `aar_` to, mints a run token for, and resolves an approve to a NON-TERMINAL execution; it ends right after the approve flip". When the advance does not land it records `_canonical_pending_phase`.
  - After the flip (~:4157-4160): `if self._canonical: await self._end_canonical_execution(self._canonical_end_phase or "Failed")`. `_canonical_end_phase` is set from the investigator result (~:3659-3662). So by the time the implementer is resolved, the `we_` is already terminal.
  - `implement_params` (~:4194-4205): `service`, `slug`, `agent_image`, `agent_version`, then `implement_params.update(self._launch_correlation())`.
  - `_launch_correlation()` (~:4586-4607), gated by `LAUNCH_CORRELATION_PATCH = "launch-correlation"` (~:466): `temporal_workflow_id`, `temporal_run_id`, and `work_item_id` when set. It is also used by the in-loop shepherd tick (~:4971).
  - `self._implement(...)` (~:4235) submits, with pre-start requeues reusing the same params. It is followed by the abandon check, `_watch_pr` (which may `continue_as_new`), and `_finish_after_watch`.
  - `run` (~:3460-3486) ends a still-open canonical `we_` on every exit, normal or exceptional, with `_canonical_pending_phase or _canonical_end_phase or "Failed"`.
- `orchestrator/run_implementer.py` `_setup_run_token` (~:6016): in `enforce`, it refuses an empty `WORKFLOW_EXECUTION_ID` (`EXECUTION_ID_ENV`, ~:6013) and exits 2. In `observe`, `run_token.setup` only logs a failed exchange (`orchestrator/run_token.py` module docstring). `run_token.revoke` notes that a token "ends with its run, by expiry or its execution turning terminal".
- `orchestrator/usage_ledger.py` `_CORRELATION_ENV` (~:178) does not read `WORKFLOW_EXECUTION_ID`. Adding the parameter does not change usage attribution.
- Tests:
  - `tests/test_dev_loop_workflow.py::test_neither_submit_carries_an_execution_id` (~:5409-5446) asserts that neither the implement submit nor the shepherd submit carries `execution_id`. `_fake_activities(implement_params_log=..., shepherd_params_log=...)` (~:391, 495-502) captures the params.
  - `tests/test_workflow_replay.py::test_todays_dev_loop_full_carries_the_launch_correlation_marker` (~:383-428) asserts `"execution_id" not in params` for the implement submits of a live recording. `test_dev_loop_full_prepatch_history_predates_the_launch_correlation_marker` (~:346) shows the "predates the marker" fixture-check pattern. `test_recorded_history_replays_against_current_definitions` (~:143) replays every fixture in `tests/fixtures/histories/` (`dev_loop_full.prepatch.json`, `dev_loop_full.patched.json`, `dev_loop_dispatched.json`, `dev_loop_issue_keyed.json`, and others), listed in `tests/replay_scenarios.py`.
  - `tests/test_patch_memoization.py` documents that `patched()` is memoised per id.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`: declares `execution_id` (default `""`, ~:129) and maps it to `WORKFLOW_EXECUTION_ID: "{{workflow.parameters.execution_id}}"` (~:848). It sets `MCTL_RUN_TOKEN_MODE: observe` (~:785) and the default image `ghcr.io/mctlhq/mctl-agents:1.117.0` (~:108). No gitops change is needed.
- `$MCTL_GITOPS_ROOT/services/`: only tenant directories (`admins`, `karabu`, `labs`, `namax66`), with no `mctl-api` values file. The deployed mctl-api version (4.154.0 per the issue) and its exchange rules for a terminal execution could not be observed. No mctl MCP call was made, because the gitops checkout already answered the CWFT question.
- Live Workflows `mctl-agents-implement-21260455` / `-55052262` (cited by the issue) were not inspected from this run.

## Proposed solution

One new marker, `IMPLEMENT_EXECUTION_ID_PATCH = "implement-execution-id"`. It is defined next to `LAUNCH_CORRELATION_PATCH` with a comment citing #991, #717 S5 and the CWFT parameter. It is evaluated exactly once, at the approve-flip site, before `_end_canonical_execution` would run, and its result is stored in `self._implement_holds_execution: bool` (initialised `False` in `__init__`).

1. Defer the end of the canonical `we_` (~:4157-4160):
   ```python
   if self._canonical:
       self._implement_holds_execution = workflow.patched(IMPLEMENT_EXECUTION_ID_PATCH)
       if not self._implement_holds_execution:
           await self._end_canonical_execution(self._canonical_end_phase or "Failed")
   ```
   Pre-patch histories (no marker) keep ending the `we_` here, with the identical command sequence. A patched loop keeps `_canonical_open` True. Every exit path in between (registry resolve failure, abandon during the re-approval park, deadline, exception) still ends it through `run`'s existing handling, with the investigator's `_canonical_end_phase`.

2. Add the id to `implement_params` only (not to `_launch_correlation`, so the shepherd tick is unchanged), right after `implement_params.update(self._launch_correlation())`:
   ```python
   if self._implement_holds_execution:
       execution_id = self._canonical_execution_id()
       if execution_id:
           implement_params["execution_id"] = execution_id
       else:
           workflow.logger.warning(
               "implement submit for %s carries no execution_id: no canonical execution",
               workflow.info().workflow_id,
           )
   ```
   The source is the same as investigate's: `_canonical_execution` already is `dispatched.execution_id` for a dispatched canonical loop. No value is minted. Adding an activity argument needs no marker of its own, but it is placed under this marker anyway so the param and the held execution can never disagree.

3. End the `we_` with the implement result, immediately after `implement_result = await self._implement(...)` and before the abandon check, the merge watch and any `continue_as_new`:
   ```python
   if self._implement_holds_execution:
       self._canonical_end_phase = "Succeeded" if implement_result.succeeded else "Failed"
       await self._end_canonical_execution(self._canonical_end_phase)
   ```
   If the advance does not land, `_canonical_pending_phase` is set, and `run`'s exit retries it as today. Ending before `_watch_pr` means no hop needs to carry an open execution in `MergeWatchResume`. If `_implement` raises, `run`'s `except` ends it `Failed`.

4. Tests and docs (see tasks.md). Flip only the implement half of `test_neither_submit_carries_an_execution_id`, and keep the shepherd half asserting absence. Update the live-recording assertion in `test_workflow_replay.py`. Add a "predates the marker" check on the prepatch fixture and a replay test. Update the comments at ~:4200-4205 and the `_end_canonical_execution` docstring ("ends after the implement run, or right after the approve flip for a history that predates `implement-execution-id`").

Why this shape: it is the smallest change that hands the implementer an id from the issue's required source and also lets the run-token exchange succeed. Without step 1 the parameter would name a terminal execution.

## Alternatives

- **(b) Add `execution_id` only and leave the end at the flip.** This is the literal issue scope, and the diff is one line plus a marker. Dropped as the default because, per `_end_canonical_execution`'s own docstring, mctl-api does not mint run tokens for a terminal execution. The observe proof would just trade `workflow_without_execution` for another refusal. If the reviewer picks this in the clarification answer, drop steps 1 and 3; the tests in tasks.md shrink to the param assertions.
- **(c) Attach a second execution to the WorkItem for the implement run** (a new `ensure_issue_execution`-style activity with an implement-specific engine ref). This gives cleaner per-invocation attribution, and matches T4's original rationale ("an implementer ... invocation is not the investigator's `we_`"). Dropped because the issue explicitly says to use the investigate source and never a new value, and because it needs a new activity, new mctl-api semantics for a second execution per loop run, and new failure modes.
- **Put `execution_id` in `_launch_correlation()`.** Dropped: that also changes the shepherd tick, which is explicitly out of scope, and it would reuse `launch-correlation`, a marker existing histories have already recorded.

## Platform impact

- Migrations: none, and no gitops change (the CWFT already declares and maps the parameter).
- Backward compatibility and replay: every behavioural change is behind `implement-execution-id`. Histories without it (all current fixtures, and in-flight loops already past the flip) replay unchanged. A loop that is still running and reaches the flip on new code records the marker and takes the new path. That is safe because nothing before the flip changes.
- Behaviour change: between the approve flip and the end of the implement run (typically 1-10 minutes, bounded by `_implement`'s timeouts), the WorkItem now has a non-terminal execution. mctl-api answers `execution_active` to a new execution request for that item during that window, where today it would accept a resume. `_await_canonical_reapproval(after_flip=True)` stays reachable for a signal-delivered resume, but a surface-created request is refused by mctl-api until implement ends. This is recorded under Open questions.
- Resource impact: one more `advance` activity is not added. The same single advance just moves later.
- Risks and mitigations:
  - The exchange may also need something else (scope or handler reconciliation, explicitly a later slice). Under `observe` that is only logged, and the S5 proof run shows it.
  - The `we_` could be left open if the worker dies mid-implement. That is mitigated by Temporal durability: `run`'s exit handling still runs on the resumed worker, and the dispatcher reconciles the own `we_` of a closed loop (existing comment ~:3469-3471).
  - In `enforce` (a later slice), a legacy loop with no canonical id would still fail at the pod. This is deliberate and logged by the warning.
