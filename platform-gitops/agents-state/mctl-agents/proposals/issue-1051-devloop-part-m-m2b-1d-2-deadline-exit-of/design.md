# Design: issue-1051-devloop-part-m-m2b-1d-2-deadline-exit-of

## Current state

Paths and lines are those at PR #1049 head `9ac2ff4`, read from an archive of that commit. #1049 is open and not
merged. Main is `14645f9`, where #1049's branch has not landed. Main also carries #1045, which the PR branch predates.
That difference is unrelated spike files.

### The merge watch (`orchestrator/temporal/workflows/dev_loop.py`, 7050 lines at `9ac2ff4`)

- **Loop and deadline.** `_watch_pr` (line 6485) carries `deadline` from `resume.deadline` or computes
  `workflow.now() + MERGE_WATCH_DEADLINE` (14 d, line 552). It loops on
  `while workflow.now() < deadline and not self._abandoned:` (line 6670) and sleeps `cadence.poll_interval` at the
  bottom. The loop has no `else:`. When the condition goes false, control falls straight into `finally` (line 6954),
  and that block settles the tick and gate and writes `release` (or `terminal` if `watch.last` is MERGED/CLOSED). The
  method then returns `_WatchOutcome(last=watch.last, ended=watch_ended)` (line 7050). **This is the defect.** There is
  no read after the deadline.
- **Marker already present (M2b-1b, `883b3a1bf`).** `MERGE_WATCH_RECONCILE_PATCH = "merge-watch-terminal-reconcile"`
  (line 489) is evaluated only in the fresh-start arm (line 6611). It is carried as
  `MergeWatchResume.terminal_reconcile: bool = False` (record line ~1674), read in the resume arm (line 6552), put into
  the hop record (line 6711), and stored on `_MergeWatchRun.terminal_reconcile`. No code branches on it yet.
- **Per-run state.** `_MergeWatchRun` (line 1797) holds `last`, `polls_without_pr`, `terminal_status_polls`,
  `saw_open_pr`, `track_ownership`, `poll_index`, `terminal_reconcile`, `tick_task` and `gate_task`. It is never
  serialized.
- **Extracted helpers (1b).** `_apply_found_state(state, watch)` (line 6442) is the found-branch bookkeeping, including
  `_track_ownership`. `_terminal_claim(state, watch)` (line 6465) is the in-loop `terminal` write plus `_finish_claim`,
  which clears `_owned_entity_id` on success (line ~5659), so `finally` does not write twice.
- **Settles.** `_settle_tick` (line 5223) and `_settle_gate` (line 5453) cancel an in-flight task and then
  `await task` inside `except asyncio.CancelledError`. That handler would also absorb an outer workflow cancel. A
  running gated consume still runs `gh pr merge` after the cancel (docstring, line 5465), and the Argo run of a tick
  finishes on its own (line 5229).
- **Gate bookkeeping.** `_record_gate_result` (line 5416) latches `_gate_off_until_poll` from `poll_index` and sets
  `_gate_settled_head = _gate_head` on a settled outcome or on `ran`. `_gate_head` is set when an attempt starts (line
  6885). `_gate_settled_head` is carried as `merge_gate_settled_head` (lines 6730, 4619). No field records "a gate ran
  (merged) at head H" separately from "a human denied/expired H".
- **Exits.** These exits return or break without the deadline path: MERGED/CLOSED (line 6784), the non-transient read
  error (line 6768), the grace polls (line 6947), the #516 break (line 6931) and the hop break (line 6738).
- **Result and tail (1d-1).** `_WatchOutcome` (line 1816) has `watch_end: str = ""` and `reconcile_record: str = ""`.
  `_finish_after_watch` (line 4685) passes `outcome.watch_end` into `DevLoopResult.watch_end` and special-cases only
  `WATCH_END_RECONCILE_REQUIRED`. The constants `WATCH_END_FINAL_READ`, `WATCH_END_ABANDONED_UNVERIFIED` and the
  others are at lines 1157-1164. `self._reconcile_required` (line 2019) and its two `_deliver` checks (lines
  3005-3016) exist, and nothing sets the flag.
- **Run exit.** `run` (line 3648) catches `(Exception, asyncio.CancelledError)`, ends the canonical execution and the
  deliveries, and re-raises (line 3650), so a raised `ApplicationError` ends the deliveries before failing the run.
- **Activities.** `record_merge_watch_reconcile` and `confirm_no_pr` are registered in `orchestrator/temporal/worker.py`
  with no caller (1c). `_is_transient` (line 1470) is the loop's read-error classifier. Nothing in the workflow uses
  `is_cancelled_exception` today.
- `GATED_ACTIVITY_TIMEOUT = timedelta(minutes=10)` is in `orchestrator/temporal/workflows/action_approval.py:132`.
  `PR_STATE_TIMEOUT` is 2 min and `PR_STATE_RETRY_POLICY` is 5 attempts (lines 616-617).

### Tests that bear on this slice

- `tests/test_merge_watch_worker_gap.py` (#1030) starts `DevLoopWorkflow.run` from a `MergeWatchResume` whose deadline
  lies inside a worker gap. **Its `_resume_record` does not set `terminal_reconcile`, so the field defaults to False**:
  as written, the harness would keep exercising the legacy line even after this change. Scenario A
  (`test_deadline_in_gap_ends_watch_without_reading_merged`) is the defect pin. Scenario B and
  `test_resume_record_fields_reach_the_merge_watch_path` are controls.
- `tests/test_dev_loop_workflow.py` contains fresh runs, where the marker evaluates True under new code, that end on the
  deadline:
  - `test_merge_detection_deadline_returns_last_open_state` (line 4068) stays green, because the final read is OPEN.
  - `test_deadline_is_carried_not_recomputed_across_hops` (line 7863) stays green: 3 polls plus 1 final read is within
    its `<= 5` bound, and `ended == ""` holds.
  - **`test_merge_detection_survives_read_failures_until_deadline` (line 4103) goes red.** Its fake raises
    `ProposalListingError` from call 2 on, so the final read fails on every attempt and the interim ends the run Failed.
    This is edit E1.
- `tests/test_pre_m1_compat.py`: `M1_ADDED["MergeWatchResume"]` (line 154) and `M1_DEFAULTS` are proven against the
  class by `test_the_pre_m1_field_sets_are_m1_minus_exactly_these` (line 479). A new field makes that test red. This is
  edit E2; 1b's merge changed this file by 4 lines for the same reason.
- `tests/test_merge_watch_typed_result.py` (#1049): `test_nothing_in_production_sets_the_flag_or_a_watch_end` (line 79)
  fails on any `_WatchOutcome(... watch_end=...)` call. Its own docstring says "1d-1-only scan: 1d-2 and 1d-3 remove
  it". This is edit E3.
- Flat-directory fixture guards: each iterates `tests/fixtures/histories/*.json` (or `dev_loop_*.json`) with an explicit
  allow-list.
  - `tests/test_execution_request_replay.py` lines 374, 431, 474, 530, 685 and 728.
  - `tests/test_pre_m1_compat.py::_recorded_dev_loop_histories` (line 581), which asserts that `deferred-resume-contract`
    is absent.
  - `tests/test_workflow_replay.py::test_every_recorded_fixture_belongs_to_a_scenario` (line 599, with
    `_STANDALONE_FIXTURES` at line 576).
  - Any fresh DevLoop recording that reaches implement records `deferred-resume-contract` (`dev_loop.py:4419`). A new
    flat fixture would therefore turn several of these red. None of them looks into a subdirectory; `pre_m1/` is
    already one.
- No committed fixture contains `merge-watch-terminal-reconcile`, checked by grep over `tests/fixtures`.

### Deployed state checked

- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: `image.tag: "1.117.0"`.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker-exec/values.yaml` and `.../mctl-agents-worker-implement/values.yaml`:
  both `1.117.0`.
- So no deployed worker runs code from `883b3a1bf` or later, and no production history carries the marker. The
  `labs/agent-worker-preview` service is a different image (`ghcr.io/mctlhq/agent-worker-preview`).
- `gh pr view 1049`: OPEN, head `9ac2ff4763a6de3e4d5394ae9a147f89ce00c6c7`, not merged.
- `gh issue view 1029`: OPEN. `gh issue view 1025`: OPEN. It records a deployed implementer cap of $20, and the owner
  rule that red-before / green-after evidence is mandatory while separate `test:` / `feat:` commits are not.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/issue-1021-*` and `issue-1046-*` (all three files each) were
  read as the specification. `issue-1046-*/.status.yaml` reads `implemented`, PR #1049.
- The 1d-2 row of the #1046 table was read from the #1046 issue body.
- mctl MCP tools were not called. This slice changes no runtime configuration and is not deployed. mctl-api
  `restartIfAbandoned` was not re-read (Open question Q7).

## Proposed solution

All production changes are in `orchestrator/temporal/workflows/dev_loop.py`, written on top of #1049. No activity, no
CWFT, no env var and no new `workflow.patched` marker is added.

### 1. Constants and state

- `FINAL_READ_ATTEMPTS = 3` and `FINAL_READ_BACKOFF = timedelta(minutes=2)`, beside `PR_STATE_TIMEOUT`.
- `MERGE_WATCH_RECONCILE_UNRECORDED = "MergeWatchReconcileUnrecorded"` (the `ApplicationError` type).
- `GATED_ACTIVITY_TIMEOUT`, imported from `action_approval` like `DEFAULT_MAX_WAIT_SECONDS`.
- `_MergeWatchRun.unrecorded: bool = False`. This is the interim "keep the claim" flag, set only at the R7 decision
  point. It is deliberately not named `_retain_claim`: 1d-3 introduces `_retain_claim` with its wider scope, which
  spans from decision start and covers cancellation, and it removes this field.
- `self._gate_ran_head = ""` in `__init__`. `_record_gate_result` sets `self._gate_ran_head = self._gate_head` when
  `result.ran`. The field is `MergeWatchResume.gate_ran_head: str = ""`, filled in the hop record and rehydrated in
  `_resume_merge_watch` beside `merge_gate_settled_head`. It is instance state only and issues no command.
- `@dataclass(frozen=True) class _FinalRead: fresh: PRState | None; abandoned: bool; last_not_found: PRState | None`.
  `last_not_found` is unused here and kept for 1d-4's `_no_pr_proven`.
- `@dataclass(frozen=True) class _WatchDecision: kind: str; last: PRState | None`, where `kind` is one of `final`,
  `open`, `abandoned` or `unrecorded`.

### 2. Helpers

```python
async def _wait_unless_abandoned(self, duration: timedelta) -> bool:
    if self._abandoned:
        return True
    if duration <= timedelta(0):
        return False                       # a negative timer is a RuntimeError
    try:
        await workflow.wait_condition(lambda: self._abandoned, timeout=duration)
        return True
    except TimeoutError:                   # the same exception `_land_delivery`'s wait catches (line 3050)
        return False

async def _settle_watch_work(self, watch, service, slug) -> bool:
    in_flight = [t for t in (watch.tick_task, watch.gate_task) if t is not None and not t.done()]
    for t in in_flight:
        t.cancel()
    if in_flight:
        await workflow.wait(in_flight)     # an outer cancel raises HERE (mutation (ai))
    await self._settle_tick(watch.tick_task, service, slug)          # done() branch: drain
    await self._settle_gate(watch.gate_task, service, slug, repo=..., number=..., poll_index=watch.poll_index)
    watch.tick_task = None
    watch.gate_task = None
    return bool(in_flight)
```

The `repo`/`number` arguments are the ones `finally` passes today. `_settle_gate`'s `done()` branch runs
`_finish_gate`, so `MERGE_APPROVED` is still logged and `_gate_ran_head` is set before the read. `workflow.wait`
exists in the pinned `temporalio==1.34.0` (`uv.lock`, checked in this investigation). It is the deterministic
counterpart of `asyncio.wait`, and `asyncio.wait` must not be substituted for it.

```python
async def _final_pr_read(self, watch, service, slug) -> _FinalRead:
    last_not_found = None
    for attempt in range(FINAL_READ_ATTEMPTS):
        if attempt and await self._wait_unless_abandoned(FINAL_READ_BACKOFF):
            return _FinalRead(None, True, last_not_found)
        try:
            state = await workflow.execute_activity(get_pr_state, args=[service, slug],
                start_to_close_timeout=PR_STATE_TIMEOUT, retry_policy=PR_STATE_RETRY_POLICY)
        except ActivityError:
            state = None                   # any failure is a failed attempt (no cancel re-raise: 1d-3)
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

### 3. The decision (deadline subset of #1021's `_decide_watch_end`)

```python
async def _decide_watch_end(self, exit_name, watch, service, slug) -> _WatchDecision:
    assert exit_name == "deadline"         # noqa: S101 -- the other exits are 1d-4
    unobserved = await self._settle_watch_work(watch, service, slug)       # R2
    settled_at = workflow.now()
    if self._abandoned:
        return _WatchDecision("abandoned", watch.last)                    # (al, first)
    read = await self._final_pr_read(watch, service, slug)                # R3
    if read.abandoned:
        return _WatchDecision("abandoned", read.fresh or watch.last)
    fresh = read.fresh
    if fresh is not None and fresh.state == "OPEN" and fresh.head_sha and fresh.head_sha == self._gate_ran_head:
        unobserved = True                                                 # R6
    if unobserved and (fresh is None or fresh.state == "OPEN"):
        if await self._wait_unless_abandoned(settled_at + GATED_ACTIVITY_TIMEOUT - workflow.now()):
            return _WatchDecision("abandoned", fresh or watch.last)
        read = await self._final_pr_read(watch, service, slug)
        if read.abandoned:
            return _WatchDecision("abandoned", read.fresh or watch.last)
        fresh = read.fresh
    if fresh is not None and fresh.state in ("MERGED", "CLOSED"):
        await self._terminal_claim(fresh, watch)                          # R4, same write as in-loop
        return _WatchDecision("final", fresh)
    if fresh is not None and not unobserved:
        return _WatchDecision("open", fresh)                              # R5
    if self._abandoned:
        return _WatchDecision("abandoned", fresh or watch.last)
    watch.unrecorded = True                                               # R7 interim
    return _WatchDecision("unrecorded", fresh or watch.last)
```

The `fresh.head_sha and ...` guard keeps an empty head from matching an empty `_gate_ran_head`. After the second read
set, an OPEN with `unobserved` still True falls through to `unrecorded`, as #1021 routes it to the record.

### 4. Wiring in `_watch_pr`

A local `watch_end = ""` is declared beside `watch_ended`. An `else:` is added to the existing `while` (Python runs it
only when the condition goes false, never after `break` or `return`), inside the existing `try`:

```python
while workflow.now() < deadline and not self._abandoned:
    ...                                        # unchanged
else:
    if watch.terminal_reconcile:               # R12: unpatched histories take no new command
        if self._abandoned:
            watch_end = WATCH_END_ABANDONED_UNVERIFIED            # R10, no command
        else:
            decision = await self._decide_watch_end("deadline", watch, service, slug)
            watch.last = decision.last if decision.last is not None else watch.last
            if decision.kind == "final":
                return _WatchOutcome(last=decision.last, watch_end=WATCH_END_FINAL_READ)
            watch_end = {"open": WATCH_END_FINAL_READ,
                         "abandoned": WATCH_END_ABANDONED_UNVERIFIED}.get(decision.kind, "")
```

The other changes:

- **`finally`.** The relinquishing block's guard becomes `if not hopping and not watch.unrecorded and ...`. When
  `watch.unrecorded` is set, the block logs
  `MERGE_WATCH_RECONCILE_UNRECORDED repo=... workflow=... exit=deadline last=<state/url/head or none>` and skips
  `_report_claim_abandonment`, so nothing is released and nothing is recorded. The two settle calls stay as they are
  and find None after a deadline decision, so no task is settled twice.
- **After `finally`, before the `hopping` return.**
  `if watch.unrecorded: raise ApplicationError("merge watch deadline: pull-request state not established; claim retained", type=MERGE_WATCH_RECONCILE_UNRECORDED, non_retryable=True)`.
  `run`'s `except` ends the canonical execution and the deliveries, then re-raises, and the run is `Failed`.
- **Final return.** `return _WatchOutcome(last=watch.last, ended=watch_ended, watch_end=watch_end)`.
- **`_finish_after_watch` is unchanged.** `final-read` and `abandoned-unverified` pass through to
  `DevLoopResult.watch_end`. The `pr` field is the fresh state, and the CLI already annotates `abandoned-unverified`.

Commands on each path:

- **Unpatched** (`terminal_reconcile` False): the `else:` body issues nothing, so commands are byte-identical to today.
- **Patched, no attempt in flight, final read found on the first attempt:** one `get_pr_state`, then today's `finally`
  write (`terminal` comes from `_terminal_claim`, `release` from `finally`).
- **Patched, attempt in flight:** cancel commands, the `workflow.wait`, then the reads. Up to two read sets and the
  window add at most about 80 minutes beyond the deadline, which is not added to the deadline itself.

### 5. Gap harness (`tests/test_merge_watch_worker_gap.py`)

`_resume_record(t0, offset, *, terminal_reconcile: bool = False)`. The default keeps
`test_resume_record_fields_reach_the_merge_watch_path`'s `got == want` and scenario B unchanged.

- **Scenario A becomes `test_deadline_in_gap_reads_the_merged_pr_once_more`,** run with `terminal_reconcile=True`. It
  asserts two `get_pr_state` schedules, the second at or after `gap_end`; `merged_returns == 1`;
  `result.pr.state == "MERGED"`; `result.watch_end == WATCH_END_FINAL_READ`; and lifecycle ops containing `terminal`
  and no `release`. The ops are recorded by wrapping the factory's `lifecycle_ownership` fake the way `_activities`
  wraps `get_pr_state`.
- **New `test_unpatched_record_keeps_the_legacy_deadline_end`** keeps today's assertions with `terminal_reconcile=False`
  (R15).
- **The module docstring's "Scenario A" paragraph and "Honest limit" are updated.** #1029 is closed only by the owner,
  after the corrected harness is verified.

### 6. Fixtures and replay

- **Recorder.** A recorder in the new test module, `record_final_read(env, *, hop)`, plus a thin
  `tools/record_merge_watch_final_read.py` script in the style of `tools/record_pre_m1_histories.py`. It records with
  `MERGE_WATCH_DEADLINE` monkeypatched to 40 min and, for the hop variant, `MERGE_WATCH_HISTORY_FLOOR = 1`, under
  `UnsandboxedWorkflowRunner`. The pattern is `test_deadline_is_carried_not_recomputed_across_hops`.
- **The two fixtures.**
  - `tests/fixtures/histories/merge_watch/dev_loop_final_read.json` is a fresh run: the marker is recorded exactly once,
    and the deadline final read returns MERGED and then `terminal`.
  - `.../merge_watch/dev_loop_final_read_hop.json` is the last continued run of a hopped watch: it has zero marker
    events, its `terminal_reconcile=True` arrives through the start input, and it ends with the deadline final read.
- **Replay test.** `tests/test_merge_watch_final_read.py` replays both under the same monkeypatches. A "today's code
  replays its own fresh recording" test ties the fixtures to the code, as `test_todays_issue_keyed_loop_replays_its_own_history`
  does.
- **No registration needed.** The subdirectory is invisible to every flat-directory guard (Current state), so no entry
  in `_STANDALONE_FIXTURES` or any allow-list is needed. This deviates from #1021 task 8's wording (Q3), and the
  deviation removes four or more existing-test edits.
- **Old-history replay.** It is shown by the existing suites, which must stay green unedited:
  `tests/test_workflow_replay.py`, `tests/test_execution_request_replay.py`, `tests/test_pre_m1_compat.py` (replay
  parts) and `tests/test_patch_memoization.py`. A new test also records a run from a resume record with
  `terminal_reconcile=False` across the deadline and replays it, with no final read.

### 7. Scope adjustments (narrowing, not widening)

- **`tick_blocked_until` (#1021 section 2) moves to 1d-4.** It guards the tick boundary after a settle. A deadline
  decision never returns to the loop: `final` returns, while `open`, `abandoned` and `unrecorded` fall into `finally`.
  So no boundary can follow a 1d-2 settle, and mutation (am) cannot be shown red. Only the grace-polls and read-error
  sites (1d-4) resume the loop after a settle.
- **Mutation (ao), `poll_index=0`, also moves to 1d-4.** `_settle_watch_work` passes the real `watch.poll_index` in
  this slice. That index only feeds `_gate_off_until_poll`, which nothing reads after a deadline decision.
- **`gate_ran_head` stays in 1d-2.** A gate that ran in an earlier run of a hopped watch, with the final read still
  OPEN at that head, is observable at the deadline (mutation (x), test D11).

### 8. Sizing against the implementer cap (#1025)

- **Production estimate.** About 170-220 lines in `dev_loop.py`: 2 constants, 1 field, 2 small dataclasses, 4 helpers,
  the `else:` arm, 3 lines in `finally`, the raise, `gate_ran_head` in 3 places and docstrings.
- **Test estimate.** About 600-800 lines in the new `tests/test_merge_watch_final_read.py` and about 40 lines changed
  in the gap harness. Add 2 fixtures, 1 recorder script, E1-E3 (about 15 lines), and 10 mutation runs, each a re-run of
  one test module.
- **Comparison.** 1d-1 (77 production lines and 428 test lines) passed all gates in one implementer pass (about 29
  min, `mctl-agents-implement-ab31f64e`). This slice is about twice that, so it is judged to fit one bounded pass under
  the $20 cap, but not with much room.
- **Pre-declared fallback split.** If the pass cannot finish, the implementer stops and reports instead of trimming
  tests:
  - **1d-2a:** sections 1-5, with D1-D14, D16 and D17 and the mutations. For (e) it uses only the gap harness and the
    hop parts of D10 that need no fixture.
  - **1d-2b:** section 6 (the fixtures and recorder) plus D15.

  1d-2a alone keeps every invariant, because fixtures add no behaviour.
- **Commit shape.** It follows #1025's owner rule: a single implementation commit is acceptable. Red evidence is
  reproduced by running the new and changed tests against the branch base commit with the production change stashed,
  and pasting the command and output into the PR.

## Alternatives

1. **Add a new `workflow.patched` marker for the deadline branch.**
   - What it is: for example `merge-watch-deadline-final-read`, instead of reusing `merge-watch-terminal-reconcile`.
   - Why it was considered: it would make the branch independent of every history recorded since `883b3a1bf`.
   - Why it was dropped: it needs another `MergeWatchResume` field and so another E2-style edit, and #1021 specifies a
     single marker. No deployed worker has run code from `883b3a1bf` onward (tag `1.117.0`), so no production history
     records the marker without the branch. The residual risk, a non-production worker built from main in that window,
     is stated under Platform impact.
2. **Do the final read in `finally` or in `_finish_after_watch`.**
   - Why it was dropped: `finally` must not run a decision before the relinquishing write it guards, and
     `_finish_after_watch` runs after the claim is already released. That is #1021 alternative 2.
3. **Keep the interim as "end Completed with the stale OPEN" on an unreadable read.**
   - What it would buy: it would avoid E1.
   - Why it was dropped: it is the fail-open direction the issue forbids, and it is exactly mutation (d).
4. **Register the fixtures flat in `_STANDALONE_FIXTURES`, as #1021 task 8 says.**
   - Why it was dropped: the flat-directory marker guards would need allow-list edits in at least two more test files.
5. **Keep `tick_blocked_until` in 1d-2 and test it through a probe that calls the tick-boundary predicate directly.**
   - Why it was dropped: the field would have no production caller in this slice, so the test would prove a mechanism
     the slice cannot reach.

## Platform impact

- **Replay.**
  - Pre-marker histories (`dev_loop_full.*`, `dev_loop_resumed.json`, `dev_loop_deferred_resume.json`, `pre_m1/` and
    the rest) decode `terminal_reconcile=False`, and the `else:` body issues nothing for them. They schedule identical
    commands and are not re-recorded.
  - A history recorded by code from `883b3a1bf` to #1049 carries the marker but took the no-read exit. That history
    would hit a nondeterminism error under this code if it were replayed past its deadline exit. No such history exists
    in production (tag `1.117.0`) or in `tests/fixtures`.
- **No new marker.** Old-worker consequence: a history recorded by this slice that already contains deadline-decision
  commands, replayed by a worker below this slice, fails with nondeterminism. That affects open runs in the settle,
  backoff or window (up to about 80 minutes past the deadline), and queries (for example `lifecycle_claim`) against
  closed runs of that shape. So **rollback below this slice is unsafe for runs whose first run recorded the marker and
  which have reached the deadline decision.** Rollback below `883b3a1bf` was already unsafe for every run that recorded
  the marker. This proposal decides nothing for B4 (#1007).
- **Payloads.**
  - `MergeWatchResume` gains `gate_ran_head` (defaulted). A new record decoded by an older worker drops the key: Temporal's
    converter ignores unknown keys, as pinned by `test_unsupported_direction_pre_m1_decoder_silently_drops_m1_fields`.
    A run continued that way would then miss a ran-but-unobserved gate, which is the fail-open direction, and only after
    a rollback.
  - `DevLoopResult` gains no field. The new values `final-read` and `abandoned-unverified` appear in `watch_end`.
    1d-1's CLI handles both. `start.py` `restart_if_restartable` and, per #1021, mctl-api decide on `ended` and
    `implement` only, and `ended` is unchanged on these paths.
  - An older reader drops `watch_end`. A newer reader of an old payload gets `""`.
- **New end state.** `Failed` with `MergeWatchReconcileUnrecorded`, claim retained until the store's liveness bound
  (about 10 h after close). Intake can restart a Failed issue id (Q6). No detector exists yet. #1022 must cover this
  state, together with 1d-3's states, before any release carrying the #1021 line. This slice adds no release and lifts
  nothing.
- **Resource impact.** A patched deadline end adds 1-3 `get_pr_state` calls (up to 6 with the window) and up to 3
  timers. That is once per watch and negligible.
- **Risks and mitigations.**
  - Other existing tests may be pushed onto the new path, for example a merge gate in flight at the deadline in a fresh
    test. Mitigation: task 1 runs the full suite against the change first, and any red test other than E1-E3 stops the
    slice.
  - An outer cancel might not raise from `workflow.wait` as the design assumes. Mitigation: test D13 proves it before
    mutation (ai) is run.
  - The interim limits in Q5. Mitigation: they are documented, fail closed or keep today's line, and 1d-3 replaces
    them.
- **Merge governance.**
  - The implementer PR must be verified as blocked by GitHub (the #1020 code-owner hold). If it is not blocked, stop.
  - A HEAD change after review, for example a shepherd push, needs re-verification and a fresh review.
  - No autonomous merge, no admin bypass, no release, deployment, Vault or GitOps rollout.
  - B4 stays FAIL and the release hold stays ON. #1003, gitops#2394 and mctl-api#934 stay Draft.
  - 1d-3 and 1d-4 are not started until this slice is resolved.
