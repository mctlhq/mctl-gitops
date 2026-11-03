# Tasks: issue-991-feat-devloop-pass-execution-id-to-the-im

- [ ] 1. Declare `IMPLEMENT_EXECUTION_PATCH = "implement-execution-id"` and
  `IMPLEMENT_EXECUTION_MISSING_ERROR_TYPE` in `orchestrator/temporal/workflows/dev_loop.py` beside
  `LAUNCH_CORRELATION_PATCH`, with a `#:` comment (purpose, #717 S5, migration by attrition); init
  `self._hold_canonical_for_implement = False` in `__init__`. — DoD: constants importable; lint passes.
- [ ] 2. (depends on 1) At the flip site (~:4157-4160) evaluate the marker once inside `if self._canonical:` and
  skip `_end_canonical_execution` when it is recorded. — DoD: pre-patch fixtures still replay; a new run
  schedules no advance at the flip.
- [ ] 3. (depends on 2) After `implement_params.update(self._launch_correlation())` (~:4205) add
  `execution_id = self._canonical_execution_id()` under the marker; raise a non-retryable `ApplicationError`
  when it is empty. Do not touch `_launch_correlation` or the shepherd tick params. — DoD: implement submit
  carries the canonical `we_`; shepherd submit unchanged.
- [ ] 4. (depends on 2) Right after `_implement` returns (~:4236), under the marker, set
  `_canonical_end_phase` from `implement_result.succeeded` and call `_end_canonical_execution`. — DoD: exactly
  one advance per loop, after the implement; exits before it still end the `we_` via `run`.
- [ ] 5. (depends on 2) Under the marker, make the after-flip re-approval bind its grant to the still-open
  canonical `we_` rather than waiting for a new execution (or, if the test in T6 shows mctl-api semantics forbid
  it, keep the existing gate and document the behaviour). — DoD: T6 passes; decision noted in the PR body.
- [ ] 6. Update docstrings of `_end_canonical_execution` and `_canonical_execution_id`, and the CHANGELOG entry
  via the normal release-please flow (feat commit). — DoD: no stale "ends right after the approve flip" text.

## Tests
- [ ] T1. In `tests/test_dev_loop_workflow.py` replace `test_neither_submit_carries_an_execution_id`: assert
  `implement_log[0]["execution_id"]` equals the loop's canonical `we_` (from the fake ensure/dispatch activity)
  and keep `assert "execution_id" not in shepherd_log[0]`. Mutation: revert task 3 -> the implement assertion
  fails; add the id in `_launch_correlation` instead -> the shepherd assertion fails.
- [ ] T2. Dispatched loop (`execution_request_id` set, fake `BoundExecution(execution_id="we_ctx_test")`):
  implement submit carries `we_ctx_test`. Mutation: use `self._executions[-1]` after a delivered resume -> fails.
- [ ] T3. Ordering: record the activity call order from `_fake_activities`; assert the canonical advance happens
  after the implement submit and not between approve and implement, with phase `Succeeded`, and `Failed` when
  the fake implement fails. Mutation: restore the flip-site end -> fails.
- [ ] T4. Requeue: a pre-start implement failure followed by success -> both submits carry the same
  `execution_id`.
- [ ] T5. Empty canonical id under the marker (fake ensure returns "") -> loop fails with
  `IMPLEMENT_EXECUTION_MISSING_ERROR_TYPE` and no implement submit is recorded. Mutation: remove the raise ->
  fails.
- [ ] T6. Resume delivered between flip and implement under the marker: the loop does not hang on
  `opened()` and the grant is requested on the canonical `we_` (or the documented fallback from task 5).
- [ ] T7. Replay: existing `tests/fixtures/histories/dev_loop_*.json` (no new marker) replay unchanged via
  `tests/test_workflow_replay.py`; add an assertion that they do not contain "implement-execution-id" so they
  keep exercising the unpatched branch. Record a new fixture (e.g. `dev_loop_implement_execution.json`, new
  scenario in `tests/replay_scenarios.py`) with the current code and assert it contains the marker and an
  implement submit with `execution_id`. Mutation: move the `patched()` call after the advance -> pre-patch
  replay raises non-determinism.
- [ ] T8. `tests/test_patch_memoization.py` still passes; full `pytest` and lint green.

## Rollback
Revert the PR and release; the worker image rollback (`services/admins/mctl-agents-worker*/values.yaml` tag
back to the previous release) is safe for loops that never reached the flip. Loops that already recorded
`implement-execution-id` would hit non-determinism on an image without the marker, so prefer a forward fix that
keeps the marker and makes the patched branch behave like the old one (end at the flip, no `execution_id`),
or let those loops finish before rolling back. The runner side needs no rollback: under `observe` a refused
exchange is only logged, and `MCTL_RUN_TOKEN_MODE` can be removed from the CWFT (mode off).
