# Tasks: issue-991-feat-devloop-pass-execution-id-to-the-im

Amended 2026-11-03. Task and test numbers 1-6 and T1-T8 keep their meaning; added items are 4a, 5 (rewritten), 7,
T9-T11 and T12. Gate: do not release or enable any of this before the Rollout gate in requirements.md holds.

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
  `_canonical_end_phase` from `implement_result.succeeded` and call `_end_canonical_execution`. This line is
  reached on success only: a failed, cancelled or timed-out implement raises `ApplicationError` out of
  `_implement` and `run`'s exception path ends the `we_` `Failed`. Only `Succeeded` or `Failed` is ever written
  (never `Error`). — DoD: exactly one advance per loop; a success ends `Succeeded` after the implement; a failure
  ends `Failed` in the exit path (T3); exits before the implement still end the `we_` via `run`.
- [ ] 4a. (depends on 4) Declare `IMPLEMENT_END_RETRY_PATCH = "implement-end-retry"` beside
  `IMPLEMENT_EXECUTION_PATCH`; evaluate it once after the post-implement end, under the hold marker only, into
  `self._retry_pending_end` (init False). In `_watch_pr`, at the top of each poll iteration, retry
  `_end_canonical_execution(self._canonical_pending_phase, retry_policy=FAST_ACTIVITY_RETRY_POLICY)` while
  `_canonical_open` and a pending phase exist; before the continue-as-new hop make a last attempt and carry
  `canonical_execution_id`, `canonical_open`, `canonical_pending_phase` as defaulted `MergeWatchResume` fields,
  rehydrated in `_resume_merge_watch` (verify first what it does with `_canonical_open` today). — DoD: T9-T11
  pass; no retry command appears for histories without the new marker.
- [ ] 5. (depends on 2) Under the marker pass `after_flip=not self._hold_canonical_for_implement` to
  `_await_canonical_reapproval` (grant on the still-open canonical `we_`, `execution_id=""`). With the mctl-api
  queue switch on no delivery reaches the loop in that window; `after_flip=True` stays only for pre-marker
  histories and the legacy `resume` signal. Do NOT implement deferred-resume behaviour here (mctl-agents#993).
  — DoD: T6 passes; the PR body states this scope.
- [ ] 6. Update docstrings of `_end_canonical_execution` and `_canonical_execution_id`, fix the stale
  `_await_canonical_reapproval` and `_launch_correlation` docstrings, and the CHANGELOG entry via the normal
  release-please flow (feat commit). — DoD: no stale "ends right after the approve flip" text; the
  `_await_canonical_reapproval` docstring no longer says a resume opens a new execution under the marker; the
  `_launch_correlation` docstring says `execution_id` is deliberately not part of it.
- [ ] 7. Rollout gate (no code): keep PR #992 in draft; do not enable `IMPLEMENT_EXECUTION_PATCH` or bump the
  worker image until mctlhq/mctl-api#931 is released with its queue switch observed ON, the mctl-agents#993
  behaviour exists and is integration-tested, and this amendment is approved with a new digest. Order: queue
  switch -> `IMPLEMENT_EXECUTION_PATCH` -> worker image bump (`EXECUTION_REQUEST_DISPATCHER` is already
  `"true"`). — DoD: gate evidence linked in the release PR.

## Tests
- [ ] T1. In `tests/test_dev_loop_workflow.py` replace `test_neither_submit_carries_an_execution_id`: assert
  `implement_log[0]["execution_id"]` equals the loop's canonical `we_` (from the fake ensure/dispatch activity)
  and keep `assert "execution_id" not in shepherd_log[0]`. Mutation: revert task 3 -> the implement assertion
  fails; add the id in `_launch_correlation` instead -> the shepherd assertion fails.
- [ ] T2. Dispatched loop (`execution_request_id` set, fake `BoundExecution(execution_id="we_ctx_test")`):
  implement submit carries `we_ctx_test`. Mutation: use `self._executions[-1]` after a delivered resume -> fails.
- [ ] T3. Ordering: record the activity call order from `_fake_activities`; assert the canonical advance happens
  after the implement submit and not between approve and implement, with phase `Succeeded` on success. For a
  failed implement the fake implement RAISES `ApplicationError` (as `_implement` does for a failed, cancelled or
  timed-out run): assert the loop raises, that exactly one advance with phase `Failed` is recorded, and that it
  is recorded by `run`'s exit path (after the raise), not by the line after `_implement`; assert no phase other
  than `Succeeded` or `Failed` is ever sent. Mutation: restore the flip-site end -> fails; end the `we_`
  `Succeeded` on the exception path -> the failure case fails.
- [ ] T4. Requeue: a pre-start implement failure followed by success -> both submits carry the same
  `execution_id`.
- [ ] T5. Empty canonical id under the marker (fake ensure returns "") -> loop fails with
  `IMPLEMENT_EXECUTION_MISSING_ERROR_TYPE` and no implement submit is recorded. Mutation: remove the raise ->
  fails.
- [ ] T6. A legacy `resume` signal delivered between flip and implement under the marker (the only way a
  delivery can occur there; with the mctl-api queue switch on the dispatcher cannot deliver): the loop does not
  hang on `opened()` and the grant is requested on the canonical `we_` (`after_flip=False`). Mutation: pass
  `after_flip=True` under the marker -> the loop waits on `opened()` and the test fails.
- [ ] T7. Replay: existing `tests/fixtures/histories/dev_loop_*.json` (no new marker) replay unchanged via
  `tests/test_workflow_replay.py`; add an assertion that they do not contain "implement-execution-id" so they
  keep exercising the unpatched branch. Record a new fixture (e.g. `dev_loop_implement_execution.json`, new
  scenario in `tests/replay_scenarios.py`) with the current code and assert it contains the marker and an
  implement submit with `execution_id`. Mutation: move the `patched()` call after the advance -> pre-patch
  replay raises non-determinism.
- [ ] T8. `tests/test_patch_memoization.py` still passes (including the new `implement-end-retry` marker); full
  `pytest` and lint green.
- [ ] T9. End-advance retried during the merge watch: the fake advance activity fails (returns no answer) for the
  post-implement end, then succeeds; the fake PR state stays OPEN for several polls. Assert the `we_` is closed
  (query `canonical_open` False) at a poll while the watch is still running, with phase `Succeeded`, and that no
  further advance is sent afterwards. Mutation: remove the retry in `_watch_pr` -> the `we_` stays open until the
  watch ends and the test fails.
- [ ] T10. Retry across a hop: the advance keeps failing until after a continue-as-new hop of the merge watch;
  assert the continued run still retries, the `we_` ends exactly once, and `MergeWatchResume` built without the
  new fields still decodes. Mutation: drop the carried fields -> the `we_` is never ended by the watch.
- [ ] T11. Replay: a history recording `implement-execution-id` but not `implement-end-retry` (record it before
  adding the marker) replays unchanged with no retry command; a new fixture records both markers and a retried
  advance. Mutation: evaluate `patched(IMPLEMENT_END_RETRY_PATCH)` unconditionally in the poll loop -> the old
  fixture raises non-determinism.
- [ ] T12. Rewriting existing tests (gate, not code): the 21 tests failing on #992
  (`test_execution_request_resume.py` 17, `test_execution_request_dispatch.py` 1,
  `test_execution_request_replay.py` 3) and `test_a_resume_delivered_after_the_implement_step_succeeds_at_once`
  are NOT edited by this slice. They are rewritten to the mctl-agents#993 contract only after that behaviour
  exists, and only after mutation-discriminating regression and end-to-end tests for it exist (a resume during
  implement delivered after Succeeded, Failed, Cancelled and timeout; stale `expected_state_version`; Temporal
  replay before and after the marker). Never fit an existing expectation to a lost request.

T-numbering note: T1-T8 are the approved numbering and keep their meaning; T9-T12 are new in this amendment.

## Rollback
Revert the PR and release; the worker image rollback (`services/admins/mctl-agents-worker*/values.yaml` tag
back to the previous release) is safe ONLY for loops that never reached the flip. A worker image rollback after
histories recorded `implement-execution-id` (or `implement-end-retry`) makes those loops fail with
non-determinism on an image without the marker, so prefer a forward fix that keeps the markers and makes the
patched branch behave like the old one (end at the flip, no `execution_id`, no retry), or let those loops finish
before rolling back. Order when backing out: first turn off the loop-side change (forward fix or image), and only
then the mctl-api queue switch; switching the queue off first re-opens the refusal window while the worker still
holds the `we_` through implement, and a rolled-back worker with the queue still on leaves queued resumes that
the older loop treats as a silent no-op. The runner side needs no rollback: under `observe` a refused
exchange is only logged, and `MCTL_RUN_TOKEN_MODE` can be removed from the CWFT (mode off).
