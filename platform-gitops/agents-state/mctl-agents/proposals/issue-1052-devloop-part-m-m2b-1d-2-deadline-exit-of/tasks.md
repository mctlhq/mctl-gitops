# Tasks: issue-1052-devloop-part-m-m2b-1d-2-deadline-exit-of

This file implements slice M2b-1d-2 of #1021, split in #1046 and carried by #1052 as successor of #1051.

- The #1021 digest `sha256:e833d2af0ce3ce1e30699e6a77d221ba34af8948175c1ad75f2f0acd566fb144` is provenance only.
- The baseline is main `55b4633`, the merge of #1049.
- Under the owner rule on #1025, red-before and green-after evidence is mandatory. A single implementation commit is
  acceptable if the red runs can be reproduced (command and output go in the PR).

## Implementation

- [ ] 0. Gate. Before writing code, confirm four things:
  - this proposal's digest is approved;
  - that approval accepts E1-E3 (`requirements.md` R0a), the marker reuse (Q1) and the V2 closure scope (Q2);
  - the branch starts from main at or after `55b4633`;
  - #1051 is not approved or running.

  - DoD: if any check fails, nothing is committed and a report naming the failed check is posted on #1052.
- [ ] 1. Red baseline (depends on 0). Run the full suite (`uv run pytest`) on the branch base and record that it is
  green. Write D1, the converted gap-harness pin, and run it against the base with no production change.
  - DoD: D1 is red on its two-read / `pr.state == "MERGED"` assertion, not on an import or setup error. The command
    and output are kept for the PR.
  - If D1 cannot be shown red, stop and report (STOP 3).
- [ ] 2. Tests first (depends on 1).
  - Write D2-D18. They go in the new `tests/test_merge_watch_final_read.py`, except D1/D2, which go in
    `tests/test_merge_watch_worker_gap.py`. That file gets the `terminal_reconcile` kwarg on `_resume_record`, the
    scenario A conversion, the unpatched control and the docstring update.
  - Apply E1. Change the final assertions of `test_merge_detection_survives_read_failures_until_deadline`
    (`tests/test_dev_loop_workflow.py:4103`) to the interim end:
    - `WorkflowFailureError` whose cause is an `ApplicationError` of type `MergeWatchReconcileUnrecorded`;
    - no `release` and no `terminal` after the last pre-deadline poll.

    Update its docstring to point to D6 and to state that 1d-3 changes the test again.
  - Apply E2. Add `"gate_ran_head"` to `M1_ADDED["MergeWatchResume"]` (`tests/test_pre_m1_compat.py:154`) and
    `"gate_ran_head": ""` to `M1_DEFAULTS`.
  - Apply E3. In `tests/test_merge_watch_typed_result.py:79`, delete the `_WatchOutcome` / `watch_end` half of
    `test_nothing_in_production_sets_the_flag_or_a_watch_end`. Keep the `_reconcile_required` half and update its
    docstring.
  - DoD: D1, D3-D14, D13b-c and D18 (patched cases) are red against the base for the right reason. D2, D17 and the
    existing suite are green. The red run is reproduced in the PR.
- [ ] 3. State (depends on 2).
  - Add the constants `FINAL_READ_ATTEMPTS`, `FINAL_READ_BACKOFF` and `MERGE_WATCH_RECONCILE_UNRECORDED`, and the
    `GATED_ACTIVITY_TIMEOUT` import.
  - Add `self._watch_unrecorded` and `self._gate_ran_head`. `_record_gate_result` sets `self._gate_ran_head` when
    `result.ran`.
  - Add `MergeWatchResume.gate_ran_head: str = ""`. It is filled in the hop record and rehydrated in
    `_resume_merge_watch`.
  - Add the `_FinalRead` and `_WatchDecision` dataclasses.
  - DoD:
    - `tests/test_pre_m1_compat.py` (with E2), `tests/test_patch_memoization.py` and every replay test are green;
    - `grep -c "workflow.patched(" orchestrator/temporal/workflows/dev_loop.py` is unchanged.
- [ ] 4. Helpers (depends on 3). Add `_wait_unless_abandoned`, `_settle_watch_work`, `_final_pr_read` and `_settled`,
  as written in design section 2.
  - DoD: no `is_cancelled_exception`, no `_retain_claim`, no `tick_blocked_until`, and no scheduling of
    `record_merge_watch_reconcile` or `confirm_no_pr` (D17 green).
- [ ] 5. Decision and wiring (depends on 4).
  - Add `_decide_watch_end("deadline", ...)`, which sets the flag at decision start.
  - Add the `while ... else:` arm under `if watch.terminal_reconcile:` with the abandon guard.
  - Add the `watch_end` and `decision_kind` locals.
  - In `finally`, add the `self._watch_unrecorded` guard and the `MERGE_WATCH_RECONCILE_UNRECORDED` log line.
  - Add the raise after `finally` (only on `decision_kind == "unrecorded"`) and the final return with `watch_end`.
  - Correct the deadline part of the `_watch_pr` docstring.
  - Leave the grace-polls, read-error, #516, hop and MERGED/CLOSED exits untouched.
  - DoD: D1, D3-D14, D13b-d and D16 are green, along with D2 and E1.
- [ ] 6. Deliveries (depends on 5). Make the two expression edits in `_deliver` (design section 5).
  - DoD:
    - D18 is green;
    - every test in `tests/test_merge_watch_typed_result.py` and `tests/test_execution_request_resume.py` is green
      without being edited.
- [ ] 7. Fixtures (depends on 6). Add `tools/record_merge_watch_final_read.py` and the recorder helpers. Record
  `tests/fixtures/histories/merge_watch/dev_loop_final_read.json` and `.../merge_watch/dev_loop_final_read_hop.json`.
  - DoD:
    - D15 is green in the normal `uv run pytest` run;
    - `git diff --stat tests/fixtures/histories/*.json tests/fixtures/histories/pre_m1` is empty;
    - the flat-glob guards are green without being edited: `test_pre_m1_compat.py:584`, `test_workflow_replay.py:607`
      and `test_execution_request_replay.py` lines 376, 433, 476, 534, 686 and 731.
- [ ] 8. Full suite (depends on 7). Run `uv run pytest` over the whole repository.
  - DoD: the suite is green.
  - STOP 1: if any test outside E1-E3, the gap harness and the new files needed a change, stop and report on #1052.
  - STOP 4: if the pass cannot finish, stop and report the split in design section 9.
- [ ] 9. Mutation proof (depends on 8). Apply each mutation locally, run the named tests, confirm they are red, revert,
  and confirm the mutation is absent from `git diff`. Paste the command and the failing test into the PR.

  | Mutation | Change | Expected red |
  |---|---|---|
  | (a) | the decision returns `open(watch.last)` without reading | D1, D3 |
  | (d) | treat a failed final read as OPEN (`fresh = watch.last` when nothing is found) | D6 |
  | (e) | recompute `deadline = workflow.now() + MERGE_WATCH_DEADLINE` in the resume arm | D1, D10 |
  | (g) | issue the `release` write before the first final read | D3, D7 |
  | (v) | run `_decide_watch_end` also when the `else:` is reached with `self._abandoned` | D8 |
  | (w) | run the first `_final_pr_read` before `_settle_watch_work` | D7, D11 (settle-before-read) |
  | (x) | return `open` for a found OPEN while `unobserved` | D11 (window OPEN, ran-head OPEN) |
  | (ac) | skip `_apply_found_state` in `_final_pr_read` | D12 |
  | (ai) | replace `workflow.wait` by awaiting the cancelled tasks through `_settle_tick` / `_settle_gate` | D13 |
  | (al, first) | remove the `self._abandoned` check after the settle | D14 |
  | N1 (slice-local) | drop `and not self._watch_unrecorded` from `_deliver` (both expressions) | D18, D13 (delivery part) |
  | N2 (slice-local) | set `self._watch_unrecorded = True` only at the R7 return, not at decision start | D13b, D13c |

  (am) and (ao) are not run here. They move to 1d-4 with `tick_blocked_until` (owner ruling).
  - DoD: twelve red runs recorded, and none of the mutations in the diff.
- [ ] 10. PR (depends on 9).
  - The description links #993, #1021 (digest as provenance only), #1046, #1049, #1051 (superseded), #1052 and this
    proposal's approved digest.
  - It contains:
    - the D1 red-on-base evidence;
    - the E1-E3 list;
    - the marker-reuse deviation (Q1);
    - the V1-V3 table (design section 6);
    - the mutation output;
    - the replay evidence;
    - the observed V3 SDK surface (Q6).
  - It states:
    - the PR is blocked by the #1020 code-owner hold;
    - #1022 must be resolved before any release that carries 1d-3, and the release hold stays ON;
    - B4 stays FAIL;
    - #1003, gitops#2394 and mctl-api#934 stay Draft;
    - 1d-3 and 1d-4 are not started;
    - #1029 is closed only after the owner verifies D1.
  - DoD:
    - the PR is open and GitHub is verified to block it. If it is not blocked, stop.
    - any later HEAD change needs re-verification and a fresh review.
    - the implementer merges, releases and deploys nothing.

## Tests

All tests below are new and live in `tests/test_merge_watch_final_read.py` unless noted otherwise. They run on
`WorkflowEnvironment.start_time_skipping()` with `_fake_activities` from `tests/test_dev_loop_workflow.py`, and they
count activities from history events (`ACTIVITY_TASK_SCHEDULED`), not from fake calls. "Patched" means a fresh run (the
marker evaluates True) or a resume record with `terminal_reconcile=True`.

- [ ] D1. (`tests/test_merge_watch_worker_gap.py`, the converted pin.) Run scenario A with `terminal_reconcile=True`.
  - Expect two `get_pr_state` schedules, the second at or after `gap_end`.
  - Expect `merged_returns == 1`, `pr.state == "MERGED"` and `watch_end == "final-read"`.
  - Expect ops containing `terminal` and no `release`.
  - `_assert_interrupted` still holds.
  - Red on `55b4633`.
- [ ] D2. (Same file.) Scenario A with `terminal_reconcile=False`: one read, `OPEN`, `watch_end == ""`. Scenario B and
  the record-fields test are unchanged.
- [ ] D3. A patched run reaches the deadline and the final read returns MERGED.
  - Expect exactly one post-deadline `get_pr_state` and `watch_end == "final-read"`.
  - Deploy observation and `security_record_landed` are each scheduled once.
  - `terminal` is written and `release` never is. The run is Completed.
- [ ] D4. The final read returns OPEN with a new head.
  - Expect the fresh state and `final-read`.
  - Expect `release` after the read, and no deploy observation.
- [ ] D5. The final read returns CLOSED: `terminal` is written and there is no deploy observation.
- [ ] D6. Unreadable final read. Run three variants separately: every attempt raises the transient
  `ProposalListingError`; every attempt raises a non-transient error; every attempt returns `found=False`.
  - Expect exactly `FINAL_READ_ATTEMPTS` post-deadline reads, with `FINAL_READ_BACKOFF` timers between them.
  - The run ends Failed with `ApplicationError` type `MergeWatchReconcileUnrecorded`.
  - No `release` or `terminal` after the deadline, and the log line is present.
  - Neither `record_merge_watch_reconcile` nor `confirm_no_pr` is scheduled.
  - The `lifecycle_claim` query still names the claim.
- [ ] D7. Ordering, read from history. On every path in D3-D6, the settle commands come before the first
  post-deadline read, and that read comes before the relinquishing write where one exists.
- [ ] D8. Abandon during the watch.
  - Expect no read after the abandon, no decision timer and a `release`.
  - Expect `watch_end == "abandoned-unverified"` and `ended` starting with `abandoned:`.
  - The existing abandon test (`tests/test_dev_loop_workflow.py:2219`) stays green without being edited.
- [ ] D9. Abandon during a backoff and, separately, during the R6 window: the run wakes at once with no further read,
  ends `abandoned-unverified` and writes `release`. Abandon during a read:
  - that returns OPEN: the run ends `abandoned-unverified` with the fresh state;
  - that returns MERGED: the run reports MERGED with `terminal`.
- [ ] D10. Hop. Repeat D3, D4 and D6 in two setups: a watch that hopped before the gap (the continued run starts past
  the deadline), and a gap that begins after a hop.
  - `deadline` and `terminal_reconcile` are carried unchanged.
  - The continued run has zero marker events.
- [ ] D11. Own merge attempts.
  - A gate in flight at the deadline is cancelled and waited for before the first read.
  - A merge that lands during the window gives a second read of MERGED, then `terminal`.
  - A gate still OPEN after `GATED_ACTIVITY_TIMEOUT` gives the interim Failed end.
  - A `_gate_ran_head` equal to the OPEN head gives the same Failed end, within one run and across a hop
    (`gate_ran_head` carried).
  - With nothing in flight there is no `workflow.wait`, no window timer, and the run ends `final-read` OPEN.
  - `finally` settles nothing a second time.
- [ ] D12. Bookkeeping.
  - A final-read OPEN sets `_last_pr` and `saw_open_pr`, resets `polls_without_pr` and `terminal_status_polls`, and
    takes the claim through `_track_ownership`.
  - A MERGED first resolved by the final read, starting from a record with no claim, gives `acquire` then `terminal`,
    in that order.
- [ ] D13. (Closes V2: cancel in the settle.) Set up a patched run whose merge gate is in flight at the deadline, using
  a test-only `ActionApprovalWaitWorkflow` double registered under the same name. On cancellation the double holds
  until a test signal arrives, so the parent's `workflow.wait` is provably pending. The test then calls `handle.cancel()`
  on the parent.
  - `describe().status == WorkflowExecutionStatus.CANCELED`.
  - No `get_pr_state` is scheduled after the cancel.
  - No `release` and no `terminal` is written; `MERGE_WATCH_RECONCILE_UNRECORDED` is logged.
  - An open carried delivery lands `Failed`.
- [ ] D13b. (V2: cancel in the backoff.) The first final read fails, and `handle.cancel()` is called while the
  `FINAL_READ_BACKOFF` timer is pending. Expect CANCELED, no further read, no `release`/`terminal`, and the log line.
- [ ] D13c. (V2: cancel in the window.) A gate is in flight at the deadline, the first read returns OPEN, and
  `handle.cancel()` is called while the window timer is pending. Expect the same as D13b.
- [ ] D13d. (V3 pin, accepted interim limit.) A final-read `get_pr_state` fake blocks until the test calls
  `handle.cancel()`. Variant (i): the remaining attempts raise. Variant (ii): the next attempt returns MERGED.
  - Expect the observed 1.34.0 behaviour: the cancelled attempt is counted.
  - (i) ends Failed `MergeWatchReconcileUnrecorded`, with no `release` and the delivery `Failed`.
  - (ii) ends Completed with `terminal` and the fresh MERGED.
  - Neither variant is CANCELED.
  - The docstring names #1021 mutation (y) in 1d-3 as the change that must turn this red.
  - If the SDK instead surfaces `CancelledError` (Q6), assert CANCELED with no `release`, and report it in the PR.
- [ ] D14. Abandon delivered while the settle waits: no read after the settle, `abandoned-unverified` and a `release`.
- [ ] D15. Marker and replay (T-11 share).
  - The marker is recorded once on a fresh run and zero times on a continued run.
  - A `terminal_reconcile=False` record reaching the deadline makes no final read, and its recording replays.
  - Both `merge_watch/` fixtures replay clean.
  - Today's code replays its own fresh recording.
  - Every existing fixture replays unchanged.
- [ ] D16. Duplicates (T-14 deadline share). A redelivered final-read `get_pr_state` gives one `terminal`, one deploy
  observation and one security record. Replaying the history produces no extra command.
- [ ] D17. Scope pins. An AST scan of `dev_loop.py` finds none of the following:
  - an `execute_activity` of `record_merge_watch_reconcile` or `confirm_no_pr`;
  - `_reconcile_required = True`;
  - `is_cancelled_exception`;
  - `tick_blocked_until`;
  - `_retain_claim`;
  - a new `workflow.patched` string.

  `tests/test_execution_request_resume.py` (T-16) stays green without being edited.
- [ ] D18. (Closes V1: deliveries.) Reuse the `_deliver_with` pattern of `tests/test_merge_watch_typed_result.py`. Set
  up a resume record with a past deadline, `terminal_reconcile=True` and a carried open delivery whose fulfil is
  released only once the decision has started.
  - (i) All final reads fail: the delivery's execution lands `Failed`, never `Succeeded`, and the run is Failed.
  - (ii) The final read returns OPEN: the delivery waits for the decision, then lands `Succeeded`, as today.
  - (iii) `terminal_reconcile=False`: lands `Succeeded`, as today.

Placement of the 23 #1021 tests:

- **In this slice:**
  - T-1 (D3), T-2 (D4), T-3 (D5).
  - T-4 in its interim form (D6).
  - T-8 deadline share (D7).
  - T-10 without its record-marker part (D10).
  - T-11 with two of the four fixtures (D15).
  - T-14 deadline share (D16).
  - T-15 deadline share (D8, D9, D14).
  - T-16 as a pin (D17).
  - T-19 deadline share without `tick_blocked_until` (D11).
  - T-20 settle, backoff and window cancellation with retention (D13, D13b, D13c). This is pulled forward by the V2
    closure.
  - T-21 without its #516-after-resume part (D12).
- **Already landed:** T-7 and T-17 (1c, #1042); the reachable part of T-12, and T-13 (1d-1, #1049).
- **Deferred to 1d-3:**
  - T-4 reconcile-required form, T-8 record ordering, T-9.
  - T-10 record-marker part, T-12 wired part, T-14 record share, T-15 post-decision record part.
  - T-18, T-22 reconcile edges.
  - From T-20: the cancelled-activity re-raise (y), the record retry sleep and the running record activity. D13d pins
    the interim behaviour.
  - The `dev_loop_reconcile_required` fixture.
- **Deferred to 1d-4:**
  - T-5, T-6.
  - T-15 grace, read-error and `confirm_no_pr` parts; T-19 grace, read-error and `tick_blocked_until` parts, with
    (am) and (ao).
  - T-21 #516-after-resume, the T-22 grace-to-deadline part, T-23.
  - The `dev_loop_no_pr_confirmed` fixture.

## Rollback

- **Before any release.** Nothing is released or deployed (the release hold is ON), so rollback is a plain revert of
  the PR. The revert also undoes E1-E3 and removes the two fixtures. No production history carries the marker (worker
  tag `1.117.0`).
- **After a later release that carries this slice.** Do not revert below this slice while either of these exists:
  - watches whose first run recorded `merge-watch-terminal-reconcile` and that are inside the deadline decision;
  - closed runs of that shape that are still queried.

  A lower worker replaying such a history hits nondeterminism. Instead, keep the branch and stop new adoption with
  `workflow.deprecate_patch` in a follow-up, or drain those runs first (visibility listing on `DevLoopWorkflow`). A
  lower worker that continues a hopped watch also drops `gate_ran_head`, which is the fail-open direction.
- **Claims left by the interim Failed or Cancelled ends.** The lifecycle store's existing dead-owner reaping recovers
  them (liveness bound, about 10 h). Only intake can start a new run on a Failed or Cancelled id;
  `restart_if_restartable` cannot. No manual release is part of this rollback.
- **B4.** Nothing here decides B4 (#1007).
