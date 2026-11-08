# DevLoop Part M, M2b-1d-2: deadline exit of the merge watch, and the gap-harness regression (#1021 slice, successor of #1051)

## Context

Issue #1052 carries slice M2b-1d-2 of the sequential plan recorded on #1021 and split in #1046. It replaces #1051, whose
Temporal DevLoop ended `Completed` without a durable result and cannot be restarted. The scope is the 1d-2 row of the
#1046 table:

- the merge watch's deadline exit gets a settle, a final PR read and a decision;
- an unreadable final read gets an interim fail-closed end;
- the defect pin in the gap harness (`tests/test_merge_watch_worker_gap.py`, #1029 / PR #1030) becomes a regression
  test;
- two replay fixtures are added.

The specification is the approved #1021 proposal
(`platform-gitops/agents-state/mctl-agents/proposals/issue-1021-devloop-part-m-m2b-feedback-tick-and-dea/`, digest
`sha256:e833d2af0ce3ce1e30699e6a77d221ba34af8948175c1ad75f2f0acd566fb144`). It is cited as provenance only: #1021 is
not restarted and its files are not edited. This proposal is written against main `55b4633`, the merge of PR #1049
(M2b-1d-1). It carries over the owner's rulings on the #1051 proposal and answers the three verified findings
(V1-V3) listed on #1052.

Today `DevLoopWorkflow._watch_pr` (`orchestrator/temporal/workflows/dev_loop.py`) ends at the 14-day deadline with no
PR read once the loop condition goes false. If a worker gap crosses the deadline, the watch therefore ends on a stale
`OPEN` even though the PR merged in the meantime. Scenario A of the gap harness pins this: it expects one
`get_pr_state` call and `result.pr.state == "OPEN"`, while the fake already answers `MERGED`. The `finally` block then
writes `release`, not `terminal`, and neither deploy observation nor the security record runs.

## User stories

- AS the owner of a DevLoop whose PR merged while no worker ran I WANT the watch to read the PR once more at the
  deadline SO THAT the loop reports MERGED, writes `terminal`, and runs deploy observation and the security record.
- AS an operator I WANT a deadline exit whose final read fails, or which is cancelled while it decides, to keep the
  lifecycle claim and never report success SO THAT nothing is released or marked `Succeeded` while the PR state is
  unknown.
- AS the reviewer of the #1021 line I WANT the #1029 defect pin shown red on current main and green with the change
  SO THAT the gap is proven fixed, not assumed fixed.
- AS a release owner I WANT every pre-change history to replay unchanged, the replay and rollback consequences of the
  marker stated, and no release implied SO THAT B4 (#1007) and the release hold are not touched.

## Acceptance criteria (EARS)

### Scope gate

- R0a. IF making the change green needs any edit to an existing test or replay fixture other than E1, E2, E3, the
  gap-harness pin and the two named fixtures THEN the implementer SHALL stop and report on #1052 with no workaround.
  The owner accepted E1-E3 on #1051 as the only exceptions:
  - E1: the final assertions of
    `tests/test_dev_loop_workflow.py::TestDevLoopWorkflow::test_merge_detection_survives_read_failures_until_deadline`
    (line 4103).
  - E2: the `M1_ADDED` / `M1_DEFAULTS` rows for `MergeWatchResume.gate_ran_head` in `tests/test_pre_m1_compat.py`
    (`M1_ADDED` at line 151).
  - E3: removal of the `_WatchOutcome(watch_end=...)` half of `test_nothing_in_production_sets_the_flag_or_a_watch_end`
    in `tests/test_merge_watch_typed_result.py` (line 79).
- R0b. IF the work needs a record, a caller of `record_merge_watch_reconcile` or `confirm_no_pr`, a record backoff, a
  heartbeat, a cancellation re-raise, `tick_blocked_until`, or `_reconcile_required` being set THEN the implementer
  SHALL stop and report.
- R0c. IF the slice does not fit one bounded implementer pass THEN the implementer SHALL stop and report the split
  pre-declared in design.md section 9, not widen.

### Deadline exit

The deadline exit is gated by the existing marker `merge-watch-terminal-reconcile`, carried as `terminal_reconcile`.

- R1. WHEN the `while workflow.now() < deadline and not self._abandoned` loop of `_watch_pr` ends because its condition
  went false, `watch.terminal_reconcile` is True and `self._abandoned` is False, THE SYSTEM SHALL decide the end through
  `_decide_watch_end("deadline", ...)` before the `finally` block runs. It SHALL NOT decide after the hop `break`,
  after the #516 terminal-status `break`, or after any `return`.
- R2. WHEN the deadline decision starts THE SYSTEM SHALL first set the interim retention flag (R8). It SHALL then settle
  the in-flight shepherd tick and merge gate through `_settle_watch_work`:
  - cancel both;
  - `await workflow.wait(...)` on the cancelled tasks, only if at least one was in flight;
  - drain both through `_settle_tick` / `_settle_gate`, with the real `watch.poll_index`;
  - set both task references to None.

  Only after that SHALL it issue the first final read.
- R3. WHEN the final read runs THE SYSTEM SHALL call `get_pr_state` at most `FINAL_READ_ATTEMPTS = 3` times, with
  `PR_STATE_TIMEOUT` and `PR_STATE_RETRY_POLICY`. Between attempts it SHALL wait `FINAL_READ_BACKOFF = 2 min`, and the
  wait SHALL end early on abandon. THE SYSTEM SHALL apply `_apply_found_state` to the first found state and return
  that state. Any `ActivityError` and any `found=False` counts as one failed attempt.
- R4. IF a final read returns MERGED or CLOSED THEN THE SYSTEM SHALL write the lifecycle `terminal` op through
  `_terminal_claim`. It SHALL end with that state and `watch_end == "final-read"`, followed by the existing tail:
  deploy observation, `security-record-landed` and the incident watch on MERGED.
- R5. IF a final read returns OPEN and no own attempt is unobserved THEN THE SYSTEM SHALL end with the fresh OPEN state
  and `watch_end == "final-read"`, and the `finally` block SHALL write today's `release`.
- R6. WHILE an own attempt is unobserved THE SYSTEM SHALL NOT treat a found OPEN as final. An attempt is unobserved if
  the settle found a tick or gate in flight, or if the fresh OPEN head equals a non-empty `_gate_ran_head`. In that
  case THE SYSTEM SHALL wait until `settled_at + GATED_ACTIVITY_TIMEOUT` (the wait ends early on abandon) and then run
  one more final-read set.
- R7. IF the final-read set yields no found state, or yields OPEN while an attempt is still unobserved, THEN THE SYSTEM
  SHALL, as an interim end replaced in 1d-3:
  - keep the retention flag set;
  - skip every relinquishing lifecycle write;
  - log `MERGE_WATCH_RECONCILE_UNRECORDED`;
  - after `finally`, raise `ApplicationError(type="MergeWatchReconcileUnrecorded", non_retryable=True)`.

  The run therefore ends `Failed` with the claim retained.

### Retention, deliveries and cancellation (answers V1-V3)

- R8. WHILE the deadline decision is in progress THE SYSTEM SHALL hold `self._watch_unrecorded = True`. That holds from
  before the settle until the decision returns `final`, `open` or `abandoned`, and the flag is cleared only then. The
  flag is an instance field, not `_reconcile_required` and not `_retain_claim`.
- R9. WHILE `self._watch_unrecorded` is True THE SYSTEM SHALL issue no `release` and no `terminal` from `finally`, and
  SHALL log `MERGE_WATCH_RECONCILE_UNRECORDED` there instead. This holds whatever unwinds the watch: the R7 raise, a
  workflow cancellation, or an unexpected exception.
- R10 (closes V1). WHILE `self._watch_unrecorded` is True THE SYSTEM SHALL NOT land a resume delivery `Succeeded`:
  - `_deliver`'s decision wait SHALL NOT resolve on approval or gates alone while the flag is set;
  - `decided` SHALL include `and not self._watch_unrecorded`;
  - on the R7 Failed end and on a cancel during the decision, `run`'s `except` therefore lands each still-open
    delivery `Failed`.

  A delivery that is still waiting when the decision ends `final` or `open` SHALL land as today.
- R11 (closes V2). IF the workflow is cancelled during the settle's `workflow.wait`, a final-read backoff, or the R6
  window THEN THE SYSTEM SHALL end the run `Cancelled`. It SHALL write no `release` and no `terminal`, make no further
  `get_pr_state` call after the cancel, and land open deliveries `Failed`.
- R12 (V3, accepted interim limit). IF a workflow cancellation is delivered while a final-read `get_pr_state` activity
  is running THEN THE SYSTEM SHALL count the resulting `ActivityError` as a failed attempt. That is today's SDK
  behaviour and #1021 mutation (y) is not applied. The decision then continues under R3-R7 and R8-R10, with this
  consequence:
  - the run may end `Completed` on a fresh MERGED/CLOSED (`terminal`) or a fresh verified OPEN (`release`);
  - or it may end `Failed` with the claim retained;
  - it never ends on a stale state, and it never releases while the state is unknown.

  A pin test (D13d) SHALL assert this. 1d-3 replaces it with the re-raise.
- R13. WHILE deciding THE SYSTEM SHALL NOT set `self._reconcile_required`, SHALL NOT schedule
  `record_merge_watch_reconcile` or `confirm_no_pr`, and SHALL NOT use `is_cancelled_exception`. It SHALL add no
  heartbeat, no record backoff and no `_retain_claim`.

### Abandon, gate bookkeeping, replay

- R14. IF `self._abandoned` is observed at any of the following points THEN THE SYSTEM SHALL wake at once, make no
  further read, clear the retention flag, end with `watch_end == "abandoned-unverified"` (with the last observed or
  fresh state in `last`), and write today's `release`:
  - after the settle;
  - after a final-read attempt that found no MERGED/CLOSED;
  - during a backoff;
  - during the R6 window.

  A final read that returns MERGED/CLOSED under abandon SHALL still end under R4.
- R15. WHEN the `else:` of the loop is reached with `self._abandoned` True THE SYSTEM SHALL make no final read, add no
  timer, set no retention flag, and set `watch_end == "abandoned-unverified"`. `ended` SHALL stay
  `abandoned: <reason>` and `release` SHALL be unchanged.
- R16. WHEN `_record_gate_result` records a result with `ran` True THE SYSTEM SHALL set `self._gate_ran_head` to that
  attempt's head. The head SHALL be carried across a hop in `MergeWatchResume.gate_ran_head: str = ""` and rehydrated
  by `_resume_merge_watch`.
- R17. WHILE `watch.terminal_reconcile` is False THE SYSTEM SHALL schedule exactly today's commands at the deadline
  exit and return today's result. This covers every history recorded before the marker and every resume record
  without the field.
- R18. WHEN a continued run starts past its carried deadline THE SYSTEM SHALL run the deadline decision at once,
  without recomputing the deadline.
- R19. THE SYSTEM SHALL add no new `workflow.patched` marker. This is an owner-visible deviation from #1052's wording:
  see design.md section 7 and Q1.

### Gap harness, fixtures, evidence

- R20. WHEN the gap harness runs scenario A with a resume record carrying `terminal_reconcile=True` THE SYSTEM SHALL:
  - schedule exactly two `get_pr_state`, the second at or after `gap_end`;
  - return `pr.state == "MERGED"` and `watch_end == "final-read"`;
  - write `terminal` and no `release`.

  This test SHALL be shown red on main `55b4633` (or the later main commit the branch starts from) with no production
  change. It SHALL fail on the read-count / `MERGED` assertion, not on an import or setup error.
- R21. WHEN scenario A runs with `terminal_reconcile=False` THE SYSTEM SHALL keep today's end: one read and `OPEN`.
- R22. THE SYSTEM SHALL ship `tests/fixtures/histories/merge_watch/dev_loop_final_read.json` and
  `.../merge_watch/dev_loop_final_read_hop.json`. Both SHALL be replay-tested by a test in the normal CI suite (the
  owner's condition for the subdirectory), and no existing fixture SHALL be re-recorded.
- R23. THE SYSTEM SHALL be accompanied by mutation proof for (a), (d), (e), (g), (v), (w), (x), (ac), (ai) and
  (al, first), plus the slice-local N1 and N2 (tasks.md task 9). Each mutation SHALL be applied locally, shown red with
  the expected test named, reverted, and kept out of the diff. (am) and (ao) move to 1d-4 with `tick_blocked_until`,
  per the owner's ruling.

## Out of scope

- The following 1d-3 items:
  - the record (`_record_reconcile` and the `record_merge_watch_reconcile` caller), `_reconcile_heartbeat`, the record
    backoff and `_retain_claim`;
  - all cancellation re-raises, including the one in `_final_pr_read` (#1021 mutation (y)) and the ones in
    `_ownership` (aj);
  - setting `_reconcile_required` and the `reconcile-required` result wiring;
  - the `dev_loop_reconcile_required` fixture.
- The following 1d-4 items:
  - the grace-polls and non-transient read-error exits, `_no_pr_proven`, the `confirm_no_pr` caller and
    `no-pr-confirmed`;
  - `tick_blocked_until` with mutations (am) and (ao);
  - the `dev_loop_no_pr_confirmed` fixture and the T-23 restart pins.
- Any change to the fields of `DevLoopResult`, and any change to `orchestrator/temporal/cli.py`, `start.py`,
  `activities/pr_state.py` or `activities/issue_state.py`.
- Any release, deployment, Vault or GitOps rollout, any B4 decision (#1007), #1022, lifting the release hold, and
  undrafting #1003, gitops#2394 or mctl-api#934. Starting 1d-3 or 1d-4 is also out of scope.

## Open questions

- Q1. **Marker reuse (owner-visible deviation).** #1052 asks for "new `workflow.patched` marker for any command-order
  change". This proposal instead reuses the existing `merge-watch-terminal-reconcile` (M2b-1b), as #1021 specifies a
  single marker for this line.
  - Why it is sound: no deployed worker carries the marker. The worker tag is `1.117.0`, and #1039, #1042 and #1049 are
    absent from that release's changelog. No committed fixture carries the marker either.
  - The interpretation taken: approving this digest accepts the reuse.
  - If the owner wants a new marker instead: it is `merge-watch-deadline-final-read`, evaluated in the fresh arm and
    carried as a second `MergeWatchResume` bool. That costs one more E2-style row, which needs a fresh ruling.
- Q2. **V2 closure pulls one piece of 1d-3 forward.** Retaining the claim when a cancel arrives during the decision is
  part of what #1021 gives `_retain_claim` (mutation (z)). It is closed here with the interim flag only: no re-raise,
  no record, no `_ownership` change. The cancel already propagates on its own from timer waits and from
  `workflow.wait`. The interpretation taken is that this is not "behaviour from 1d-3" in the sense of R0b, because
  R0b's list (record, callers, backoff, heartbeat, re-raises) is untouched, and the alternative would leave the
  owner's STOP criterion violated. If the owner rules otherwise, the slice stops at task 0.
- Q3. A delivery refused on the interim end lands `Failed` with an empty refusal, as an abandoned one does. No new
  `delivery-<refusal>` reason is added, because a new reason would be a new vocabulary value for the surfaces.
  1d-3's `merge-watch-reconcile-required` refusal is not reused, because it would claim a record that does not exist.
- Q4. The implementer cap (#1025, $20 per the #1051 investigation) was not re-observed in this run. Sizing (design
  section 9) is judged against the 1d-1 pass.
- Q5. mctl-api's reader of `DevLoopResult` (`restartIfAbandoned`) was not re-read in this run. "Decodes `ended` and
  `implement` only" is taken from the #1021 and #1046 designs.
- Q6. V3's exact SDK surface was not executed in this run. On `temporalio==1.34.0` (installed and pinned), V3 says a
  workflow cancel during a running activity surfaces as `ActivityError` with a cancelled cause. D13d pins the
  behaviour actually observed. If it surfaces as `asyncio.CancelledError` instead, the run already ends `Cancelled`
  with the claim retained, the R12 limit does not exist, and D13d asserts that and is reported as such in the PR.
