# Tasks: issue-1052-devloop-part-m-m2b-1d-2-deadline-exit-of (slice 1d-2a: the deadline decision, inert)

This file implements slice M2b-1d-2a of #1021 (the first half of the 1d-2 split, carried by #1052, successor of #1051).

- The #1021 digest `sha256:e833d2af0ce3ce1e30699e6a77d221ba34af8948175c1ad75f2f0acd566fb144` is provenance only.
- The baseline is main `55b4633`, the merge of #1049.
- Under the owner rule on #1025, red-before and green-after evidence is mandatory. A single implementation commit is
  acceptable if the red runs can be reproduced (command and output go in the PR).
- This slice is inert: it adds no call site, edits no existing test, adds no payload field and no marker. The
  activation, its guards and every cancellation pin are 1d-2b.

## Implementation

- [ ] 0. Gate. Before writing code, confirm four things:
  - this proposal's digest is approved (not the superseded digest
    `sha256:512664c4d06c709be257ef053f2a94456b943389f157aac8fa73e9aee14c9d24` and not grant `aar_2191c03d35aa4db58a91833004490dac`);
  - that approval accepts the flag pull-forward (Q2) and that the abandon-before-decision guard and mutation (v)
    are a 1d-2b wiring question (design section 3);
  - the branch starts from main at or after `55b4633`;
  - #1051 is not approved or running.

  - DoD: if any check fails, nothing is committed and a report naming the failed check is posted on #1052.
- [ ] 1. Baseline. Run the full suite (`uv run pytest`) on the branch base and record that it is green. Locate the seam
  for the harness (design section 5): read `_FlaggedLoop` and its siblings and decide between overriding `_watch_pr` and
  `run`.
  - DoD: green baseline recorded. If no subclass can reach `_decide_watch_end` without a production edit beyond the
    design, stop and report (R0b).
- [ ] 2. Tests first (depends on 1). Write `tests/test_merge_watch_decision.py`: the harness, A1-A10 and D17a.
  - The test module must not import the new constants or helpers at module level (that would fail at collection, not
    per test): reference them as attributes of the imported `dev_loop` module inside the tests (`dev_loop.FINAL_READ_ATTEMPTS`).
  - DoD: A1-A10 are red against the base for the right reason (the helpers do not exist, so each test fails on the
    missing attribute at run time, not on a collection or setup error that would also fail after the change). D17a is green on the base only for the
    parts that describe today's code; the part that names the new helpers is red. The red run is reproduced in the PR.
- [ ] 3. State (depends on 2).
  - Add the constants, the `GATED_ACTIVITY_TIMEOUT` import, `self._watch_unrecorded` and `self._gate_ran_head` in
    `__init__`, the `_gate_ran_head` assignment in `_record_gate_result`, and the `_FinalRead` / `_WatchDecision`
    dataclasses.
  - DoD:
    - A10 is green;
    - every existing test and replay suite is green unedited;
    - `grep -c "workflow.patched(" orchestrator/temporal/workflows/dev_loop.py` is unchanged.
- [ ] 4. Helpers and decision (depends on 3). Add `_wait_unless_abandoned`, `_settle_watch_work`, `_final_pr_read`,
  `_settled` and `_decide_watch_end`, as written in design sections 2 and 3, with the `repo` / `number` arguments copied
  from the `finally` block.
  - DoD:
    - A1-A9 and D17a are green;
    - no `is_cancelled_exception`, no `_retain_claim`, no `tick_blocked_until`, no `_reconcile_required = True`, no
      scheduling of `record_merge_watch_reconcile` or `confirm_no_pr` (D17a);
    - `git diff` shows no change to `_watch_pr`, `_deliver` or the `finally` block.
- [ ] 5. Full suite (depends on 4). Run `uv run pytest` over the whole repository.
  - DoD: the suite is green.
  - STOP 1: if any existing test needed a change, stop and report on #1052.
  - STOP 4: if the pass cannot finish, stop and report (R0c); do not trim tests.
- [ ] 6. Mutation proof (depends on 5). Commit first, then for each mutation: apply it locally, run only
  `tests/test_merge_watch_decision.py`, confirm the named tests are red, revert, and confirm the mutation is absent from
  `git diff`. Paste the command and the failing test into the PR.

  | Mutation | Change | Expected red |
  |---|---|---|
  | (a) | the decision returns `open(watch.last)` without reading | A1, A2 |
  | (d) | treat a failed final read as OPEN (`fresh = watch.last` when nothing is found) | A4 |
  | (w) | run the first `_final_pr_read` before `_settle_watch_work` | A5, A7 |
  | (x) | return `open` for a found OPEN while `unobserved` | A7 (window OPEN, ran-head OPEN) |
  | (xr) | drop the `_gate_ran_head` comparison | A7 (ran-head) |
  | (win) | drop the window re-read | A7 (merge lands during the window) |
  | (ac) | skip `_apply_found_state` in `_final_pr_read` | A8 |
  | (al, first) | remove the `self._abandoned` check after the settle | A6 (i) |
  | (fl1) | do not set `_watch_unrecorded` at decision start | A9 |
  | (fl2) | `_settled` does not clear the flag | A9 |
  | (fl3) | clear the flag on the `unrecorded` return | A4, A9 |
  | (inert) | add a call to `_decide_watch_end` inside `_watch_pr` | D17a |
  | (ws) | measure the window from decision start instead of `settled_at` | A7 (window duration) |
  | (wt) | drop `workflow.wait(in_flight)` | A5, A7 (stubborn gate), if distinguishable |
  | (pc) | drop the pre-cancel loop in `_settle_watch_work` | A5, A7 (stubborn gate), if distinguishable |

  - A mutation that does not turn its named tests red is reported as such with its output, never claimed red. If a
    mutant proves equivalent, say so and why, and adjust the DoD in the PR; do not weaken the test to make it fail.
  - (v) is not a 1d-2a mutation (it is wiring, design section 3); it is run in 1d-2b.
  - DoD: the twelve rows above red with output; (ws) red; (wt) and (pc) red or reported equivalent with reasoning (design
    section 7); none of the mutations in the diff.
- [ ] 7. PR (depends on 6).
  - The description links #993, #1021 (digest as provenance only), #1046, #1049, #1051 (superseded), #1052 and this
    proposal's approved digest.
  - It contains:
    - the baseline-red evidence of task 2;
    - the statement that nothing calls the decision in production and why (design section 4), with the D17a result;
    - the harness limits (design section 5: no wiring, no real child workflow, no cancellation surface);
    - the mutation output;
    - the replay evidence (existing suites green and unedited).
  - It states:
    - the PR is blocked by the #1020 code-owner hold;
    - 1d-2b is the activation and owns S1/S2/S3 and #1029's conversion; #1029 stays open;
    - #1022 must be resolved before any release that carries 1d-3, and the release hold stays ON;
    - B4 stays FAIL;
    - #1003, gitops#2394 and mctl-api#934 stay Draft;
    - 1d-2b, 1d-3 and 1d-4 are not started.
  - DoD:
    - the PR is open and GitHub is verified to block it. If it is not blocked, stop.
    - any later HEAD change needs re-verification and a fresh review.
    - the implementer merges, releases and deploys nothing.

## Tests

All tests below are new and live in `tests/test_merge_watch_decision.py`. They run on
`WorkflowEnvironment.start_time_skipping()` with `_fake_activities` from `tests/test_dev_loop_workflow.py`, through the
test-only `DevLoopWorkflow` subclass of design section 5, and they count activities from history events
(`ACTIVITY_TASK_SCHEDULED`), not from fake calls.

- [ ] A1. Final read MERGED: kind `final`, exactly one read after the decision started, `terminal` written once, no
  `release`, `_watch_unrecorded` False afterwards.
- [ ] A2. Final read OPEN, nothing in flight: kind `open` with the fresh state, no window timer, no `terminal`, no
  `release` written by the decision, flag False.
- [ ] A3. Final read CLOSED: kind `final`, `terminal` written.
- [ ] A4. Unreadable final read, three variants run separately (every attempt raises the transient `ProposalListingError`;
  every attempt raises a non-transient error; every attempt returns `found=False`). Expect exactly `FINAL_READ_ATTEMPTS`
  reads with `FINAL_READ_BACKOFF` timers between them, kind `unrecorded`, flag True, no `release` or `terminal`, neither
  `record_merge_watch_reconcile` nor `confirm_no_pr` scheduled, and nothing raised by the decision.
- [ ] A5. Ordering, read from history. On the paths of A1-A4 only "`terminal` comes after the read that returned the
  terminal state" is non-vacuous (nothing is in flight). The settle-before-read ordering uses a stubborn gate: the
  harness's standing-in gate task blocks when cancelled until the test releases it; zero `get_pr_state` events while it
  is blocked, exactly one after the release.
- [ ] A6. Abandon, five cases:
  - (i) set before the decision: the settle runs, then no read, kind `abandoned`, flag False;
  - (ii) during a backoff: wakes at once, no further read;
  - (iii) during the window: same;
  - (iv) during a read that returns OPEN: kind `abandoned` with the fresh state;
  - (v) during a read that returns MERGED: kind `final`;
  - for (iv) and (v) the fake `get_pr_state` blocks until the test sends the abandon signal, then returns.
- [ ] A7. Own attempts:
  - a stubborn gate task (as in A5) standing in flight is cancelled and awaited before the first read;
  - the window timer's duration is asserted from history (not only its count), so a window measured from decision start
    is detected;
  - a merge that lands during the window gives a second read of MERGED and kind `final`;
  - OPEN after `GATED_ACTIVITY_TIMEOUT` gives `unrecorded`;
  - `_gate_ran_head` equal to the OPEN head gives `unrecorded`, and a different head gives `open`;
  - with nothing in flight there is no `workflow.wait` and no window timer.
- [ ] A8. Bookkeeping:
  - a final-read OPEN sets `_last_pr` and `saw_open_pr`, resets `polls_without_pr` and `terminal_status_polls`, and takes
    the claim through `_track_ownership`;
  - a MERGED first resolved by the final read, from a state with no claim, gives `acquire` then `terminal`, in that order.
- [ ] A9. Flag lifecycle, each asserted explicitly and read through the harness query: True while the decision is blocked
  in the settle, in a backoff and in the window; False after `final`, `open` and `abandoned`; True after `unrecorded`; True
  after an exception raised
  inside the decision (a harness override of `_apply_found_state` raising `ApplicationError`).
- [ ] A10. `_record_gate_result` with `ran` True sets `_gate_ran_head` to the attempt's head; with `ran` False it leaves it
  unchanged.
- [ ] D17a. Inertness pin (design section 4): an AST scan of `dev_loop.py` finds
  - no call site of `_decide_watch_end`, `_settle_watch_work`, `_final_pr_read` or `_wait_unless_abandoned` outside each
    other;
  - no `While.orelse` in `_watch_pr`, and no mention in `_watch_pr`, `_deliver` or the `finally` block of
    `_watch_unrecorded` or the helpers;
  - `_watch_unrecorded` only in `__init__`, `_decide_watch_end` and `_settled`;
  - none of `is_cancelled_exception`, `_retain_claim`, `tick_blocked_until`, `_reconcile_required = True`, or an
    `execute_activity` of `record_merge_watch_reconcile` / `confirm_no_pr`;
  - an AST count of `workflow.patched(` **calls** equal to the count on `55b4633` (not a text count: the module docstring
    mentions the string).

  The docstring says 1d-2b replaces this test with an activation pin.

Placement of the 23 #1021 tests:

- **In this slice (decision level only):** the decision shares of T-1, T-2, T-3 (A1-A3), T-4 interim form (A4), T-8
  deadline share (A5), T-15 deadline share (A6), T-19 deadline share without `tick_blocked_until` (A7), T-21 without its
  #516-after-resume part (A8).
- **In 1d-2b:** the wiring forms of the same tests; T-10 (hop), T-11 (two of four fixtures), T-14 deadline share, T-16
  pin, T-20 settle/backoff/window cancellation with retention (D13, D13b, D13c); D13d; D18 (V1 closure); the gap-harness
  conversion (T-1's end-to-end form).
- **Already landed:** T-7 and T-17 (1c, #1042); the reachable part of T-12, and T-13 (1d-1, #1049).
- **Deferred to 1d-3:** T-4 reconcile-required form, T-8 record ordering, T-9, T-10 record-marker part, T-12 wired part,
  T-14 record share, T-15 post-decision record part, T-18, T-22 reconcile edges; from T-20 the cancelled-activity
  re-raise (y), the record retry sleep and the running record activity; the `dev_loop_reconcile_required` fixture.
- **Deferred to 1d-4:** T-5, T-6; T-15 grace, read-error and `confirm_no_pr` parts; T-19 grace, read-error and
  `tick_blocked_until` parts with (am) and (ao); T-21 #516-after-resume, the T-22 grace-to-deadline part, T-23; the
  `dev_loop_no_pr_confirmed` fixture.

## Rollback

- **Before any release.** A plain revert of the PR. Nothing is released or deployed (release hold ON). The revert
  removes the new methods, the two fields, the one assignment in `_record_gate_result` and the new test file.
- **After a later release that carries this slice.** Nothing to protect: the code is unreachable and no history, payload
  or result changed. The rollback consequences begin with 1d-2b and are stated there.
- **B4.** Nothing here decides B4 (#1007).
