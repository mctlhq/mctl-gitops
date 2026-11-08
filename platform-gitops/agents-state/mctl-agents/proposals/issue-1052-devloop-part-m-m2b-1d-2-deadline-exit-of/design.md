# Design: issue-1052-devloop-part-m-m2b-1d-2-deadline-exit-of (slice 1d-2a: the deadline decision, inert)

## Current state

Paths and lines are read on main `55b4633` (the merge of PR #1049, M2b-1d-1), the baseline for this slice.
`orchestrator/temporal/workflows/dev_loop.py` has 7050 lines. The line numbers below were checked against that commit by
an independent read-only pass (2026-11-08); the only correction it found is marked.

### The merge watch

- **Loop and deadline.** `_watch_pr` (line 6485) takes `deadline` from `resume.deadline` (line 6531) or computes
  `workflow.now() + MERGE_WATCH_DEADLINE` (line 6533).
  - It loops on `while workflow.now() < deadline and not self._abandoned:` (line 6670) inside a `try` and sleeps
    `cadence.poll_interval` at the bottom (line 6953).
  - The loop has no `else:`. When the condition goes false, control falls into `finally` (line 6954). That block settles
    the tick and the gate, then writes `release`, or `terminal` if `watch.last` is MERGED/CLOSED, when
    `not hopping and watch.track_ownership and self._owned_entity_id` holds (**line 6974**; an earlier draft said 6973).
  - A second, separate guard `if not hopping and watch.track_ownership:` (line 7045) calls `_report_claim_abandonment`.
  - It then returns `_WatchOutcome(last=watch.last, ended=watch_ended)` (line 7050).
  - Nothing reads the PR after the deadline. **This is the defect** that #1029 pins.
- **Marker (M2b-1b).** `MERGE_WATCH_RECONCILE_PATCH = "merge-watch-terminal-reconcile"` (line 489) is evaluated only in
  the fresh-start arm (line 6611). It is carried as `MergeWatchResume.terminal_reconcile: bool = False` (line 1674), read
  in the resume arm (line 6552), put into the hop record (line 6711), and stored on `_MergeWatchRun.terminal_reconcile`
  (line 1810). No code branches on it yet.
- **Per-run state.** `_MergeWatchRun` (line 1797) is a plain holder, never serialized: `last`, `polls_without_pr`,
  `terminal_status_polls`, `saw_open_pr`, `track_ownership`, `poll_index`, `terminal_reconcile`, `tick_task`, `gate_task`.
  `test_merge_watch_run_shape` (`tests/test_dev_loop_workflow.py`, line 7649) pins this field list; this slice adds none.
- **Helpers from 1b.** `_apply_found_state(state, watch)` (line 6442) does the found-branch bookkeeping, including
  `_track_ownership`. `_terminal_claim(state, watch)` (line 6465) is the in-loop `terminal` write plus `_finish_claim`,
  which clears `_owned_entity_id`, so `finally` does not write twice.
- **Settles.** `_settle_tick` (line 5223) and `_settle_gate` (line 5453) cancel an in-flight task and then `await task`
  inside `except asyncio.CancelledError`; that handler would also absorb an outer workflow cancel. Cancelling the gate
  propagates into `run_gated_action`'s child `ActionApprovalWaitWorkflow`. Per the `_settle_gate` docstring, a consume
  that is already running still runs `gh pr merge` after the cancel.
- **Gate bookkeeping.** `_gate_head` is set when an attempt starts (line 6885). `_record_gate_result` (line 5416) sets
  `_gate_settled_head = _gate_head` (line 5433) on a settled outcome or on `ran`. Nothing records "a gate ran at head H"
  separately from "a human settled H".

### Why activation is a separate slice (S1, S2, S3, verified on main)

- **S1 (V1).** `_deliver` (line 2924) waits on `self._abandoned or self._is_approved() or self._gates_passed or
  self._exiting or self._hopping` and computes `decided = (self._is_approved() or self._gates_passed) and not
  self._abandoned`; it consults `_reconcile_required` (lines 3005, 3013) only. A delivery still waiting when
  `_settle_deliveries` sets `_exiting` (line 3109) therefore lands `Succeeded` on an approved loop, including on a new
  interim Failed end.
- **S2 (V2).** Only `hopping` suppresses the relinquishing write in `finally`. A cancel unwinding through a future
  decision would write `release`.
- **S3 (V3).** Nothing uses `is_cancelled_exception`. A new `except ActivityError` around a final-read attempt also
  catches a cancelled activity (SDK 1.34.0, read from source: `ActivityError` with a cancelled cause; a `CancelledError`
  is possible when the result is already ready in the same activation).

All three only matter once something calls the decision. In 1d-2a nothing does.

### Restart (corrected)

- `start.py:33`: `DEV_LOOP_ID_REUSE_POLICY = ALLOW_DUPLICATE_FAILED_ONLY`, the intake poller's policy
  (`run_issue_poller.py:235`, `run_issue_directive_poller.py:1201`, `cli.py:37`).
- `start.py:42`: `DISPATCH_ID_REUSE_POLICY = ALLOW_DUPLICATE`, the dispatcher's and mctl-api fulfil's policy: any closed
  run may be followed by a new one, because a resume request is an explicit ask.
- `RESTART_ID_REUSE_POLICY = ALLOW_DUPLICATE` is the operator restart; `restart_if_restartable` (`start.py:107`)
  reads a COMPLETED run only (`start.py:136`) and only after the run was abandoned before implement.
- So **both intake and the dispatcher/fulfil path can start a new run on the id of a Failed or Cancelled run**; the
  operator restart cannot. The consequence for the future Failed end belongs to 1d-2b (design section 8): a re-added
  intake label on an issue whose implement succeeded and whose PR is open would start a second full pipeline, where today
  it hits "already handled". Not a 1d-2a concern, because 1d-2a produces no new end state.

### Tests that bear on this slice

- 1d-2a edits **none** of them. In particular `test_merge_detection_survives_read_failures_until_deadline` (line 4103),
  `test_pre_m1_compat.py` (`M1_ADDED`, line 151) and `test_nothing_in_production_sets_the_flag_or_a_watch_end`
  (`tests/test_merge_watch_typed_result.py`, line 79) all stay green, because nothing in production reaches the decision
  and no payload field is added.
- Precedent for a test-only `DevLoopWorkflow` subclass: `_FlaggedLoop` (`tests/test_merge_watch_typed_result.py`,
  lines ~240-350, with `_FlagDuringWaitLoop` and `_FlagClearedAtWaitLoop`). The new harness follows it.
- Fakes: `_fake_activities` in `tests/test_dev_loop_workflow.py` (`pr_states`, `pr_state_raises_after`,
  `pr_state_error_type`); activities are counted from history events (`ACTIVITY_TASK_SCHEDULED`), not from fake calls.
- CI: `uv run --locked pytest -q` (`.github/workflows/pr-validation.yml:230`), `testpaths = ["tests"]`, no filter.
  A new `tests/test_merge_watch_decision.py` is collected.

### SDK

`uv.lock` pins `temporalio==1.34.0`; the repo `.venv` may hold 1.31.0. This slice relies on `workflow.wait` (it raises
`ValueError` on an empty list, hence the `if in_flight:` guard) and on `workflow.wait_condition`, both present on 1.34.0.

## Proposed solution (1d-2a)

All production changes are in `orchestrator/temporal/workflows/dev_loop.py`, on top of `55b4633`. The slice adds no
activity, CWFT, env var, marker or payload field, and **no call site**.

### 1. Constants and state

- `FINAL_READ_ATTEMPTS = 3` and `FINAL_READ_BACKOFF = timedelta(minutes=2)`, beside `PR_STATE_TIMEOUT`.
- `MERGE_WATCH_RECONCILE_UNRECORDED = "MergeWatchReconcileUnrecorded"`, defined here for 1d-2b's `ApplicationError` type
  and log tag. If it would be dead code with no reader, the implementer defines it in 1d-2b instead; either is
  acceptable, and D17a does not scan for it.
- `GATED_ACTIVITY_TIMEOUT`, imported from `action_approval` (line 132 there), like `DEFAULT_MAX_WAIT_SECONDS`.
- `self._watch_unrecorded = False` and `self._gate_ran_head = ""`, set in `__init__`. Instance state, not serialized,
  issue no command.
- `_record_gate_result` additionally sets `self._gate_ran_head = self._gate_head` when `result.ran`. This is the one
  edit to an existing method (R2): an attribute assignment, no `workflow.*` call.
- `@dataclass(frozen=True) class _FinalRead` with `fresh: PRState | None` and `abandoned: bool` (the earlier draft's
  `last_not_found` is dropped: unused here, and 1d-4 can add it when it has a reader).
- `@dataclass(frozen=True) class _WatchDecision` with `kind: str` (`final`, `open`, `abandoned`, `unrecorded`) and
  `last: PRState | None`.

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
        return False          # a workflow cancel is NOT caught: CancelledError propagates

async def _settle_watch_work(self, watch, service, slug) -> bool:
    in_flight = [t for t in (watch.tick_task, watch.gate_task) if t is not None and not t.done()]
    for t in in_flight:
        t.cancel()
    if in_flight:
        await workflow.wait(in_flight)     # an outer cancel raises HERE, not absorbed (mutation (ai), 1d-2b)
    await self._settle_tick(watch.tick_task, service, slug)      # done() branch: drain only
    await self._settle_gate(watch.gate_task, service, slug, repo=repo, number=number,
                            poll_index=watch.poll_index)   # repo/number derived as `finally` derives them
    watch.tick_task = None
    watch.gate_task = None
    return bool(in_flight)

async def _final_pr_read(self, watch, service, slug) -> _FinalRead:
    for attempt in range(FINAL_READ_ATTEMPTS):
        if attempt and await self._wait_unless_abandoned(FINAL_READ_BACKOFF):
            return _FinalRead(None, True)
        try:
            state = await workflow.execute_activity(get_pr_state, args=[service, slug],
                start_to_close_timeout=PR_STATE_TIMEOUT, retry_policy=PR_STATE_RETRY_POLICY)
        except ActivityError:
            state = None       # includes a cancelled attempt: accepted interim limit (S3), pinned in 1d-2b
        if state is not None and state.found:
            await self._apply_found_state(state, watch)
            terminal = state.state in ("MERGED", "CLOSED")
            return _FinalRead(state, self._abandoned and not terminal)
        if self._abandoned:
            return _FinalRead(None, True)
    return _FinalRead(None, False)
```

`workflow.wait` is used rather than `asyncio.wait` because it is the deterministic one. The `repo` and `number`
arguments are derived from `self._owned_entity_id` / the watch exactly as `finally` derives them today (the implementer
copies that code). When
`_settle_gate`'s `done()` branch runs `_finish_gate`, `MERGE_APPROVED` is logged and `_gate_ran_head` is set before the
read.

### 3. The decision

The deadline subset of #1021's `_decide_watch_end`.

```python
async def _decide_watch_end(self, exit_name, watch, service, slug) -> _WatchDecision:
    assert exit_name == "deadline"          # noqa: S101 -- the other exits are 1d-4
    self._watch_unrecorded = True           # R4: from decision START
    unobserved = await self._settle_watch_work(watch, service, slug)
    settled_at = workflow.now()
    if self._abandoned:
        return self._settled(_WatchDecision("abandoned", watch.last))        # (al, first)
    read = await self._final_pr_read(watch, service, slug)
    if read.abandoned:
        return self._settled(_WatchDecision("abandoned", read.fresh or watch.last))
    fresh = read.fresh
    if fresh is not None and fresh.state == "OPEN" and fresh.head_sha and fresh.head_sha == self._gate_ran_head:
        unobserved = True                                                     # R8
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
    return _WatchDecision("unrecorded", fresh or watch.last)                  # flag stays True (R10)
```

`_settled(d)` sets `self._watch_unrecorded = False` and returns `d`. An exception or cancel anywhere inside leaves the
flag True (R11).

**About an "abandoned before the decision" guard.** The first draft put `if self._abandoned:` before the decision in the
`else:` arm of `_watch_pr` (its mutation (v)). That guard is wiring, so it is not part of 1d-2a. Two independent passes
established, for 1d-2b's benefit:
- In **commands** a guard-less path is equal to the guarded one: with nothing in flight both emit the same history, and
  with something in flight today's `finally` settles it by the same cancel-and-await.
- In the **typed result** they are not equal. Without the guard an ordinary operator abandon reaches the decision, which
  returns kind `abandoned`, which the section 8 mapping turns into `watch_end = abandoned-unverified`; today that value
  is `""`, and `test_every_other_watch_end_keeps_todays_result` pins `""`. So 1d-2b must either keep the guard or map
  abandon-before-decision to `""`, and its D8 must assert `watch_end` for an ordinary abandon so that (v) is killable.
  (v) therefore returns to the 1d-2b mutation list; it is not claimed equivalent.
In 1d-2a the decision keeps its own check after the settle (mutation (al, first)), which makes it correct whichever way
1d-2b decides.

### 4. Inertness, and how it is pinned

- **No call site.** `_decide_watch_end`, `_settle_watch_work`, `_final_pr_read` and `_wait_unless_abandoned` are called
  only by each other and by the test harness. `_watch_pr`, `_deliver`, the `finally` block and `_finish_after_watch` are
  not edited.
- **No new command from any existing path.** `__init__` gains two attributes; `_record_gate_result` gains one
  assignment. Neither schedules anything, so no existing history changes shape and no marker is needed. The existing
  replay suites (`test_workflow_replay.py`, `test_execution_request_replay.py`, `test_pre_m1_compat.py`,
  `test_patch_memoization.py`) stay green unedited; that is the replay evidence.
- **Pin (D17a).** An AST scan of `dev_loop.py` asserts: the four helpers have no call site outside each other;
  `_watch_pr` has no `While.orelse` and does not mention `_watch_unrecorded` or the helpers; `_deliver` and the `finally`
  block do not mention `_watch_unrecorded`; `_watch_unrecorded` occurs only in `__init__`, `_decide_watch_end` and
  `_settled`; none of `is_cancelled_exception`, `_retain_claim`, `tick_blocked_until`, `_reconcile_required = True` and an
  `execute_activity` of `record_merge_watch_reconcile` / `confirm_no_pr` occurs; the count of `workflow.patched(` equals
  the count on `55b4633` (the implementer records the literal in the test). The test's docstring states that 1d-2b
  replaces it with an activation pin.

### 5. The test harness (test-only)

A subclass of `DevLoopWorkflow` in the new test file, registered in the test worker with a unique workflow name, in the
style of `_FlaggedLoop`. It overrides `_watch_pr` (or `run`, whichever `_FlaggedLoop`'s precedent shows to be the smaller
seam) to:

- build a `_MergeWatchRun` with `track_ownership` as the case requires;
- optionally install harness-created tasks as `watch.tick_task` and `watch.gate_task` (a task awaiting a future that the
  harness never sets stands in for a gate in flight);
- call `self._decide_watch_end("deadline", watch, "svc", "slug")`;
- expose the returned `_WatchDecision` and `self._watch_unrecorded` through a query, and let the test set
  `self._abandoned` through the real abandon signal.

**What the harness does and does not prove.** It proves the decision's behaviour (reads, ordering, kinds, flag
lifecycle) against the real helpers and the real `_apply_found_state`, `_terminal_claim` and `_settle_*`. It does not
prove the wiring in `_watch_pr`, the `finally` guards, `_deliver`, or any cancellation surface, and it does not run the
real `ActionApprovalWaitWorkflow` (the standing-in gate is a plain task). All of that is 1d-2b. If no subclass can reach
the decision without editing production code, the implementer stops (R0b).

### 6. Tests (all new, in `tests/test_merge_watch_decision.py`)

They run on `WorkflowEnvironment.start_time_skipping()` with `_fake_activities`. "Reads" means `ACTIVITY_TASK_SCHEDULED`
events of `get_pr_state` after the decision started.

- A1. Final read MERGED: kind `final`, exactly one read, `terminal` written once, no `release`, flag False.
- A2. Final read OPEN, nothing in flight: kind `open` with the fresh state, no window timer, no `terminal`, no `release`
  by the decision, flag False.
- A3. Final read CLOSED: kind `final`, `terminal` written.
- A4. Unreadable, three variants (transient `ProposalListingError`; non-transient error; `found=False`): exactly
  `FINAL_READ_ATTEMPTS` reads, `FINAL_READ_BACKOFF` timers between them, kind `unrecorded`, flag **True**, no `release`
  or `terminal`, `record_merge_watch_reconcile` and `confirm_no_pr` not scheduled, nothing raised.
- A5. Ordering, from history. On the paths of A1-A4 nothing is in flight, so only the part "`terminal` follows the read
  that returned the terminal state" is non-vacuous there. The settle-before-read ordering is asserted with a **stubborn
  gate**: the harness's standing-in gate task, when cancelled, blocks until the test releases it; the test asserts zero
  `get_pr_state` events while it is blocked and exactly one after the release.
- A6. Abandon: (i) set before the decision: settle, then no read, kind `abandoned`, flag False; (ii) during a backoff:
  wakes at once, no further read; (iii) during the window; (iv) during a read that returns OPEN and (v) during a read that
  returns MERGED: the fake `get_pr_state` blocks until the test sends the abandon signal and then releases it; (iv) gives
  kind `abandoned` with the fresh state, (v) gives kind `final`.
- A7. Own attempts: a stubborn gate (as in A5) standing in flight is cancelled and awaited before the first read; the
  window timer's duration is asserted from history (`settled_at + GATED_ACTIVITY_TIMEOUT` minus the time already spent,
  not a count), so a window measured from decision start is detected; a merge that lands during the window gives a second read of MERGED and kind `final`; OPEN after `GATED_ACTIVITY_TIMEOUT` gives `unrecorded`;
  `_gate_ran_head` equal to the OPEN head gives `unrecorded`, a different head gives `open`; with nothing in flight there
  is no `workflow.wait` and no window timer.
- A8. Bookkeeping: a final-read OPEN sets `_last_pr` and `saw_open_pr`, resets `polls_without_pr` and
  `terminal_status_polls`, and takes the claim through `_track_ownership`; a MERGED first resolved by the final read,
  from a state with no claim, gives `acquire` then `terminal`, in that order.
- A9. Flag lifecycle, each asserted explicitly: True while the decision is blocked in the settle, in a backoff and in the
  window (read through the harness query); False after `final`, `open` and `abandoned`; True after `unrecorded` (asserted
  here as well as in A4, so (fl3) has two killers); True after an exception raised
  inside the decision (a harness override of `_apply_found_state` raising `ApplicationError`).
- A10. `_record_gate_result` with `ran` True sets `_gate_ran_head` to the attempt's head; with `ran` False it does not.
- D17a. The inertness pin of section 4.

### 7. Mutation proof (1d-2a share)

Each applied locally by exact-text substitution on a worktree copy, only `tests/test_merge_watch_decision.py` run, shown
red, reverted, absent from the diff. The method is the one used for #1049 (commit first, then mutate).

| Mutation | Change | Expected red |
|---|---|---|
| (a) | the decision returns `open(watch.last)` without reading | A1, A2 |
| (d) | treat a failed final read as OPEN (`fresh = watch.last` when nothing is found) | A4 |
| (w) | run the first `_final_pr_read` before `_settle_watch_work` | A5, A7 |
| (x) | return `open` for a found OPEN while `unobserved` | A7 (window OPEN, ran-head OPEN) |
| (xr) | drop the `_gate_ran_head` comparison | A7 (ran-head) |
| (win) | drop the window re-read (`unobserved` goes straight to `unrecorded`) | A7 (merge lands during the window) |
| (ac) | skip `_apply_found_state` in `_final_pr_read` | A8 |
| (al, first) | remove the `self._abandoned` check after the settle | A6 (i) |
| (fl1) | do not set `_watch_unrecorded` at decision start | A9 |
| (fl2) | `_settled` does not clear the flag | A9 |
| (fl3) | clear the flag on the `unrecorded` return | A4, A9 |
| (inert) | add a call to `_decide_watch_end` inside `_watch_pr` | D17a |
| (ws) | measure the window from decision start instead of `settled_at` | A7 (window duration) |
| (wt) | drop `workflow.wait(in_flight)` | A5, A7 (stubborn gate), if distinguishable |
| (pc) | drop the pre-cancel loop in `_settle_watch_work` | A5, A7 (stubborn gate), if distinguishable |

(wt) and (pc) may prove equivalent in 1d-2a, because `_settle_gate` also cancels and awaits the task itself (a prototype
of this design left them alive against an ordinary gate). If the stubborn gate does not kill them either, the implementer
reports each as equivalent in this slice with the reasoning and its output; they move to 1d-2b with (ai), where D13
distinguishes them. Nothing is claimed red without output. (v) is not a 1d-2a mutation (it is wiring); it is a 1d-2b
mutation (section 3). (e), (g), (ai), N1, N2 and the other wiring mutations belong to 1d-2b; (am) and (ao) to 1d-4.
DoD: the twelve first rows red with output; (ws) red; (wt) and (pc) red or reported equivalent; none in the diff.

### 8. What 1d-2b will contain (declared here, decided in its own proposal)

Recorded so nothing is lost; 1d-2b gets its own issue, investigator, proposal, digest, review, approval, PR and owner
merge GO, after 1d-2a is merged.

- **Wiring.** The `while ... else:` under `if watch.terminal_reconcile:` calls the decision; `watch_end` and
  `decision_kind` locals; on `final` return `_WatchOutcome(last, watch_end=final-read)`; on `open`/`abandoned` set
  `watch_end` and fall to `finally`; on `unrecorded` raise `ApplicationError(type=MergeWatchReconcileUnrecorded,
  non_retryable=True)` after `finally`; final return carries `watch_end`.
- **Both guards in `finally`.** The relinquishing write becomes `if not hopping and not self._watch_unrecorded and
  watch.track_ownership and self._owned_entity_id:` and logs `MERGE_WATCH_RECONCILE_UNRECORDED` instead; the
  `_report_claim_abandonment` guard (line 7045) is stated explicitly (it only logs when `_claim_abandoned` was already
  True, so low impact, but the proposal must say whether it changes).
- **`_deliver` guard.** `and not self._watch_unrecorded` in the wait predicate and in `decided` (closes S1).
- **`MergeWatchResume.gate_ran_head: str = ""`**, carried in the hop record and rehydrated next to
  `merge_gate_settled_head` (line 4619). Needs E2 (the `M1_ADDED` / `M1_DEFAULTS` rows).
- **Marker.** Reuse `merge-watch-terminal-reconcile` (owner ruling 2026-11-08), with replay proof of old histories. Basis:
  no deployed worker records it (worker tag `1.117.0`; the latest release 1.117.0 of 2026-11-03 does not contain
  `883b3a1bf`), and no committed fixture carries it. Old-worker consequence: a history recorded after 1d-2b that already
  contains deadline-decision commands fails with nondeterminism on a worker below it, so rollback below 1d-2b is unsafe
  for runs that recorded the marker and reached the decision.
- **Tests.** The gap-harness conversion (scenario A, shown red on the base first); E1, E2, E3 as the only existing-test
  edits:
  - E1: the final assertions of `tests/test_dev_loop_workflow.py::TestDevLoopWorkflow::test_merge_detection_survives_read_failures_until_deadline`
    (line 4103) change to the interim end (a `WorkflowFailureError` whose cause is an `ApplicationError` of type
    `MergeWatchReconcileUnrecorded`, with no `release` and no `terminal` after the last pre-deadline poll);
  - E2: the `M1_ADDED` / `M1_DEFAULTS` rows for `MergeWatchResume.gate_ran_head` in `tests/test_pre_m1_compat.py`
    (`M1_ADDED` at line 151);
  - E3: removal of the `_WatchOutcome(watch_end=...)` half of `test_nothing_in_production_sets_the_flag_or_a_watch_end`
    (`tests/test_merge_watch_typed_result.py`, line 79), keeping its `_reconcile_required` half;
  also `tests/test_merge_watch_final_read.py` with the two `merge_watch/` fixtures and their recorder (flat globs do not
  see the subdirectory; `pre_m1/` is the precedent); D13 (cancel in the settle, with a **new** test-only
  `ActionApprovalWaitWorkflow` double that proves the parent's `workflow.wait` and the flag, **not** real child
  cancellation, released in teardown because `_settle_gate` in `finally` waits on it), D13b, D13c, D13d (S3 pin; asserts
  the observed 1.34.0 surface, `ActivityError`, and the same-activation `CancelledError` caveat), a pin for the
  `_ownership` activities inside the decision absorbing a cancel, D18 with **its own** helper (not an edit of
  `_deliver_with`, which hard-codes a 2099 deadline, no `terminal_reconcile` and one OPEN state), the activation pin
  replacing D17a, and the wiring mutations: (v) (with a D8 that asserts `watch_end` for an ordinary abandon, section 3), (e), (g), (ai),
  N1, N2 (which also turns D13 red), a mutation per `finally`
  guard, a mutation for the `gate_ran_head` hop carry, and one for each `_deliver` expression.
- **Platform impact to state in 1d-2b.** A watch whose PR is open at the deadline with a gate or tick in flight now
  ends `Failed` with the claim retained about 10 h (before: `release` and Completed); that is frequent (a merge gate
  waiting for approval), fail-closed, and pinned by tests. A Failed end is restartable by intake (see Restart above).
  Abandon with an unobserved gate releases the claim, as today. Reader compatibility: no `DevLoopResult` field changes;
  `watch_end` gains `final-read` and `abandoned-unverified`; mctl-api reads `Ended` and `Implemented` on Completed runs
  only. Delivery holding during a decision can delay a delivery by up to about 80 min.
- **S3** is an accepted interim limit **only while undeployed** (the release hold is ON), with D13d proving no stale
  success and no unintended claim release; 1d-3's re-raise (y) must turn D13d red on purpose.

### 9. Sizing and budget

- **1d-2a production:** about 140-170 lines in `dev_loop.py` (constants and fields about 15, dataclasses about 14,
  helpers about 70, decision about 45, the `_record_gate_result` line). About 2 times 1d-1's 77.
- **1d-2a tests:** about 550-700 lines (harness about 120, A1-A10 and D17a). About 1.3-1.6 times 1d-1's 428.
- Fifteen mutation rows against one new file are cheap.
- **Judged to fit one bounded pass**, with moderate margin, because the work is one new module-local concept with no
  wiring, no fixture, no recorder and no existing-test edit. R0c is a hard stop; the implementer does not trim tests. If
  it stops, the report says where, and the next cut is helpers + decision with A1-A9 versus the harness-heavy A6/A7/A9.
- **1d-2b (estimate, for its own proposal to confirm):** about 80-110 production lines, about 600-750 test lines, 2
  fixtures, 1 recorder, E1-E3 and about 12 mutation runs. If its own proposal judges that too large, it splits further
  before approval rather than relying on a mid-pass stop.
- **Commit shape** (owner rule on #1025): a single implementation commit is acceptable. The red evidence is reproduced
  against the branch base with the production change stashed, and command and output are pasted into the PR.

## Alternatives

1. **Ship the wiring behind a constant that is False.** Rejected: one line flips an unsafe path on, and the wiring could
   not be mutation-tested while off. 1d-2a has no caller instead.
2. **Wire the decision in 1d-2a and add the guards in 1d-2b.** Rejected by the owner: it leaves an active unsafe runtime
   path (S1/S2) between the two merges.
3. **Split by test type (decision tests in a, fixtures and recorder in b), as the first draft's fallback did.** Rejected:
   1d-2a alone would keep 85-90% of the work and still contain the wiring.
4. **A new marker `merge-watch-deadline-final-read`.** Not needed in 1d-2a, which uses no marker. The owner ruled for reuse
   in 1d-2b; the new marker remains the alternative there (a second `MergeWatchResume` bool and another E2-style row).
5. **Close S3 with `if is_cancelled_exception(exc): raise` in `_final_pr_read`.** This is #1021 mutation (y), assigned to
   1d-3 and listed among #1052's STOP items. Pinned in 1d-2b instead.
6. **Close S1 by setting `_reconcile_required` on the interim end.** Forbidden by #1052, and its refusal would claim a
   record that does not exist.
7. **Do the final read in `finally` or `_finish_after_watch`.** Rejected (#1021 alternative 2): `finally` must not decide
   after the write it guards, and the tail runs after the claim is gone.

## Platform impact (1d-2a)

- **Replay.** No new command is reachable from any existing path, so no history changes shape and no marker is evaluated.
  The existing replay suites are the evidence.
- **Rollback.** Before any release, a plain revert of the PR. Nothing is released or deployed (release hold ON). After a
  release that carries this slice there is nothing to protect: the new code is unreachable.
- **Payload compatibility.** No `MergeWatchResume`, `DevLoopResult`, `_MergeWatchRun` or CLI change in either direction.
- **Resources.** None at runtime.
- **Risks and mitigations.**
  - The harness may not reach the decision without a production edit. Mitigation: R0b stop with a named reason.
  - An existing test may fail for a reason this slice did not foresee (for example a test that enumerates `DevLoopWorkflow`
    attributes). Mitigation: task 1 runs the full suite on the base and after the change; any edit to an existing test is
    a stop (R0a).
  - A reader mistakes inert code for the finished fix. Mitigation: D17a's docstring, the PR description, and #1029 stays
    open until 1d-2b converts its pin.
- **Merge governance.**
  - The implementer PR must be verified as blocked by GitHub (the #1020 code-owner hold); if it is not blocked, stop.
  - Any HEAD change after review (including a shepherd push) needs re-verification and a fresh review.
  - No autonomous merge, admin bypass, release, deployment, Vault or GitOps rollout.
  - B4 stays FAIL and the release hold stays ON. #1003, gitops#2394 and mctl-api#934 stay Draft.
  - 1d-2b, 1d-3 and 1d-4 are not started by this slice; each needs its own owner GO.
  - #1022 must be resolved before any release that carries 1d-3. Green tests are never grounds for lifting the release hold.
