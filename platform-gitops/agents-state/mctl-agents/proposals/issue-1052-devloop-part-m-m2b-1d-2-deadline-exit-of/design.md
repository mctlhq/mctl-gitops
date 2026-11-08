# Design: issue-1052-devloop-part-m-m2b-1d-2-deadline-exit-of

## Current state

Paths and lines are read on main `55b4633` (the merge of PR #1049, M2b-1d-1). That is the clone HEAD and the baseline
for this slice. `orchestrator/temporal/workflows/dev_loop.py` has 7050 lines.

### The merge watch

- **Loop and deadline.** `_watch_pr` (line 6485) takes `deadline` from `resume.deadline` (line 6531) or computes
  `workflow.now() + MERGE_WATCH_DEADLINE` (line 6533).
  - It loops on `while workflow.now() < deadline and not self._abandoned:` (line 6670) inside a `try` and sleeps
    `cadence.poll_interval` at the bottom (line 6953).
  - The loop has no `else:`. When the condition goes false, control falls into `finally` (line 6954). That block
    settles the tick and the gate, then writes `release`, or `terminal` if `watch.last` is MERGED/CLOSED, when
    `not hopping and watch.track_ownership and self._owned_entity_id` holds (line 6973).
  - It then returns `_WatchOutcome(last=watch.last, ended=watch_ended)` (line 7050).
  - Nothing reads the PR after the deadline. **This is the defect** that #1029 pins.
- **Marker (M2b-1b).** `MERGE_WATCH_RECONCILE_PATCH = "merge-watch-terminal-reconcile"` (line 489) is evaluated only in
  the fresh-start arm (line 6611). It is carried as `MergeWatchResume.terminal_reconcile: bool = False` (line 1674), read
  in the resume arm (line 6552), put into the hop record (line 6711), and stored on `_MergeWatchRun.terminal_reconcile`
  (line 1810). No code branches on it yet.
- **Per-run state.** `_MergeWatchRun` (line 1797) is a plain holder that is never serialized: `last`,
  `polls_without_pr`, `terminal_status_polls`, `saw_open_pr`, `track_ownership`, `poll_index`, `terminal_reconcile`,
  `tick_task` and `gate_task`.
- **Helpers from 1b.**
  - `_apply_found_state(state, watch)` (line 6442) does the found-branch bookkeeping, including `_track_ownership`.
  - `_terminal_claim(state, watch)` (line 6465) is the in-loop `terminal` write plus `_finish_claim`, which clears
    `_owned_entity_id`, so `finally` does not write twice.
  - The in-loop MERGED/CLOSED exit is at line 6784.
- **Settles.**
  - `_settle_tick` (line 5223) and `_settle_gate` (line 5453) cancel an in-flight task and then `await task` inside
    `except asyncio.CancelledError`. That handler would also absorb an outer workflow cancel.
  - Cancelling the gate propagates into `run_gated_action`'s child `ActionApprovalWaitWorkflow`.
  - Per the `_settle_gate` docstring, a consume that is already running still runs `gh pr merge` after the cancel.
- **Gate bookkeeping.**
  - `_gate_head` is set when an attempt starts (line 6885).
  - `_record_gate_result` (line 5416) sets `_gate_settled_head = _gate_head` (line 5433) on a settled outcome or on
    `ran`.
  - Nothing records "a gate ran at head H" separately from "a human settled H".
- **Exits that skip the deadline path.** These return or break without reaching it:
  - MERGED/CLOSED (line 6784);
  - the non-transient read error (`return _WatchOutcome(last=watch.last)`, line ~6768);
  - the grace polls;
  - the #516 break;
  - the hop break.

### Result, deliveries and run exit

- **1d-1 typed result.**
  - `WATCH_END_FINAL_READ`, `WATCH_END_RECONCILE_REQUIRED`, `WATCH_END_NO_PR_CONFIRMED` and
    `WATCH_END_ABANDONED_UNVERIFIED` are defined at lines 1157-1160.
  - `MERGE_WATCH_RECONCILE_REFUSAL = "merge-watch-reconcile-required"` is defined at line 503.
  - `self._reconcile_required = False` is set at line 2019, and nothing sets it True.
  - `_finish_after_watch` (line 4685) passes `outcome.watch_end` through.
- **`_deliver` (line 2924), verified for V1.**
  - It checks `_reconcile_required` before the decision wait (line 3005) and after it (line 3013).
  - It waits on `self._abandoned or self._is_approved() or self._gates_passed or self._exiting or self._hopping`.
  - It then computes `decided = (self._is_approved() or self._gates_passed) and not self._abandoned`.
  - So on any run end where the flag is unset, a delivery still waiting (for example one whose bind is still polling
    when `_settle_deliveries` sets `_exiting`, line 3109) lands `Succeeded` on a loop that has been approved. That
    includes a new interim Failed end. **V1 is confirmed in the code.**
- **`run` (line 3635).** It catches `(Exception, asyncio.CancelledError)`, ends the canonical execution and the
  deliveries, and re-raises. A raised `ApplicationError` and a cancellation therefore both settle deliveries before the
  run ends.
- **V2, confirmed in the code.** `finally` has no state other than `hopping` that suppresses the relinquishing write.
  If the deadline decision awaits a timer and the workflow is cancelled, the `CancelledError` unwinds through `finally`,
  and `finally` writes `release`.
- **V3.** Nothing in the workflow uses `is_cancelled_exception`. The in-loop read classifier is `_is_transient`
  (line 1470). A new `except ActivityError` around a final-read attempt would also catch a cancelled activity, unless
  it re-raises. #1021 assigns that re-raise to 1d-3 (its mutation (y)).
- **Activities.** `record_merge_watch_reconcile` and `confirm_no_pr` are registered in `orchestrator/temporal/worker.py`
  and have no caller (1c).
- **Restart.**
  - `start.py:33` uses `DEV_LOOP_ID_REUSE_POLICY = ALLOW_DUPLICATE_FAILED_ONLY` for intake, via
    `start_dev_loop_workflow`. Its callers are `run_issue_poller.py:235`, `run_issue_directive_poller.py:1201` and
    `cli.py:37`.
  - `restart_if_restartable` (`start.py:107`, called from `cli.py:42`) reads a COMPLETED run only (`start.py:136`).
  - **Only intake can start a new run on the id of a Failed or Cancelled run.** `restart_if_restartable` does not
    handle FAILED.

### Tests that bear on this slice

Line numbers are corrected against `55b4633`.

- `tests/test_merge_watch_worker_gap.py` (#1030). `_resume_record(t0, offset)` (line 135) does not set
  `terminal_reconcile`, so the field defaults to False. Scenario A, `test_deadline_in_gap_ends_watch_without_reading_merged`
  (line 304), is the defect pin: it expects one read and `OPEN`. Scenario B (line 319) and
  `test_resume_record_fields_reach_the_merge_watch_path` (line 330) are controls.
- `tests/test_dev_loop_workflow.py`. These fresh runs end on the deadline, so the marker evaluates True under the new
  code:
  - `test_merge_detection_deadline_returns_last_open_state` (line 4068) stays green, because the final read is OPEN.
  - `test_deadline_is_carried_not_recomputed_across_hops` (line 7863) stays green, within its `<= 5` read bound.
  - `test_merge_detection_survives_read_failures_until_deadline` (line 4103) goes red: every final read fails. This is
    E1.
  - The abandon test is at line 2219. The merge-gate harness with a never-deciding `read_action_approval` fake is at
    lines 8170-8190.
- `tests/test_pre_m1_compat.py`.
  - `M1_ADDED` (line 151, with the `MergeWatchResume` row at line 154) is proven by
    `test_the_pre_m1_field_sets_are_m1_minus_exactly_these` (line 479). That requires E2.
  - `_recorded_dev_loop_histories` is defined at line 581, and its flat glob is at **line 584**. The #1051 proposal
    cited 581, the def line.
- `tests/test_workflow_replay.py`. `_STANDALONE_FIXTURES` is at line 576, and
  `test_every_recorded_fixture_belongs_to_a_scenario` is at line 599, with its flat glob at **line 607**.
- `tests/test_execution_request_replay.py`. The flat globs are at **lines 376, 433, 476, 534, 686 and 731**; #1051
  cited 374/431/474/530/685/728. None of these globs looks into a subdirectory, and `pre_m1/` already is one.
- `tests/test_merge_watch_typed_result.py`.
  - `test_nothing_in_production_sets_the_flag_or_a_watch_end` (line 79) is a "1d-1-only scan". That requires E3.
  - The delivery harness is `_deliver_with`, with the test-only `_FlaggedLoop` class (lines ~240-350). It starts a
    continued run carrying an open delivery and is the pattern D18 reuses.
- `tests/test_execution_request_dispatch.py:1612` and `tests/test_execution_request_resume.py:824` already cancel
  through `handle.cancel()` and assert `WorkflowExecutionStatus.CANCELED`. That is the pattern D13 uses.
- `grep -rl merge-watch-terminal-reconcile tests/fixtures` returns nothing.

### SDK

- `uv.lock` pins `temporalio==1.34.0` (lines 478 and 940). The interpreter in this run imports 1.34.0 from
  `/app/.venv`.
- Checked on 1.34.0: `workflow.wait(fs, *, timeout=None, return_when=...)` exists, and so does
  `temporalio.exceptions.is_cancelled_exception`.
- The #1051 investigation read SDK behaviour on 1.31.0, a mismatch the owner flagged. This proposal relies only on
  facts checked on 1.34.0. The cancel surface in V3 is pinned by a test (Q6), not assumed.

### Deployed state checked

- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml:27`: `tag: "1.117.0"`.
- `.../mctl-agents-worker-exec/values.yaml:34` and `.../mctl-agents-worker-implement/values.yaml:57`: both `1.117.0`.
- `CHANGELOG.md` and `.release-please-manifest.json` in the clone: the latest release is `1.117.0` (2026-11-03), and
  #1039, #1042 and #1049 are not in it. So no deployed worker runs code that records `merge-watch-terminal-reconcile`,
  and no production history carries it.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/issue-1021-*`, `issue-1046-*` and `issue-1051-*` were read. The
  #1051 triplet is the predecessor whose verified findings V1-V3 this proposal answers.
- Not observed in this run:
  - The mctl MCP tools were not called. The slice changes no runtime configuration and deploys nothing.
  - `gh` was not used, so the state of #1029, #1025 and #1020 and the implementer cap were not re-read (Q4).
  - mctl-api's `restartIfAbandoned` was not re-read (Q5).
  - `git show 883b3a1bf` is unavailable in this shallow clone. The marker's presence is read from the source instead.

## Proposed solution

All production changes are in `orchestrator/temporal/workflows/dev_loop.py`, on top of `55b4633`. The slice adds no
activity, CWFT, env var or `workflow.patched` marker.

### 1. Constants and state

- `FINAL_READ_ATTEMPTS = 3` and `FINAL_READ_BACKOFF = timedelta(minutes=2)`, placed beside `PR_STATE_TIMEOUT`.
- `MERGE_WATCH_RECONCILE_UNRECORDED = "MergeWatchReconcileUnrecorded"`, used as the `ApplicationError` type and as the
  log tag.
- `GATED_ACTIVITY_TIMEOUT`, imported from `action_approval` (line 132 there), like `DEFAULT_MAX_WAIT_SECONDS`.
- `self._watch_unrecorded = False`, set in `__init__`. This is the interim retention flag (R8).
  - It is an instance field because `_deliver` reads it.
  - It is not serialized and not carried across a hop: no hop happens during a decision.
  - It is deliberately neither `_reconcile_required` nor `_retain_claim`. 1d-3 replaces it with `_retain_claim` and
    the record.
- `self._gate_ran_head = ""`, set in `__init__`. `_record_gate_result` sets `self._gate_ran_head = self._gate_head`
  when `result.ran`. A matching field `MergeWatchResume.gate_ran_head: str = ""` is filled in the hop record and
  rehydrated in `_resume_merge_watch` next to `merge_gate_settled_head` (line 4619). It is instance state and issues no
  command.
- `@dataclass(frozen=True) class _FinalRead`, with fields `fresh: PRState | None`, `abandoned: bool` and
  `last_not_found: PRState | None`. `last_not_found` is unused here and kept for 1d-4.
- `@dataclass(frozen=True) class _WatchDecision`, with fields `kind: str` (one of `final`, `open`, `abandoned`,
  `unrecorded`) and `last: PRState | None`.

### 2. Helpers

```python
async def _wait_unless_abandoned(self, duration: timedelta) -> bool:
    if self._abandoned:
        return True
    if duration <= timedelta(0):
        return False
    try:
        await workflow.wait_condition(lambda: self._abandoned, timeout=duration)
        return True
    except TimeoutError:
        return False          # a workflow cancel is NOT caught: CancelledError propagates (R11)

async def _settle_watch_work(self, watch, service, slug) -> bool:
    in_flight = [t for t in (watch.tick_task, watch.gate_task) if t is not None and not t.done()]
    for t in in_flight:
        t.cancel()
    if in_flight:
        await workflow.wait(in_flight)     # an outer cancel raises HERE, not absorbed (mutation (ai))
    await self._settle_tick(watch.tick_task, service, slug)      # done() branch: drain only
    await self._settle_gate(watch.gate_task, service, slug, repo=..., number=..., poll_index=watch.poll_index)
    watch.tick_task = None
    watch.gate_task = None
    return bool(in_flight)

async def _final_pr_read(self, watch, service, slug) -> _FinalRead:
    last_not_found = None
    for attempt in range(FINAL_READ_ATTEMPTS):
        if attempt and await self._wait_unless_abandoned(FINAL_READ_BACKOFF):
            return _FinalRead(None, True, last_not_found)
        try:
            state = await workflow.execute_activity(get_pr_state, args=[service, slug],
                start_to_close_timeout=PR_STATE_TIMEOUT, retry_policy=PR_STATE_RETRY_POLICY)
        except ActivityError:
            state = None       # includes a cancelled attempt: accepted interim limit R12 (V3); 1d-3 adds (y)
        if state is not None and state.found:
            await self._apply_found_state(state, watch)
            terminal = state.state in ("MERGED", "CLOSED")
            return _FinalRead(state, self._abandoned and not terminal, last_not_found)
        if state is not None:
            last_not_found = state
        if self._abandoned:
            return _FinalRead(None, True, last_not_found)
    return _FinalRead(None, False, last_not_found)
```

`workflow.wait` is used rather than `asyncio.wait`, because it is the deterministic one. The `repo` and `number`
arguments are the ones `finally` passes today. `_settle_gate`'s `done()` branch runs `_finish_gate`, so
`MERGE_APPROVED` is logged and `_gate_ran_head` is set before the read.

### 3. The decision

This is the deadline subset of #1021's `_decide_watch_end`.

```python
async def _decide_watch_end(self, exit_name, watch, service, slug) -> _WatchDecision:
    assert exit_name == "deadline"          # noqa: S101 -- the other exits are 1d-4
    self._watch_unrecorded = True           # R8: from decision START (closes V2; N2 moves this to R7)
    unobserved = await self._settle_watch_work(watch, service, slug)
    settled_at = workflow.now()
    if self._abandoned:
        return self._settled(_WatchDecision("abandoned", watch.last))        # (al, first)
    read = await self._final_pr_read(watch, service, slug)
    if read.abandoned:
        return self._settled(_WatchDecision("abandoned", read.fresh or watch.last))
    fresh = read.fresh
    if fresh is not None and fresh.state == "OPEN" and fresh.head_sha and fresh.head_sha == self._gate_ran_head:
        unobserved = True                                                     # R6
    if unobserved and (fresh is None or fresh.state == "OPEN"):
        if await self._wait_unless_abandoned(settled_at + GATED_ACTIVITY_TIMEOUT - workflow.now()):
            return self._settled(_WatchDecision("abandoned", fresh or watch.last))
        read = await self._final_pr_read(watch, service, slug)
        if read.abandoned:
            return self._settled(_WatchDecision("abandoned", read.fresh or watch.last))
        fresh = read.fresh
    if fresh is not None and fresh.state in ("MERGED", "CLOSED"):
        await self._terminal_claim(fresh, watch)
        return self._settled(_WatchDecision("final", fresh))
    if fresh is not None and not unobserved:
        return self._settled(_WatchDecision("open", fresh))
    if self._abandoned:
        return self._settled(_WatchDecision("abandoned", fresh or watch.last))
    return _WatchDecision("unrecorded", fresh or watch.last)                  # flag stays True (R7)
```

`_settled(d)` sets `self._watch_unrecorded = False` and returns `d`. An exception or cancel anywhere inside the
decision leaves the flag True.

### 4. Wiring in `_watch_pr`

A local `watch_end = ""` and `decision_kind = ""` are declared beside `watch_ended`. An `else:` is added to the existing
`while`, inside the `try`. Python runs it only when the condition goes false, never after `break` or `return`.

```python
else:
    if watch.terminal_reconcile:                     # R17: unpatched histories issue no new command
        if self._abandoned:
            watch_end = WATCH_END_ABANDONED_UNVERIFIED                   # R15, no command
        else:
            decision = await self._decide_watch_end("deadline", watch, service, slug)
            decision_kind = decision.kind
            if decision.last is not None:
                watch.last = decision.last
            if decision.kind == "final":
                return _WatchOutcome(last=decision.last, watch_end=WATCH_END_FINAL_READ)
            watch_end = {"open": WATCH_END_FINAL_READ,
                         "abandoned": WATCH_END_ABANDONED_UNVERIFIED}.get(decision.kind, "")
```

- **`finally`.** The relinquishing guard becomes
  `if not hopping and not self._watch_unrecorded and watch.track_ownership and self._owned_entity_id:`. When the flag
  is set, `finally` logs
  `MERGE_WATCH_RECONCILE_UNRECORDED repo=... workflow=... exit=deadline last=<state/url/head or none>` and skips
  `_report_claim_abandonment`, so nothing is released and nothing is recorded. The two settle calls stay. They find
  None after a completed settle. After a cancel inside `workflow.wait`, they cancel-and-await tasks that are already
  cancelled, which is today's absorbing path and harmless in `finally`.
- **After `finally`, before the `hopping` return.**
  `if decision_kind == "unrecorded": raise ApplicationError("merge watch deadline: pull-request state not established; claim retained", type=MERGE_WATCH_RECONCILE_UNRECORDED, non_retryable=True)`.
  On a cancel this line is never reached, because the `CancelledError` already propagates.
- **Final return.** `return _WatchOutcome(last=watch.last, ended=watch_ended, watch_end=watch_end)`.
- **`_finish_after_watch` is unchanged.**

### 5. Deliveries (closes V1)

Two edits in `_deliver`, both expressions only:

```python
await workflow.wait_condition(
    lambda: self._abandoned
    or ((self._is_approved() or self._gates_passed) and not self._watch_unrecorded)
    or self._exiting or self._hopping
)
...
decided = (self._is_approved() or self._gates_passed) and not self._abandoned and not self._watch_unrecorded
```

Effects:

- A delivery that reaches its wait during a decision holds until the decision settles.
  - If the decision ends `final` or `open`, the flag clears and the delivery lands as today.
  - On the interim Failed end or a cancel, `run`'s `except` calls `_settle_deliveries`, which sets `_exiting`. The
    delivery then lands `Failed` with an empty refusal (Q3).
- `_reconcile_required` and its two checks are untouched.
- `wait_condition` issues no command, and the flag is only ever True on the marker path, so no existing history
  changes shape.
- The `_in_delivery_wait` helper in `tests/test_merge_watch_typed_result.py` locates the lambda by code position
  inside `_deliver`, so it still finds it.
- Deliveries that landed before the deadline are already terminal, which is today's behaviour, and are not revisited.

### 6. Cancellation, V1-V3 at a glance

| Moment of the workflow cancel | Status | Lifecycle write | Deliveries | Pinned by |
|---|---|---|---|---|
| Settle's `workflow.wait` on a cancelled gate | Cancelled | none (flag True) | Failed | D13 |
| Final-read backoff timer | Cancelled | none | Failed | D13b |
| R6 window timer | Cancelled | none | Failed | D13c |
| A running final-read activity (V3) | not Cancelled: decision continues | `terminal` on fresh MERGED/CLOSED, `release` on fresh verified OPEN, none on unreadable (Failed) | Succeeded only if the decision settled, else Failed | D13d (interim limit, 1d-3 (y)) |
| Interim unreadable end (no cancel) | Failed `MergeWatchReconcileUnrecorded` | none | Failed | D6, D18 |

V3 is an accepted limit and not a defect against the STOP criterion:

- **No stale success.** Every Completed outcome rests on a read taken after the cancel.
- **No release on an unknown state.** A `release` happens only on a verified fresh OPEN with no unobserved attempt.
  That is the same condition as an uncancelled deadline end, and today's in-loop cancel also releases.
- **What is missing is only that the cancel is not honoured.** Fixing that needs #1021's `_final_pr_read` re-raise
  (y), which #1052 lists among the STOP items ("cancellation re-raises"). D13d pins the observed behaviour, so 1d-3
  must turn it red on purpose.

### 7. Marker: reuse, an owner-visible deviation

#1052 says "new `workflow.patched` marker for any command-order change". This slice instead **reuses
`merge-watch-terminal-reconcile`**, the single marker #1021 specifies for this line. This is a deviation from the
issue's wording and is named as such (Q1). Its basis:

- no deployed worker records the marker (tag `1.117.0`);
- no fixture records it;
- since `883b3a1bf`, every branch that consults it lands only inside unreleased code.

### 8. Gap harness and fixtures

- **Gap harness.** `_resume_record(t0, offset, *, terminal_reconcile: bool = False)`. The default keeps scenario B
  and the record-fields test unchanged.
  - Scenario A becomes `test_deadline_in_gap_reads_the_merged_pr_once_more`, with `terminal_reconcile=True`, and makes
    the R20 assertions.
  - The lifecycle ops are recorded by wrapping the factory's `lifecycle_ownership` fake, the way `_activities` wraps
    `get_pr_state`.
  - A new `test_unpatched_record_keeps_the_legacy_deadline_end` makes the R21 assertions.
  - The module docstring's "Scenario A" and "Honest limit" paragraphs are updated.
  - #1029 is closed by the owner only.
- **Red on current main.** On `55b4633` the converted test fails on `len(_pr_state_schedules(...)) == 2` /
  `pr.state == "MERGED"`, not on an import error: `terminal_reconcile` already exists on `MergeWatchResume`, and
  `WATCH_END_FINAL_READ` already exists from #1049.
- **Fixtures.**
  - `tests/fixtures/histories/merge_watch/dev_loop_final_read.json` is a fresh run: the marker is recorded once, then
    the deadline final read returns MERGED, followed by `terminal`.
  - `.../merge_watch/dev_loop_final_read_hop.json` is the last continued run of a hopped watch: zero marker events,
    `terminal_reconcile=True` in its input, and a deadline final read.
  - They are recorded by `tools/record_merge_watch_final_read.py`, in the style of `tools/record_pre_m1_histories.py`,
    with `MERGE_WATCH_DEADLINE` monkeypatched to 40 min and, for the hop variant, `MERGE_WATCH_HISTORY_FLOOR = 1`.
  - They are replayed by `tests/test_merge_watch_final_read.py`, part of the normal `uv run pytest` suite (the owner's
    condition). That test file also checks that today's code replays its own fresh recording.
  - The subdirectory is invisible to every flat glob (lines listed above), so no allow-list edit is needed. Owner
    ruled on #1051.
- **Old-history replay** is shown by the existing suites, which stay green and unedited apart from E2:
  `tests/test_workflow_replay.py`, `tests/test_execution_request_replay.py`, `tests/test_pre_m1_compat.py` and
  `tests/test_patch_memoization.py`.

### 9. Scope adjustments and sizing

- **Moved to 1d-4** (owner ruling on #1051): `tick_blocked_until` and mutations (am) and (ao). No deadline decision
  returns to the loop, so they cannot be observed here.
- **Pulled forward from 1d-3:** retention from the start of the decision, closing V2 (Q2). Only the flag scope comes
  forward, with no re-raise and no record.
- **Size.**
  - Production: about 230-280 lines in `dev_loop.py`, which is the #1051 estimate plus about 20 lines for the flag,
    `_settled` and the two `_deliver` expressions.
  - Tests: about 900-1100 lines, adding D13b-d and D18.
  - Plus 2 fixtures, 1 recorder, E1-E3 and 12 mutation runs.
  - For comparison, 1d-1 was 77 production lines and 428 test lines in one implementer pass (about 29 min). This slice
    is about 2.5 times that. **Judged to fit one bounded pass, with little margin.**
- **Pre-declared fallback split.** If the pass cannot finish, the implementer stops and reports; it does not trim tests.
  - 1d-2a: sections 1-6 and the gap harness, with D1-D14, D16-D18, and the mutations.
  - 1d-2b: the fixtures, the recorder and D15.
  - 1d-2a alone keeps every invariant, because fixtures add no behaviour.
- **Commit shape** (owner rule on #1025): a single implementation commit is acceptable. The red evidence is reproduced
  against the branch base with the production change stashed, and the command and output are pasted into the PR.

## Alternatives

1. **A new marker `merge-watch-deadline-final-read`.** It would literally follow #1052's wording. It was dropped for
   three reasons: it needs a second `MergeWatchResume` bool and another E2-style row, which is not among the accepted
   E1-E3; #1021 specifies one marker; and no deployed or committed history makes the reuse unsafe. The new marker
   stays available as the owner's choice (Q1).
2. **Close V3 with `if is_cancelled_exception(exc): raise` in `_final_pr_read`.** This is #1021 mutation (y), assigned
   to 1d-3, and it falls under #1052's STOP item "cancellation re-raises". It was dropped and pinned instead (D13d).
3. **Leave V2 as an interim limit (release on cancel during the decision).** This would keep 1d-3's retention scope
   out entirely. It was dropped because it violates the owner's stated STOP criterion: no release contrary to the
   fail-closed contract while an approved `gh pr merge` may be in flight. The closure costs one flag-placement line.
4. **Close V1 by setting `_reconcile_required` on the interim end.** This was dropped because #1052 forbids it, and the
   refusal it produces (`merge-watch-reconcile-required`) would claim a record that 1d-2 does not write.
5. **Do the final read in `finally` or `_finish_after_watch`.** This was dropped (#1021 alternative 2): `finally` must
   not decide after the write it guards, and the tail runs after the claim is gone.

## Platform impact

- **Replay.**
  - Pre-marker histories decode `terminal_reconcile=False`, so the `else:` body issues nothing. The new
    `_watch_unrecorded` flag stays False, so `_deliver` and `finally` behave identically. These histories are not
    re-recorded.
  - A history recorded by unreleased main from `883b3a1bf` up to this slice carries the marker but took the no-read
    exit. Replayed past that exit under this code, it would be nondeterministic. No production history or fixture is
    of that shape (tag `1.117.0`).
- **Old-worker consequence of the reused marker.** A history recorded by this slice that already contains
  deadline-decision commands, replayed by a worker below this slice, fails with nondeterminism. This applies to open
  runs in the settle, backoff or window (up to about 80 min past the deadline) and to queries against closed runs of
  that shape. **Rollback below this slice is unsafe for runs whose first run recorded the marker and that reached the
  deadline decision.** Rollback below `883b3a1bf` is already unsafe for any run that recorded the marker. Nothing here
  decides B4 (#1007).
- **Payload compatibility, both directions.**
  - `MergeWatchResume` gains `gate_ran_head` (default `""`).
    - New code reading an old record gets `""`.
    - An old worker reading a new record drops the key (pinned by
      `test_unsupported_direction_pre_m1_decoder_silently_drops_m1_fields`). A run continued that way misses a gate
      that ran but was not observed, which is fail-open, and only after a rollback.
  - `DevLoopResult` gains no field. `watch_end` now carries `final-read` and `abandoned-unverified`.
    - The 1d-1 CLI prints both (`test_cli_marks_an_unverified_abandoned_pr`).
    - An older reader (the shepherd, mctl-api, an old CLI) drops or ignores `watch_end`.
    - A newer reader of an old payload gets `""`.
    - `ended` and `implement`, the fields restart decisions read, are unchanged on every new path (Q5).
- **New end states, and restart.**
  - The run can now end `Failed` (`MergeWatchReconcileUnrecorded`) or `Cancelled` during a decision, in both cases
    with the claim retained until the lifecycle store's liveness bound (about 10 h after close).
  - Only intake, through `ALLOW_DUPLICATE_FAILED_ONLY`, can start a new run on that workflow id.
    `restart_if_restartable` handles COMPLETED only.
  - No detector exists yet. #1022 must cover these states, together with 1d-3's, before any release that carries
    1d-3. **Green tests are never grounds for lifting the release hold.**
- **Resources.** A patched deadline end adds 1-3 `get_pr_state` calls (up to 6 with the window) and up to 3 timers.
  That happens once per watch, so the cost is negligible.
- **Risks and mitigations.**
  - Other existing tests may be pushed onto the new path. Mitigation: task 2 runs the full suite with the change
    first, and any red test outside E1-E3 is a STOP.
  - The cancel surfaces may differ from those assumed. Mitigation: D13, D13b-d are written and observed before
    mutations (ai) and N2 are run.
  - Delivery holding during the decision could delay a delivery by up to about 80 min. This only affects deliveries
    open at the deadline and is acceptable for an interim.
- **Merge governance.**
  - The implementer PR must be verified as blocked by GitHub (the #1020 code-owner hold); if it is not blocked, stop.
  - Any HEAD change after review (including a shepherd push) needs re-verification and a fresh review.
  - No autonomous merge, admin bypass, release, deployment, Vault or GitOps rollout.
  - B4 stays FAIL and the release hold stays ON. #1003, gitops#2394 and mctl-api#934 stay Draft.
  - 1d-3 and 1d-4 are not started until this slice is resolved.
