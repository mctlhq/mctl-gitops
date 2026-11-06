# Tasks: issue-1021-devloop-part-m-m2b-feedback-tick-and-dea

Execution slice of #993 (umbrella digest
`sha256:1e461962bc774bc5ed7f129c6a78378720a79beb97e601d2ca26985d3109742b`, provenance only). Commit order is
evidence: every `test:` commit lands before the `feat:`/`fix:` commit that turns it green, and the PR description
lists the pairs. Task D (deadline-in-gap) is the acceptance gate and goes first; tasks 5-7 do not start until D's
tests are green with mutation evidence.

## Deadline-in-gap (gate)

- [ ] D0. Gap harness: a helper in `tests/temporal_harness.py` (or `tests/test_merge_watch_final_read.py`) that runs a
  real `DevLoopWorkflow` in `WorkflowEnvironment.start_time_skipping()`, stops the worker, flips the fake
  `get_pr_state` to the scripted post-gap answer, `env.sleep`s past `MERGE_WATCH_DEADLINE`, then starts a fresh worker
  on the same task queue and awaits the result; records every activity call and every lifecycle op in order - DoD:
  helper committed with D1-D4 tests, which fail on current `main` for the right reason (result `pr.state == "OPEN"`,
  no post-deadline read), not on an import error.
- [ ] D1. Tests first (commit): T-D1..T-D9 below, all red on `main` - DoD: one `test:` commit, CI log of the red run
  linked in the PR.
- [ ] D2. `MERGE_WATCH_FINAL_READ_PATCH`, `MergeWatchResume.final_read`, evaluated only in `_watch_pr`'s fresh-start
  arm, written into the hop record, read from `resume.final_read` in the resume arm (depends on D1) - DoD: T-D7 and
  T-D8 marker counts pass; existing `tests/test_patch_memoization.py` green.
- [ ] D3. `_terminal_claim` extracted from the in-loop MERGED/CLOSED branch (pure refactor, same commands) - DoD:
  every existing `_watch_pr` and replay test green with no fixture change.
- [ ] D4. `while ... else:` final read: `_final_pr_read` (`FINAL_READ_ATTEMPTS=3`, `FINAL_READ_BACKOFF=2m`,
  `found=False` and any `ActivityError` count as failure), MERGED/CLOSED via `_terminal_claim`, OPEN via the existing
  `finally` release, unreadable -> `reconcile-required` release reason (depends on D2, D3) - DoD: T-D1..T-D5, T-D9 pass.
- [ ] D5. Typed result: `_WatchOutcome.watch_end`, `DevLoopResult.watch_end`, `DevLoopResult.last_observed_pr`,
  `outcome="merge_watch_reconcile_required"`, `pr=None` on reconcile, `MERGE_WATCH_RECONCILE_REQUIRED` log; update the
  `DevLoopResult.pr` docstring (depends on D4) - DoD: T-D4 asserts every field; old `DevLoopResult` payloads decode.
- [ ] D6. Replay fixtures: record `dev_loop_final_read.json` (no hop) and `dev_loop_final_read_hop.json` (hop then gap)
  via `tools/record_workflow_history.py` scenarios added to `tests/replay_scenarios.py`; do not re-record any existing
  fixture (depends on D4) - DoD: T-D8 green; `test_every_recorded_fixture_belongs_to_a_scenario` green.
- [ ] D7. Mutation proof (each applied, confirmed red, reverted; outputs pasted into the PR): (a) remove the final
  read; (b) treat a failed read as OPEN; (c) recompute the deadline on a hop; (d) call `workflow.patched` for the
  marker in `_resume_merge_watch`; (e) relinquish the claim before the final read - DoD: five red runs recorded.

## Tasks 5-7 (switch stays OFF; validator unchanged)

- [ ] 5a. Tests first: T5 (depends on D7) - DoD: red commit.
- [ ] 5. `orchestrator/temporal/activities/rollout_switches.py`: `RolloutSwitches(deferred_feedback=False)`,
  `read_rollout_switches` (never raises; shared truthy set with `dispatcher._TRUTHY`), registered in
  `orchestrator/temporal/worker.py` `short_activities` and in the test activity registry fake (depends on 5a) - DoD:
  T5 passes.
- [ ] 6a. Tests first: T6, T7, T8, T-F7 (depends on 5) - DoD: red commit.
- [ ] 6. Feedback tick in `dev_loop.py`: `DEFERRED_FEEDBACK_PATCH` + `MergeWatchResume.feedback_tick` (fresh-start arm
  only); `FlipAuthority` recorded at the flip and carried as `MergeWatchResume.flip_authority`;
  `_feedback_authority_valid()` via `check_grant_freshness`; the `_deliver` branch (pending -> wait, done ->
  unobservable, switch, authority, enqueue); `_watch_pr` pickup with `feedback_task`, `_feedback_done` added before
  the task, hop predicate refusal, `finally` settlement (`merged-before-feedback` / `feedback-not-run` /
  cancelled -> `feedback-unobservable`); `_shepherd_tick(..., feedback=)` returning the outcome;
  `WorkflowResult.feedback_outcome` parsed in `activities/argo.py`; new refusal reasons in the vocabulary.
  `_validate_execution_request` is NOT edited (depends on 6a) - DoD: T6, T7, T8, T-F7 pass; unpatched
  `accepted_after_gates` still lands `feedback-not-ready`; all M1/M2a tests and fixtures green.
- [ ] 6b. Replay fixture `dev_loop_feedback_tick.json` (a continued run carrying an accepted-after-gates delivery,
  switch on in the fake, one tick, Succeeded) (depends on 6) - DoD: replays green.
- [ ] 7a. Tests first: S-tests below (depends on 6) - DoD: red commit.
- [ ] 7. `orchestrator/run_shepherd.py`: `--feedback-intent`, `--execution-request-id`, `--feedback-actor`,
  `--work-item-id`; `process_feedback` (intent fetch, scope classification, in-scope review-feedback under the
  existing claim and `--match-head-commit` fencing); single `feedback_outcome` to stdout and
  `$FEEDBACK_OUTCOME_PATH`; incompatible-flag exit 2 (depends on 7a) - DoD: S-tests pass; existing
  `tests/test_run_shepherd*.py` green.
- [ ] 7b. Mutation proof for tasks 5-7 (each confirmed red then reverted): switch read accepts a non-explicit value;
  switch activity error read as on; remove the `_feedback_done` guard (second tick appears); add to `_feedback_done`
  after the await instead of before; let the hop predicate ignore `feedback_task`; map an unknown outcome to
  Succeeded; skip `_feedback_authority_valid()`; emit `processed` on a failed review-feedback run; classify a
  non-exact answer as in-scope - DoD: nine red runs recorded in the PR.
- [ ] 8. PR description: link #993, #1021, the umbrella digest as provenance only, the test->fix commit pairs, the
  mutation and replay evidence, and the STOPPED T6 delivery leg; state that the PR is blocked for owner approval by
  #1020, needs independent review and green checks, and is not merged with an admin bypass - DoD: PR opened as Draft
  only if separately authorized; nothing released or deployed.

## Tests

Deadline-in-gap (new file `tests/test_merge_watch_final_read.py` unless noted):
- [ ] T-D1. Gap, final read MERGED: the PR merges with no worker, time passes the deadline, the worker returns ->
  exactly one post-deadline `get_pr_state`; result `pr.state == "MERGED"`, `watch_end == "final-read"`; deploy
  observation and `security_record_landed` each scheduled exactly once; lifecycle op `terminal`, never `release`.
- [ ] T-D2. Gap, final read OPEN -> result carries the FRESH OPEN (distinct `head_sha` from the last pre-gap read),
  `watch_end == "final-read"`, `release` after the read, no deploy observation.
- [ ] T-D3. Gap, final read CLOSED -> `pr.state == "CLOSED"`, `terminal` write, no deploy observation.
- [ ] T-D4. Gap, final read unreadable (every attempt raises transient, then non-transient, then `found=False`
  variants) -> exactly `FINAL_READ_ATTEMPTS` attempts; `watch_end == "reconcile-required"`,
  `outcome == "merge_watch_reconcile_required"`, `pr is None`, `last_observed_pr.state == "OPEN"`, `ended` non-empty,
  no deploy observation, `release` with the reconcile reason after the last attempt; never OPEN/CLOSED/success.
- [ ] T-D5. Deadline unchanged: the post-gap read happens at the first workflow task after the original deadline; no
  poll is scheduled after the deadline other than the final-read attempts; carried `deadline` string identical.
- [ ] T-D6. Hop: T-D1..T-D4 repeated where the watch hopped before the gap (continued run starts after the deadline)
  and where the gap begins after a hop; same outcomes; `MergeWatchResume.deadline` and `final_read` carried
  unchanged.
- [ ] T-D7. Marker memoisation (`tests/test_patch_memoization.py`): `merge-watch-final-read` recorded exactly once on
  a fresh run and zero times on a resumed run; a resume record with `final_read=False` performs no final read.
- [ ] T-D8. Replay (`tests/test_workflow_replay.py`): every existing pre-change fixture replays unchanged (and contains
  no `merge-watch-final-read` marker); new `dev_loop_final_read.json` and `dev_loop_final_read_hop.json` replay green.
- [ ] T-D9. Ordering and duplicates: the final read precedes the relinquishing write in the recorded op order; an
  activity task redelivered (fake fails the first delivery after recording) yields one terminal write, one deploy
  observation, one security record; replay of the recorded history produces no extra command.

Switch:
- [ ] T5. `read_rollout_switches` for `on`, `ON `, `1`, `true`, `yes` -> on; `off`, unset, empty, `2`, `enabled`,
  `tru` -> off; activity error in the workflow -> off; the scheduled command sequence is identical in every case.

Feedback tick (real `DevLoopWorkflow` continued run carrying `OpenDelivery(accepted_after_gates=True)`):
- [ ] T6. Switch on, PR OPEN, fake tick outcome `processed` -> exactly one shepherd CWFT submit with `intent_id`,
  `execution_request_id`, `feedback_actor`; the `we_` lands Succeeded; a redelivered Update for the same rid and a
  forced hop produce no second tick. Switch off -> `Failed feedback-disabled`, no tick. (The dispatcher-accept leg is
  STOPPED pending M2c.)
- [ ] T7. Outcomes `scope-expansion`, `failed`, `unobservable`, `None` (CWFT without output), an `ActivityError`, an
  in-flight tick when the PR merges, and the watch ending (merged / closed / deadline) before the tick -> Failed with
  the typed `ResumeRejection` (`scope-expansion`, `feedback-failed`, `feedback-unobservable`,
  `merged-before-feedback`, `feedback-not-run`); never Succeeded.
- [ ] T8. `flip_authority` missing, digest no longer fresh, freshness read fails -> `Failed reapproval-required`, no
  tick.
- [ ] T-F7. `_validate_execution_request` still defers `feedback-not-ready` for a new post-gates contract resume with
  an intent (existing `tests/test_execution_request_resume.py:586` case stays green); unpatched loops still land an
  accepted-after-gates delivery `feedback-not-ready`.

Shepherd (`tests/test_run_shepherd_feedback.py`):
- [ ] S-1. In-scope + review-feedback pushed under fencing -> `processed` on stdout and in the outcome file.
- [ ] S-2. Classifier `scope-expansion`, and a non-exact classifier answer -> `scope-expansion`, no implementer call.
- [ ] S-3. Review-feedback failure, head-commit fence mismatch, unexpected exception -> `failed`.
- [ ] S-4. Intent not found, `text_redacted`, client error -> `unobservable`, no classifier call.
- [ ] S-5. `--feedback-intent` with `--reconcile` / `--fix-only` / `--adopt-prs` or without `--service`/`--slug` -> exit 2.

## Rollback

Nothing is released or deployed by this proposal (release hold ON, switch unset), so before any release the rollback
is a plain revert of the PR. If a later release carries it and must be rolled back while loops that recorded
`merge-watch-final-read` or `deferred-feedback-tick` are in flight, do not delete the patched branches: either keep
them and stop new adoption with `workflow.deprecate_patch` in a follow-up deploy, or let those loops drain first
(`contract-drain-check` / visibility listing). The feedback tick is additionally inert while
`DEVLOOP_DEFERRED_FEEDBACK` is unset and the validator defers `feedback-not-ready`.
