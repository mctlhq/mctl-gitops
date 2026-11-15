# Tasks: issue-1051-devloop-part-m-m2b-1d-2-deadline-exit-of

Slice M2b-1d-2 of #1021 (approved digest `sha256:e833d2af0ce3ce1e30699e6a77d221ba34af8948175c1ad75f2f0acd566fb144`,
provenance only), split in #1046. It is written against PR #1049 head `9ac2ff4`. Under the #1025 owner rule, red and
green evidence is mandatory, and a single implementation commit is acceptable when the red runs can be reproduced
independently (command and output in the PR).

## Implementation

- [ ] 0. Gate. Confirm three things before writing any code. First, #1049 is merged on main by the owner. Second, this
  proposal's digest is approved: that approval accepts exactly edits E1-E3 (`requirements.md` R0b/R0c). Third, branch
  from main at or after the #1049 merge. - DoD: if any of the three fails, nothing is committed and a report is posted
  on #1051 naming which one.
- [ ] 1. Baseline (depends on 0). Run the full suite on the branch base and record it green. Write D1 (the converted
  gap-harness pin) and run it against the base with no production change. - DoD: D1 is red on its
  `pr.state == "MERGED"` / two-read assertion, not on an import or setup error, and the command and output are kept for
  the PR. If D1 cannot be made red on the base, stop and report (STOP condition 3).
- [ ] 2. Tests (depends on 1).
  - Write D2-D17 in the new `tests/test_merge_watch_final_read.py`, and D1/D2 in `tests/test_merge_watch_worker_gap.py`
    (the `terminal_reconcile` kwarg on `_resume_record`, the scenario A conversion, the new unpatched control and the
    docstring update).
  - Apply E1: replace the last three assertions of
    `test_merge_detection_survives_read_failures_until_deadline` with the interim end, that is
    `WorkflowFailureError` whose cause is `ApplicationError` type `MergeWatchReconcileUnrecorded`, and no `release` or
    `terminal` op after the last pre-deadline poll. The docstring should point to D6 and state that 1d-3 changes it
    again.
  - Apply E2: add `"gate_ran_head"` to `M1_ADDED["MergeWatchResume"]` and `"gate_ran_head": ""` to `M1_DEFAULTS` in
    `tests/test_pre_m1_compat.py`.
  - Apply E3: delete the `_WatchOutcome` / `watch_end` half of
    `test_nothing_in_production_sets_the_flag_or_a_watch_end` in `tests/test_merge_watch_typed_result.py`, keep the
    `_reconcile_required` half, and update its docstring.
  - DoD: D1, D3-D14 and D16 are red against the base for the right reason. D2, D17 and the existing suite are green.
    The red run is reproduced in the PR.
- [ ] 3. State (depends on 2). Add `FINAL_READ_ATTEMPTS`, `FINAL_READ_BACKOFF`, `MERGE_WATCH_RECONCILE_UNRECORDED` and
  the `GATED_ACTIVITY_TIMEOUT` import. Add `_MergeWatchRun.unrecorded`, `_FinalRead` and `_WatchDecision`. Add
  `self._gate_ran_head`, set in `_record_gate_result` on `result.ran`. Add `MergeWatchResume.gate_ran_head: str = ""`,
  filled in the hop record and rehydrated in `_resume_merge_watch`. - DoD: `tests/test_pre_m1_compat.py` (with E2),
  `tests/test_patch_memoization.py` and every replay test are green, and no new `workflow.patched` call exists
  (`grep -c "workflow.patched("` is unchanged).
- [ ] 4. Helpers (depends on 3). Add `_wait_unless_abandoned`, `_settle_watch_work` (cancel, then `workflow.wait`
  only on a non-empty list, then drain through `_settle_tick` / `_settle_gate` with the real `watch.poll_index`, then
  both tasks set to None) and `_final_pr_read`, as written in design section 2. - DoD: no `is_cancelled_exception`, no
  `_retain_claim`, and no scheduling of `record_merge_watch_reconcile` or `confirm_no_pr` (D17 green).
- [ ] 5. Decision and wiring (depends on 4). Add `_decide_watch_end("deadline", ...)` and the `while ... else:` arm
  under `if watch.terminal_reconcile:` with the abandon guard. Add the local `watch_end`, the `watch.unrecorded` guard
  and the `MERGE_WATCH_RECONCILE_UNRECORDED` log line in `finally`, the raise after `finally`, and the final return with
  `watch_end`. Correct the `_watch_pr` docstring for the deadline exit. Leave the grace-polls, read-error, #516, hop and
  MERGED/CLOSED exits untouched. - DoD: D1 and D3-D14 green, D2 green, E1 green.
- [ ] 6. Fixtures (depends on 5). Add the recorder in `tests/test_merge_watch_final_read.py` and
  `tools/record_merge_watch_final_read.py`. Record `tests/fixtures/histories/merge_watch/dev_loop_final_read.json` and
  `.../merge_watch/dev_loop_final_read_hop.json`, with no existing fixture re-recorded and nothing added to the flat
  `tests/fixtures/histories/`. - DoD: D15 green. `git diff --stat tests/fixtures/histories/*.json
  tests/fixtures/histories/pre_m1` is empty, and the flat-directory guards are green unedited.
- [ ] 7. Full suite (depends on 6). Run `uv run pytest` over the whole repository. - DoD: green. If any test other
  than those named in E1-E3, the gap harness and the new files needed a change, stop and report on #1051 (STOP 1). If
  the pass cannot finish in one implementer run, stop and report the split from design section 8 (STOP 4).
- [ ] 8. Mutation proof (depends on 7). Apply each mutation locally, run the named tests, confirm red, revert, and
  confirm `git diff` is clean of it. Paste the command and failing test into the PR.

  | Mutation | Change | Expected red |
  |---|---|---|
  | (a) | remove the final read at the deadline exit (decision returns `open(watch.last)` without reading) | D1, D3 |
  | (d) | treat a failed final read as OPEN (`fresh = watch.last` when nothing found) | D6 |
  | (e) | recompute `deadline = workflow.now() + MERGE_WATCH_DEADLINE` in the resume arm | D1, D10 |
  | (g) | issue the `release` write before the first final read | D3, D7 |
  | (v) | run `_decide_watch_end` also when the `else:` is reached with `self._abandoned` | D8 |
  | (w) | run the first `_final_pr_read` before `_settle_watch_work` | D11 (settle-before-read), D7 |
  | (x) | return `open` for a found OPEN while `unobserved` | D11 (window OPEN, ran-head OPEN) |
  | (ac) | skip `_apply_found_state` in `_final_pr_read` | D12 |
  | (ai) | replace `workflow.wait` by awaiting the cancelled tasks through `_settle_tick` / `_settle_gate` | D13 |
  | (al, first) | remove the `self._abandoned` check after the settle | D14 |

  (am) and (ao) are not run here: they are unobservable from the deadline exit (design section 7) and move to 1d-4.
  - DoD: ten red runs recorded, none of the mutations in the diff.
- [ ] 9. PR (depends on 8). The description links #993, #1021 (digest as provenance only), #1046, #1049, #1051 and the
  approved digest of this proposal. It includes the D1 red-on-base evidence, the E1-E3 list, the mutation table output,
  the replay evidence and the scope adjustments (Q3, Q4). It states the following:
  - the PR is blocked by the #1020 code-owner hold;
  - #1022 blocks any release of this line, and the release hold stays ON;
  - B4 stays FAIL, and #1003, gitops#2394 and mctl-api#934 stay Draft;
  - 1d-3 and 1d-4 are not started;
  - #1029 is closed only after the owner verifies D1.

  - DoD: PR open, and GitHub verified to block the merge. If it is not blocked, stop. Any later HEAD change needs
    re-verification and a fresh review. Nothing is merged, released or deployed by the implementer.

## Tests

All tests below are new, in `tests/test_merge_watch_final_read.py` unless noted. They run on
`WorkflowEnvironment.start_time_skipping()` with the `_fake_activities` factory from `tests/test_dev_loop_workflow.py`,
and count activities from history events (`ACTIVITY_TASK_SCHEDULED`), not from fake calls.

- [ ] D1. (`tests/test_merge_watch_worker_gap.py`, the converted pin.) Scenario A with `terminal_reconcile=True`.
  Expect two `get_pr_state` schedules, the second at or after `gap_end`; `merged_returns == 1`; `pr.state == "MERGED"`;
  `watch_end == "final-read"`; ops with `terminal` and no `release`; and `_assert_interrupted` still holds. Red on the
  base.
- [ ] D2. (`tests/test_merge_watch_worker_gap.py`.) Scenario A with `terminal_reconcile=False`: one read, `OPEN`,
  `watch_end == ""` (R15). Scenario B and the record-fields test stay unchanged.
- [ ] D3. Fresh run reaching the deadline, final read MERGED. Expect exactly one post-deadline `get_pr_state`,
  `pr.state == "MERGED"` and `watch_end == "final-read"`. Deploy observation and `security_record_landed` are each
  scheduled once, the op is `terminal` and never `release`, and the run is Completed.
- [ ] D4. Final read OPEN with a head SHA distinct from the last pre-deadline read. The result carries the fresh state,
  `watch_end == "final-read"`, a `release` after the read, and no deploy observation.
- [ ] D5. Final read CLOSED: `terminal` write and no deploy observation.
- [ ] D6. Unreadable final read: every attempt raises the transient `ProposalListingError`, then (separately) a
  non-transient error, then (separately) `found=False`. Expect exactly `FINAL_READ_ATTEMPTS` scheduled `get_pr_state`
  after the deadline, and backoff timers of `FINAL_READ_BACKOFF`. The run is Failed with `ApplicationError` type
  `MergeWatchReconcileUnrecorded`. There is no `release` or `terminal` after the deadline,
  `MERGE_WATCH_RECONCILE_UNRECORDED` is logged, and neither `record_merge_watch_reconcile` nor `confirm_no_pr` is
  scheduled.
- [ ] D7. Ordering, from history: on every D3-D6 path, the settle commands come before the first post-deadline
  `get_pr_state`, which comes before the relinquishing write (where one exists).
- [ ] D8. Abandon during the watch. Expect no `get_pr_state` after the abandon signal, no timer added by the decision, a
  `release`, `watch_end == "abandoned-unverified"` and `ended` starting `abandoned:`. The existing abandon tests in
  `tests/test_dev_loop_workflow.py` stay green unedited.
- [ ] D9. Abandon during a final-read backoff, and separately during the R6 window. The run wakes at once with no
  further attempt, ends `abandoned-unverified` and writes `release`. Abandon during a read that returns OPEN ends
  `abandoned-unverified` with that fresh state in `pr`. Abandon during a read that returns MERGED reports MERGED with
  `terminal`.
- [ ] D10. Hop. D3, D4 and D6 repeated for a watch that hopped before the gap (the continued run starts past the
  deadline), and for a gap that begins after a hop. Expect the same outcomes, with `MergeWatchResume.deadline` and
  `terminal_reconcile` carried unchanged and zero marker events in the continued run.
- [ ] D11. Own merge attempts.
  - A gate in flight at the deadline is cancelled and waited for before the first final read.
  - A gate whose merge lands during the window gives a second read of MERGED and a `terminal` write.
  - A gate that is still OPEN after `GATED_ACTIVITY_TIMEOUT` ends with the interim Failed end, not a `final-read` OPEN.
  - `_gate_ran_head` equal to the returned OPEN head gives the same result, in one run and across a hop
    (`gate_ran_head` carried).
  - With no attempt in flight there is no `workflow.wait`, no window timer, and a `final-read` OPEN.
  - `finally` settles nothing a second time.
- [ ] D12. Bookkeeping. A final-read OPEN sets `_last_pr` and `saw_open_pr`, resets `polls_without_pr` and
  `terminal_status_polls`, and takes the claim through `_track_ownership`. A MERGED first resolved by the final read,
  from a record with no claim, gives `acquire` then `terminal`, in that order.
- [ ] D13. Workflow cancel delivered while `_settle_watch_work` waits on a cancelled gate. Expect status Cancelled and
  no `get_pr_state` after the cancel. Claim retention on cancel is not asserted here; it belongs to 1d-3.
- [ ] D14. Abandon delivered while the settle waits. Expect no `get_pr_state` after the settle,
  `watch_end == "abandoned-unverified"` and a `release`.
- [ ] D15. Marker and replay (T-11 share).
  - `merge-watch-terminal-reconcile` is recorded exactly once on a fresh run and zero times on a continued run.
  - A resume record with `terminal_reconcile=False` reaching the deadline makes no final read, and its recorded history
    replays.
  - `merge_watch/dev_loop_final_read.json` and `merge_watch/dev_loop_final_read_hop.json` replay clean.
  - Today's code replays its own fresh recording.
  - Every existing fixture replays unchanged: `tests/test_workflow_replay.py`, `tests/test_execution_request_replay.py`,
    `tests/test_pre_m1_compat.py` and `tests/test_patch_memoization.py`, all unedited apart from E2.
- [ ] D16. Duplicates (T-14 deadline share). A `get_pr_state` task redelivered at the final read (the fake fails the
  first delivery after recording) gives one landed `terminal`, one deploy observation and one security record. Replay
  of that history produces no extra command.
- [ ] D17. Scope pins. An AST scan of `dev_loop.py` finds no `execute_activity` of `record_merge_watch_reconcile` or
  `confirm_no_pr`, no `_reconcile_required = True`, no `is_cancelled_exception`, no `tick_blocked_until` and no
  `_retain_claim`. `tests/test_execution_request_resume.py` (the T-16 pin) stays green unedited.

Placement of the 23 #1021 tests:

- **In this slice:** T-1 (D3), T-2 (D4), T-3 (D5), T-4 in its interim form (D6), T-8 deadline share (D7), T-10 without
  the record-marker part (D10), T-11 with two of the four fixtures (D15), T-14 deadline share (D16), T-15 deadline
  share (D8, D9, D14), T-16 as a pin (D17), T-19 deadline share without `tick_blocked_until` (D11), T-20 settle-cancel
  share (D13), T-21 without the #516-after-resume part (D12).
- **Already landed:** T-7 and T-17 in 1c (#1042); T-12 reachable part and T-13 in 1d-1 (#1049).
- **Deferred to 1d-3:** T-4 reconcile-required form, T-8 record ordering, T-9, T-10 record-marker part, T-12 wired
  part, T-14 record share, T-15 post-decision record part, T-18, T-20 retention parts, T-22 reconcile edges, and the
  `dev_loop_reconcile_required` fixture.
- **Deferred to 1d-4:** T-5, T-6, T-15 grace/read-error/`confirm_no_pr` parts, T-19 grace/read-error and
  `tick_blocked_until` parts (with (am), (ao)), T-21 #516-after-resume, the T-22 grace-to-deadline part, T-23, and the
  `dev_loop_no_pr_confirmed` fixture.

## Rollback

- **Before any release.** Nothing is released or deployed by this proposal (the release hold is ON), so before a
  release the rollback is a plain revert of the PR. The revert also reverts E1-E3 and removes the two fixtures. No
  production history carries the marker (worker tag `1.117.0`).
- **After a later release carrying this slice.** Do not revert below it while watches whose first run recorded
  `merge-watch-terminal-reconcile` are inside their deadline decision, or are closed but still queried. A worker below
  this slice replaying such a history hits a nondeterminism error. Either keep the branch and stop new adoption with
  `workflow.deprecate_patch` in a follow-up deploy, or let those runs drain first (visibility listing on
  `DevLoopWorkflow`). A worker below this slice that continues a hopped watch drops `gate_ran_head` from the record,
  which is the fail-open direction.
- **Claims left by the interim end.** Claims retained by an interim `MergeWatchReconcileUnrecorded` end are recovered
  by the lifecycle store's existing dead-owner reaping (liveness bound, about 10 h). No manual release is part of this
  rollback.
- **B4.** Nothing here decides B4 (#1007).
