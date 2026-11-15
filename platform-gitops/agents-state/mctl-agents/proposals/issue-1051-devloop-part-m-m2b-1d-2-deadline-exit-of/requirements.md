# DevLoop Part M, M2b-1d-2: deadline exit of the merge watch, and the gap-harness regression (#1021 slice)

## Context

Issue #1051 asks for slice M2b-1d-2 of the sequential plan recorded on #1021 and split in #1046. The scope is the
1d-2 row of the #1046 table: the merge watch's deadline exit gets a settle, a final PR read and a decision; an
unreadable final read gets an interim fail-closed end; the defect pin in the gap harness
(`tests/test_merge_watch_worker_gap.py`, #1029 / PR #1030) becomes a regression test; and two replay fixtures are
added. The specification is the approved #1021 proposal
(`platform-gitops/agents-state/mctl-agents/proposals/issue-1021-devloop-part-m-m2b-feedback-tick-and-dea/`, digest
`sha256:e833d2af0ce3ce1e30699e6a77d221ba34af8948175c1ad75f2f0acd566fb144`, provenance only, not restarted and not
edited). This proposal is written against the PR #1049 head `9ac2ff4` (M2b-1d-1, not merged when this was written).
**Implementation cannot start until #1049 is merged on the owner's command.**

It matters because today `DevLoopWorkflow._watch_pr` (`orchestrator/temporal/workflows/dev_loop.py`) ends at the
14-day deadline with no read when the loop condition goes false. A worker gap that crosses the deadline therefore
ends the watch on a stale `OPEN` even though the PR was merged in the meantime. Scenario A of the gap harness pins
that: one `get_pr_state` call, `result.pr.state == "OPEN"`, while the fake already answers `MERGED`. Then the
`finally` block writes `release`, not `terminal`, and deploy observation and the security record never run.

The investigation found that the slice as scoped by #1051 **already meets the issue's first STOP condition**: three
existing test files need bounded edits to stay green (E1-E3 below). This proposal names the edits exactly so that the
owner can rule on them at approval time. The investigation also found two items of the 1d-2 row that cannot be observed
from the deadline exit (`tick_blocked_until`, mutations (am) and (ao)). It moves them to 1d-4, which narrows the slice
instead of widening it.

## User stories

- AS the owner of a DevLoop whose PR merged while no worker ran I WANT the watch to read the PR once more at the
  deadline SO THAT the loop reports MERGED, writes `terminal`, and runs deploy observation and the security record.
- AS an operator I WANT a deadline exit whose final read cannot be completed to fail loudly with the claim held SO
  THAT a stale `OPEN` is never reported as the final answer and nothing is released on an unknown state.
- AS the reviewer of the #1021 line I WANT the #1029 defect pin shown red before the change and green after it SO THAT
  the gap is proven fixed, not assumed fixed.
- AS a release owner I WANT every pre-change history to replay unchanged, the replay consequence of the marker stated,
  and no release implied SO THAT B4 (#1007) and the release hold are not affected.

## Acceptance criteria (EARS)

Scope gate

- R0a. WHILE PR #1049 is not merged on main THE SYSTEM SHALL have no implementation of this proposal started.
- R0b. IF making the change green needs any edit of an existing test or replay fixture other than E1, E2, E3, the
  gap-harness pin and the two named fixtures THEN the implementer SHALL stop and report on #1051 with no workaround.
  The edits are: E1, the final assertions of
  `tests/test_dev_loop_workflow.py::TestDevLoopWorkflow::test_merge_detection_survives_read_failures_until_deadline`;
  E2, the `M1_ADDED` / `M1_DEFAULTS` rows for `MergeWatchResume.gate_ran_head` in `tests/test_pre_m1_compat.py`; E3,
  removal of the `_WatchOutcome(watch_end=...)` half of `test_nothing_in_production_sets_the_flag_or_a_watch_end` in
  `tests/test_merge_watch_typed_result.py`.
- R0c. IF the owner's approval of this proposal's digest does not accept E1-E3 THEN the implementer SHALL stop at task
  0 and report. Approval of this digest is defined as accepting exactly E1-E3 and nothing else.

Deadline exit (marker `merge-watch-terminal-reconcile`, carried as `terminal_reconcile`)

- R1. WHEN the `while workflow.now() < deadline and not self._abandoned` loop of `_watch_pr` ends because its condition
  went false, and `watch.terminal_reconcile` is True and `self._abandoned` is False, THE SYSTEM SHALL decide the end
  through `_decide_watch_end("deadline", ...)` before the `finally` block runs. The decision must not run after a hop
  `break`, after the #516 terminal-status `break`, or after any `return`.
- R2. WHEN the deadline decision starts THE SYSTEM SHALL first settle the in-flight shepherd tick and merge gate
  (`_settle_watch_work`: cancel, `workflow.wait` on the cancelled tasks only if at least one was in flight, then drain
  through `_settle_tick` / `_settle_gate` with the real `watch.poll_index`). It then sets both task references to None
  and only after that issues the first final read.
- R3. WHEN the final read runs THE SYSTEM SHALL call `get_pr_state` at most `FINAL_READ_ATTEMPTS = 3` times
  (`PR_STATE_TIMEOUT`, `PR_STATE_RETRY_POLICY`), with a `FINAL_READ_BACKOFF = 2 min` abandon-aware wait between attempts.
  It SHALL apply `_apply_found_state` to the first found state and return it. Any `ActivityError` and any `found=False`
  counts as a failed attempt.
- R4. IF a final read returns MERGED or CLOSED THEN THE SYSTEM SHALL write the lifecycle `terminal` op through
  `_terminal_claim` and end with that state, `watch_end == "final-read"`, and the existing tail (deploy observation,
  `security-record-landed`, incident watch on MERGED).
- R5. IF a final read returns OPEN and no own attempt is unobserved THEN THE SYSTEM SHALL end with the fresh OPEN state
  and `watch_end == "final-read"`, and the `finally` block SHALL write today's `release`.
- R6. WHILE an own attempt is unobserved THE SYSTEM SHALL not treat a found OPEN as final. An attempt is unobserved
  when the settle found a tick or gate in flight, or when the fresh OPEN head equals a non-empty `_gate_ran_head`. In
  that case it SHALL wait, abandon-aware, until `settled_at + GATED_ACTIVITY_TIMEOUT`, and then run one more final-read
  set.
- R7. IF the final-read set yields no found state, or yields OPEN while an attempt is still unobserved, THEN THE SYSTEM
  SHALL (interim, replaced in 1d-3) skip every relinquishing lifecycle write, log `MERGE_WATCH_RECONCILE_UNRECORDED`,
  and, after `finally`, raise `ApplicationError(type="MergeWatchReconcileUnrecorded", non_retryable=True)`, so the run
  ends `Failed` with the claim retained.
- R8. WHILE deciding THE SYSTEM SHALL not set `self._reconcile_required`. It SHALL not schedule
  `record_merge_watch_reconcile` or `confirm_no_pr`, and SHALL add no heartbeat, backoff of a record, cancellation
  re-raise or `_retain_claim`.
- R9. IF `self._abandoned` is observed after the settle, after a final-read attempt that found no MERGED/CLOSED, during a
  backoff or during the R6 window THEN THE SYSTEM SHALL wake at once, make no further read, end with
  `watch_end == "abandoned-unverified"` (the last observed or fresh state in `last`) and write today's `release`.
- R10. WHEN the loop ends because of an abandon (the `else:` reached with `self._abandoned` True) THE SYSTEM SHALL make
  no final read and add no timer, and SHALL set `watch_end == "abandoned-unverified"`. `ended` stays
  `abandoned: <reason>` and the existing `release` is unchanged.
- R11. WHEN `_record_gate_result` records a result with `ran` True THE SYSTEM SHALL set `self._gate_ran_head` to the
  attempt's head. That head SHALL be carried across a hop in `MergeWatchResume.gate_ran_head: str = ""` and
  rehydrated by `_resume_merge_watch`.
- R12. WHILE `watch.terminal_reconcile` is False (every history recorded before the marker, and every resume record
  without the field) THE SYSTEM SHALL schedule exactly today's commands at the deadline exit.
- R13. WHEN a continued run starts past its carried deadline THE SYSTEM SHALL run the deadline decision at once, with
  the deadline never recomputed.

Gap harness, fixtures, replay

- R14. WHEN the gap harness runs scenario A with a resume record carrying `terminal_reconcile=True` THE SYSTEM SHALL
  schedule exactly two `get_pr_state` (one before the gap, one final read after it) and return `pr.state == "MERGED"`,
  `watch_end == "final-read"`, with a `terminal` op and no `release`. The test SHALL be shown red, failing on its
  `MERGED` assertion and not on an import error, on the main commit the implementation branches from, before the
  production change.
- R15. WHEN scenario A runs with `terminal_reconcile=False` THE SYSTEM SHALL keep today's end: one read, `OPEN`.
- R16. THE SYSTEM SHALL ship `dev_loop_final_read.json` (fresh start, marker recorded once, deadline final read MERGED)
  and `dev_loop_final_read_hop.json` (the continued run after a hop, no marker event, deadline final read). Both go in
  `tests/fixtures/histories/merge_watch/` and SHALL replay clean, with no existing fixture re-recorded.

Evidence

- R17. THE SYSTEM SHALL be accompanied by mutation proof for (a), (d), (e), (g), (v), (w), (x), (ac), (ai) and
  (al, first). Each mutation is applied locally, shown red with the expected test named, reverted, and absent from the
  diff.
- R18. IF the work does not fit one bounded implementer pass THEN the implementer SHALL stop and report with the split
  stated in `design.md` ("Sizing"), not widen.

## Out of scope

- The record (`_record_reconcile`, `record_merge_watch_reconcile` caller), `_reconcile_heartbeat`, record backoff,
  `_retain_claim`, the cancellation re-raises (including in `_ownership`), `_reconcile_required` being set, the
  `reconcile-required` result wiring, and the `dev_loop_reconcile_required` fixture: all 1d-3.
- The grace-polls and non-transient-read exits, `_no_pr_proven`, the `confirm_no_pr` caller, `no-pr-confirmed`, their
  abandon guards, the `dev_loop_no_pr_confirmed` fixture and the T-23 restart pins: all 1d-4.
- `tick_blocked_until` and its resume field, with mutations (am) and (ao): moved to 1d-4 by this proposal, because only a
  site that resumes the loop after a settle can observe them (see design, "Scope adjustments").
- Any change to `DevLoopResult` fields (1d-1 added them), `cli.py`, `activities/pr_state.py` or
  `activities/issue_state.py`.
- Any release, deployment, Vault or GitOps rollout, B4 decision (#1007), lifting the release hold, #1022, and
  undrafting #1003, gitops#2394 or mctl-api#934.

## Open questions

- Q1. **STOP finding, needs the owner's ruling (R0c).** E1: under the marker a fresh run's deadline final read fails on
  every attempt in `test_merge_detection_survives_read_failures_until_deadline` (its fake raises
  `ProposalListingError` from call 2 on). The interim therefore ends that run Failed, the opposite of the test's
  "never fail" assertion. E2: `test_the_pre_m1_field_sets_are_m1_minus_exactly_these` enforces that every new
  `MergeWatchResume` field is listed in `M1_ADDED`; slice 1b made the same edit for `terminal_reconcile`. E3: PR #1049
  declares its scan "1d-1-only: 1d-2 and 1d-3 remove it explicitly". The interpretation taken: approving this digest
  accepts exactly these three edits. If the owner does not accept them, the slice stops at task 0.
- Q2. "Red on current main". At the time of writing, main (`14645f9`) has no `WATCH_END_*` constants. The
  interpretation taken: red is shown on the main commit the implementation branches from, which must contain the #1049
  merge. The failure must be on the `MERGED` / read-count assertion. Red on `14645f9` itself is additionally shown for
  the `pr.state` / read-count assertions only, if the owner wants it.
- Q3. Fixture location. #1021 task 8 says to register the new fixtures in `_STANDALONE_FIXTURES`. A fresh recording
  carries `deferred-resume-contract`, and at least four flat-directory guards in `tests/test_execution_request_replay.py`
  and `tests/test_pre_m1_compat.py` would then fail. Each of those would be a further edit. The interpretation taken is
  a `merge_watch/` subdirectory, which no existing glob reads.
- Q4. Moving `tick_blocked_until`, (am) and (ao) to 1d-4 departs from the 1d-2 row of #1046. The reason is that they
  are unobservable here, and shipping dead code with a mutation that cannot go red would be false evidence.
- Q5. Interim limits that 1d-3 replaces. A workflow cancel delivered during a final-read activity is counted as a failed
  attempt, because the re-raises are 1d-3. The run can then end Failed (claim retained) instead of Cancelled. A cancel
  during the settle's `workflow.wait` ends Cancelled with today's `release`. A bound open delivery is not refused on the
  interim Failed end, because `_reconcile_required` stays unset. All three fail closed or keep today's line, and none
  reaches production while the hold is ON.
- Q6. Under `ALLOW_DUPLICATE_FAILED_ONLY` (`orchestrator/temporal/start.py:33`), intake can start a new run on the same
  issue-keyed workflow id after an interim Failed end. The owner id is the workflow id, so the new run may re-acquire the
  retained claim. This is accepted as the interim behaviour #1021 already describes for its Failed end. It is recorded,
  not changed.
- Q7. mctl-api `restartIfAbandoned` was not re-read in this run. Its "decodes `ended` and `implement` only" is taken
  from the #1021 and #1046 designs.
