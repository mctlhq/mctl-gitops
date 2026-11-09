# Tasks: issue-1055-devloop-part-m-m2b-1d-2b-wire-the-merge

Slice: **1d-2b-i** (owner split, 2026-11-09). Tasks marked **(ii)** and tests D15b and D16 belong to 1d-2b-ii, which gets
its own issue after this one is merged. The implementer does not build them.

Base: main `0536caf`. Production file: `orchestrator/temporal/workflows/dev_loop.py`. The only allowed edits to existing
tests are:

- E1, E2 and E3;
- the gap-harness conversion in `tests/test_merge_watch_worker_gap.py`;
- the replacement of D17a in `tests/test_merge_watch_decision.py`.

Anything else is a STOP: report on #1055 and use no workaround.

- [ ] 0. Red on base. Convert the gap harness first (task 6, test D1) and run it against `0536caf` with no production
  change. — DoD: D1 fails because there is one `get_pr_state` and the state is OPEN, not MERGED. The command and output
  are kept for the PR. If D1 is not red, STOP.
- [ ] 1. Suite probe (depends on 0). On a scratch copy, apply tasks 2-4 and run `uv run --locked pytest -q`. — DoD: the
  only red existing tests are E1, the old gap pin, D17a and E3's `watch_end` half. In particular,
  `test_merge_detection_deadline_returns_last_open_state` and `test_deadline_is_carried_not_recomputed_across_hops`
  must be green (Q-D). Any other red test is a STOP.
- [ ] 2. Wiring (depends on 1). Make the following changes in `_watch_pr`:
  - declare the locals `watch_end = ""` and `decision_kind = ""`;
  - add the `while ... else:` arm with `if watch.terminal_reconcile and not self._abandoned:`;
  - map `final` to an early `_WatchOutcome(last=decision.last, watch_end=WATCH_END_FINAL_READ)`, `open` to
    `WATCH_END_FINAL_READ`, and `abandoned` to `WATCH_END_ABANDONED_UNVERIFIED`;
  - update `watch.last` from `decision.last` when it is not None;
  - after `finally`, raise `ApplicationError(..., type=MERGE_WATCH_RECONCILE_UNRECORDED, non_retryable=True)` on
    `decision_kind == "unrecorded"`;
  - make the final return carry `watch_end`;
  - correct the `_watch_pr` docstring.

  — DoD: design section 1 is implemented verbatim, and no other exit is touched.
- [ ] 3. `finally` guards (depends on 2). Add `not self._watch_unrecorded` to the relinquishing guard (line 7158). Add
  the `MERGE_WATCH_RECONCILE_UNRECORDED repo=... workflow=... exit=deadline last=...` warning on the flagged branch.
  Leave the `_report_claim_abandonment` guard (line 7229) unchanged, with a comment saying why (R10). — DoD: no
  `release` or `terminal` is written while the flag is True.
- [ ] 4. `_deliver` guard (depends on 2). Change the wait predicate (line 3096) to `self._abandoned or self._exiting or
  self._hopping or ((self._is_approved() or self._gates_passed) and not self._watch_unrecorded)`. Change `decided` (line
  3104) to `... and not self._abandoned and not self._watch_unrecorded`. — DoD: D18 is green, and
  `tests/test_merge_watch_typed_result.py` T6 is green unedited.
- [ ] 5. Hop carry (depends on 2). Add `MergeWatchResume.gate_ran_head: str = ""` after `merge_gate_settled_head`.
  Fill it in the hop record and rehydrate it in `_rehydrate_work_context`. Apply E2 in `tests/test_pre_m1_compat.py`
  (`M1_ADDED["MergeWatchResume"]` gains `"gate_ran_head"`, and `M1_DEFAULTS` gains `"gate_ran_head": ""`). — DoD:
  `tests/test_pre_m1_compat.py` is green with E2 only.
- [ ] 6. Gap-harness conversion. In `tests/test_merge_watch_worker_gap.py`:
  - add `_resume_record(t0, offset, *, terminal_reconcile=False)`;
  - wrap the factory's `lifecycle_ownership` fake to record ops;
  - rename scenario A to `test_deadline_in_gap_reads_the_merged_pr_once_more` (D1);
  - add `test_unpatched_record_keeps_the_legacy_deadline_end` (D2);
  - update the docstring.

  — DoD: D1 and D2 are green, and scenario B and the record-fields test are unchanged.
- [ ] 7. Existing-test edits E1 and E3 (depends on 2-3).
  - E1: the final assertions of `test_merge_detection_survives_read_failures_until_deadline` become: `WorkflowFailureError`
    whose cause is an `ApplicationError` of type `MergeWatchReconcileUnrecorded`, and no `release` or `terminal` after
    the last pre-deadline poll.
  - E3: remove the `_WatchOutcome(watch_end=...)` half of `test_nothing_in_production_sets_the_flag_or_a_watch_end`,
    keep the `_reconcile_required` half, and update its docstring.

  — DoD: both are green, and the diff touches only those lines.
- [ ] 8. New tests (depends on 2-5). Write D3-D14, D15a and D18 in `tests/test_merge_watch_final_read.py`. Replace D17a
  with the activation pin (D17). D15b and D16 are 1d-2b-ii and are not written. — DoD: all are green.
- [ ] 9. **(ii) NOT in this slice.** Fixtures: add the recorder in `tests/test_merge_watch_final_read.py` and
  `tools/record_merge_watch_final_read.py`, and record `tests/fixtures/histories/merge_watch/dev_loop_final_read.json`
  and `.../merge_watch/dev_loop_final_read_hop.json`. Deferred to 1d-2b-ii with D15b and D16. In 1d-2b-i, assert only
  that `git diff --stat tests/fixtures` is empty.
- [ ] 10. Full suite (depends on 8; task 9 is not part of this slice). Run `uv run --locked pytest -q` and `uv run ruff check`. — DoD: both are green.
  If the pass cannot finish, STOP and report on #1055 where it stopped (the split into i and ii is already applied).
- [ ] 11. Mutation proof (depends on 10). Apply each mutation below by exact-text substitution on a committed worktree,
  run only the named tests, record the red output, revert, and confirm `git diff` is clean. — DoD: every row is red
  with output, or (finally-2 only, Q-C) reported equivalent with reasoning and output. None is in the diff.

  | Mutation | Change | Expected red |
  |---|---|---|
  | (v) | drop `and not self._abandoned` from the `else:` guard | D8 |
  | (tr) | drop `watch.terminal_reconcile` from the `else:` guard | D2, D15a (unpatched record across the deadline) |
  | (fe) | drop the `final` early return (fall into `finally`, `watch_end` stays `""`) | D3, D1 |
  | (e) | recompute `deadline = workflow.now() + MERGE_WATCH_DEADLINE` in the resume arm | D10 |
  | (g) | issue the `release` write in the `else:` arm before calling the decision | D3, D7 |
  | (ai) | replace `workflow.wait(in_flight)` in `_settle_watch_work` by awaiting through `_settle_tick` / `_settle_gate` only | D13 |
  | N1 | on `unrecorded`, return `_WatchOutcome(last=watch.last)` instead of raising | E1, D6 |
  | N2 | wrap the decision call in `try: ... finally: self._watch_unrecorded = False` | D13, D13b |
  | finally-1 | drop `not self._watch_unrecorded` from the relinquishing guard | D6, D13 |
  | finally-2 | add `and not self._watch_unrecorded` to the `_report_claim_abandonment` guard | D6b (or equivalent, Q-C) |
  | carry | omit `gate_ran_head=` from the hop record (or its rehydration) | D11 (across-hop row) |
  | deliver-wait | drop `and not self._watch_unrecorded` from the wait predicate | D18 (held, then `Succeeded` after `final`) |
  | deliver-decided | drop `and not self._watch_unrecorded` from `decided` | D18 (`Failed` after `unrecorded`) |

- [ ] 12. PR (depends on 11). The description:
  - links #1021 (provenance only), #1029, #1046, #1049, #1052, #1053, #1055 and this proposal's approved digest;
  - pastes the task 0 red-on-base evidence, the E1-E3 list, the mutation table output and the replay evidence (D15a);
  - states that this is 1d-2b-i and that the fixtures, recorder, D15b and D16 are 1d-2b-ii, not started;
  - states the platform impact from design.md;
  - states that B4 (#1007) stays FAIL, the release hold stays ON, #1022 blocks any release carrying this line, and 1d-3
    and 1d-4 are not started;
  - states that #1029 is closed only by the owner after verifying D1.

  — DoD: the PR is open. Nothing is merged, released or deployed by the implementer.

## Tests

Unless noted, all tests are new, in `tests/test_merge_watch_final_read.py`. They run on
`WorkflowEnvironment.start_time_skipping()` with `_fake_activities` from `tests/test_dev_loop_workflow.py`. Activities
are counted from `ACTIVITY_TASK_SCHEDULED` history events.

- [ ] D1. Converted gap pin, in `test_merge_watch_worker_gap.py`.
  - Setup: scenario A with `terminal_reconcile=True`.
  - Expect: two `get_pr_state` schedules, the second at or after `gap_end`; `merged_returns == 1`; `pr.state ==
    "MERGED"`; `watch_end == "final-read"`; ops include `terminal` and no `release`; `_assert_interrupted` holds.
  - Must be red on the base.
- [ ] D2. Unpatched record, in the gap harness.
  - Setup: scenario A with `terminal_reconcile=False`.
  - Expect: one read, OPEN, `watch_end == ""`.
- [ ] D3. Fresh run, final read MERGED.
  - Expect: exactly one post-deadline read; `watch_end == "final-read"`; `terminal` once, never `release`; deploy
    observation scheduled once; the run Completed.
- [ ] D4. Final read OPEN, nothing in flight, head different from the last poll.
  - Expect: the fresh state in `pr`; `final-read`; `release` after the read with the fresh head; no deploy observation.
- [ ] D5. Final read CLOSED.
  - Expect: `terminal`; no deploy observation; `final-read`.
- [ ] D6. Unreadable final read, in three variants: transient `ProposalListingError`, a non-transient error, and
  `found=False`.
  - Expect: exactly `FINAL_READ_ATTEMPTS` post-deadline reads, with `FINAL_READ_BACKOFF` timers between them.
  - Expect: the run ends Failed with an `ApplicationError` of type `MergeWatchReconcileUnrecorded`.
  - Expect: no `release` or `terminal` after the deadline, `MERGE_WATCH_RECONCILE_UNRECORDED` logged, and neither
    `record_merge_watch_reconcile` nor `confirm_no_pr` scheduled.
- [ ] D6b. As D6, from a resume record that carries `claim_abandoned=True` and a held `owned_entity_id`.
  - Expect: `LIFECYCLE-CLAIM-ABANDONED` logged exactly once.
  - Pins R10.
- [ ] D7. Ordering, read from history, on D3-D6.
  - Expect: settle commands, then the first post-deadline read, then the relinquishing write (where one exists).
- [ ] D8. Ordinary operator abandon during the watch, before the deadline.
  - Expect: no `get_pr_state` after the signal; no timer added by the decision; `release`; `watch_end == ""`; `ended`
    starts with `abandoned: `.
  - Expect: the existing abandon tests stay green unedited.
- [ ] D9. Abandon during the decision, in four cases:
  - during a final-read backoff, and separately during the window: wakes at once, no further read,
    `abandoned-unverified`, `release`;
  - during a read that returns OPEN: `abandoned-unverified`, with that fresh state in `pr`;
  - during a read that returns MERGED: MERGED, `terminal`, `final-read`.
- [ ] D10. Hop.
  - Setup: D3, D4 and D6 repeated for a watch that hopped before the deadline.
  - Expect: the same outcomes; `deadline` and `terminal_reconcile` carried unchanged; zero marker events in the
    continued run.
- [ ] D11. Own merge attempts.
  - A gate in flight at the deadline is cancelled and waited for before the first read.
  - A merge that lands in the window gives a second read of MERGED and `terminal`.
  - A gate still OPEN after `GATED_ACTIVITY_TIMEOUT` ends with the Failed interim end.
  - `_gate_ran_head` equal to the OPEN head gives the Failed end, both in one run and across a hop (`gate_ran_head`
    carried).
  - With nothing in flight there is no `workflow.wait`, no window timer, and an OPEN `final-read`.
  - `finally` settles nothing twice.
- [ ] D12. Bookkeeping.
  - A final-read OPEN sets `_last_pr` and `saw_open_pr`, resets the poll counters, and takes the claim.
  - A MERGED first seen by the final read, with no claim, gives `acquire` then `terminal`.
- [ ] D13. Workflow cancel while `_settle_watch_work` waits on a gate that ignores the cancel. The gate is the test-only
  `ActionApprovalWaitWorkflow` double, released in teardown.
  - Expect: status Cancelled; no `get_pr_state` after the cancel; no `release` (S2 closed);
    `MERGE_WATCH_RECONCILE_UNRECORDED` logged.
- [ ] D13b. Cancel during a final-read backoff.
  - Expect: no further read and no `release`.
- [ ] D13c. Cancel during the window.
  - Expect: no further read and no `release`.
- [ ] D13d. S3 pin: cancel during a final-read activity.
  - Expect: the observed SDK 1.34.0 surface (`ActivityError` with a cancelled cause, caught as an unread attempt).
  - Expect: no stale `Succeeded`/Completed `final-read`, and no unintended `release`.
  - The docstring states the same-activation `CancelledError` caveat, and states that 1d-3's (y) turns this red.
- [ ] D13e. Cancel during the `acquire` or `terminal` `_ownership` activity inside the decision.
  - Expect: the observed absorb (`_ownership` swallows `CancelledError` and returns None) and the resulting end, as an
    interim-limit pin.
- [ ] D14. Abandon while the settle waits.
  - Expect: no read after the settle; `abandoned-unverified`; `release`.
- [ ] D15a. Marker and replay (1d-2b-i, in-test recording, nothing committed).
  - The marker is recorded once on a fresh run and zero times on a continued run.
  - An unpatched record across the deadline makes no final read and replays.
  - A history recorded in-test by this code replays clean through the Replayer.
  - Today's code replays its own fresh recording.
  - `test_workflow_replay.py`, `test_execution_request_replay.py`, `test_pre_m1_compat.py` (E2 only) and
    `test_patch_memoization.py` stay green.
- [ ] D15b. **(ii) NOT in this slice.** The two committed `merge_watch/` fixtures replay clean.
- [ ] D16. **(ii) NOT in this slice.** Duplicate delivery of the final-read task.
  - Expect: one landed `terminal` and one deploy observation; replay adds no command.
- [ ] D17. Activation pin, replacing D17a in `test_merge_watch_decision.py`:
  - `_watch_pr` has exactly one `While` with `orelse`, which calls `_decide_watch_end`;
  - the helpers are called only from each other and `_watch_pr`;
  - `_watch_unrecorded` occurs only in `__init__`, `_decide_watch_end`, `_settled`, `_watch_pr` and `_deliver`;
  - `MERGE_WATCH_RECONCILE_UNRECORDED` has readers;
  - none of the FORBIDDEN names occurs, and there is no `_reconcile_required = True`;
  - `PATCHED_CALLS == 37`;
  - the module docstring is updated.
- [ ] D18. Delivery held during a decision, with its own helper (not `_deliver_with`). A delivery accepted before the
  gates has its fulfilment withheld until the decision has started.
  - On `final`: held while the flag is True, then `Succeeded`.
  - On `unrecorded`: `Failed`, and the run ends Failed without hanging in `_settle_deliveries`.
  - Adds no command while held.

## Rollback

- **Before release** (the expected state: hold ON, workers on 1.117.0): revert the merge commit. No deployed worker
  ran this code, so no history carries decision commands. (The fixtures and the recorder arrive only with 1d-2b-ii and go with its own revert.)
- **After any release carrying this slice:** do not roll back below it with a plain image downgrade. Histories that
  recorded the marker and reached the decision fail with nondeterminism on an older worker. Rollback safety is
  governed by B4 (#1007). Drain or terminate those runs first, or roll forward.
- **Claims retained by an interim Failed end:** the reconciler reaps them at the liveness bound (about 10 h). An
  operator can also inspect them with `mctl_inspect_lifecycle_conflict` and fence them with
  `mctl_fence_lifecycle_claim` once they are dead.
