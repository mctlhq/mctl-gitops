# Design: issue-1055-devloop-part-m-m2b-1d-2b-wire-the-merge

## Current state

All paths and lines below were read on main `0536caf` (merge of PR #1053, slice 1d-2a), in
`orchestrator/temporal/workflows/dev_loop.py` (7234 lines) unless another file is named.

### The merge watch today

- `_watch_pr` (line ~6669) takes its deadline from `resume.deadline` or `workflow.now() + MERGE_WATCH_DEADLINE`.
  - It evaluates `terminal_reconcile = workflow.patched(MERGE_WATCH_RECONCILE_PATCH)` in the fresh-start arm only
    (line 6795), and reads it from `resume.terminal_reconcile` in the resume arm (line 6736).
  - It stores the value on `_MergeWatchRun.terminal_reconcile` and puts it into the hop record (line 6895).
  - No code branches on it.
- The loop is `while workflow.now() < deadline and not self._abandoned:` (line 6854) inside `try`, and it has no
  `else:`. Its exits:
  - a hop `break`;
  - the #516 terminal-status `break` (`watch_ended = f"proposal {terminal_status}"`);
  - the MERGED/CLOSED `return`;
  - the read-error and grace-polls `return`s;
  - the condition going false, either at the deadline or on `abandon`.
- `finally` (line 7138):
  - It calls `_settle_tick` and `_settle_gate`.
  - Under `if not hopping and watch.track_ownership and self._owned_entity_id:` (line 7158) it writes `terminal` if
    `watch.last` is MERGED/CLOSED and `release` otherwise.
  - Under `if not hopping and watch.track_ownership:` (line 7229) it calls `_report_claim_abandonment` (line 5770),
    which only logs `LIFECYCLE-CLAIM-ABANDONED` when `_claim_abandoned` is True.
- The method returns `_WatchOutcome(last=watch.last, ended=watch_ended)` (line 7234). No exit sets `watch_end`.

### The inert decision from 1d-2a

- The constants are `FINAL_READ_ATTEMPTS = 3`, `FINAL_READ_BACKOFF = 2 min` and `MERGE_WATCH_RECONCILE_UNRECORDED =
  "MergeWatchReconcileUnrecorded"` (lines 635-639). The last one is still unread (P3 on the review of #1053).
- The dataclasses are `_FinalRead` (line 1838), `_WatchDecision` (line 1847) and `_WatchOutcome.watch_end`
  (line 1880).
- The `WATCH_END_*` values are at lines 1179-1182.
- `__init__` sets `_gate_ran_head = ""` and `_watch_unrecorded = False` (lines 1999-2000), and `_record_gate_result`
  sets `_gate_ran_head` on `result.ran` (line 5521).
- The helpers are `_wait_unless_abandoned` (6573), `_settle_watch_work` (6585), `_final_pr_read` (6604), `_settled`
  (6626) and `_decide_watch_end` (6630).
- `_decide_watch_end` sets the flag at its start and clears it through `_settled` on `final`, `open` and `abandoned`.
  It leaves the flag True on `unrecorded` and on any exception.
- `_apply_found_state` (6530) sets `watch.last` and `_last_pr`. `_terminal_claim` (6553) writes `terminal` and clears
  `_owned_entity_id` when the write lands.
- `_ownership` (5583) swallows `asyncio.CancelledError` around the `lifecycle_ownership` activity and returns None.
  This is the "ownership activities absorbing a cancel" surface the issue asks to pin.
- `tests/test_merge_watch_decision.py` has 27 tests. They reach the decision through the test-only `_DecisionHarness`.
  `test_inertness_pin` (D17a, line 581) asserts four things:
  - nothing outside the helpers mentions them;
  - `_watch_pr` has no `While.orelse`;
  - `_watch_unrecorded` occurs only in `__init__`, `_decide_watch_end` and `_settled`;
  - `PATCHED_CALLS = 37`.

  The review of #1053 recorded the mutation results: (pc) red with 7 failed, (wt) red, (xr) red.

### S1, S2 and the deliveries

- `_deliver` (line 3010) checks `_reconcile_required` before and after
  `await workflow.wait_condition(lambda: self._abandoned or self._is_approved() or self._gates_passed or self._exiting
  or self._hopping)` (line 3096), then computes `decided = (self._is_approved() or self._gates_passed) and not
  self._abandoned` (line 3104).
- During a merge watch `_gates_passed` is True (set at line 4506 before implement, and at line 4733 on resume). So a
  delivery that binds during a decision lands `Succeeded` at once. That is S1.
- `run` (line 3721) catches `Exception` and `asyncio.CancelledError`, ends the canonical execution, calls
  `_settle_deliveries(hopping=False)` (which sets `_exiting`, line 3195, and waits for every delivery task), and then
  re-raises. This matters for R11: a predicate that ignored `_exiting` while the flag is stuck True would deadlock that
  settle.

### Resume record

- `MergeWatchResume` (line 1654) carries `merge_gate_settled_head` (line 1750) and `terminal_reconcile` (line 1696). It
  has no `gate_ran_head`.
- The hop record is built inline in `_watch_pr` (line ~6882, `merge_gate_settled_head=self._gate_settled_head` at line
  6914).
- `_rehydrate_work_context` restores `self._gate_settled_head = resume.merge_gate_settled_head` (line 4705).
- `tests/test_pre_m1_compat.py` lists every post-a99c888 field in `M1_ADDED` and `M1_DEFAULTS` (lines 151-171), and
  `test_the_pre_m1_field_sets_are_m1_minus_exactly_these` fails on an unlisted field. That is E2.

### Tests that bear on activation

- **Gap harness.** `tests/test_merge_watch_worker_gap.py::test_deadline_in_gap_ends_watch_without_reading_merged` (line
  304) pins the defect: one `get_pr_state`, `merged_returns == 0`, OPEN.
  - Its `_resume_record` does not set `terminal_reconcile`, so the record decodes as False and today's pin keeps passing
    after activation.
  - The conversion therefore adds a `terminal_reconcile` kwarg (default False) and runs scenario A with True. On the
    base this is red, because nothing branches on the flag.
- **E1.** `tests/test_dev_loop_workflow.py::test_merge_detection_survives_read_failures_until_deadline` (line 4119) is
  a fresh, patched run. Every read after the first raises `ProposalListingError`, so the final reads fail and the
  decision returns `unrecorded`. The test then sees a `WorkflowFailureError`, so E1 changes its final assertions.
- **E3.** `tests/test_merge_watch_typed_result.py::test_nothing_in_production_sets_the_flag_or_a_watch_end` (line 79)
  asserts that no `_WatchOutcome(...)` call passes `watch_end`. E3 removes that half and keeps the
  `_reconcile_required` half.
- **Unaffected.** `test_every_other_watch_end_keeps_todays_result` (line 229) drives `_finish_after_watch` through
  `_finish`, not `_watch_pr`, so R6 leaves it green.
- **Ride-to-deadline tests.** `test_merge_detection_deadline_returns_last_open_state` (line 4083) and
  `test_deadline_is_carried_not_recomputed_across_hops` (line ~7880) reach the patched deadline. Both should stay green
  (OPEN `final-read`, one extra read within `<= 5`). Task 1 verifies this first (Open question Q-D).
- **Shape pin.** `test_merge_watch_run_shape` (`tests/test_dev_loop_workflow.py`, line 7665) pins the
  `_MergeWatchRun` fields. This slice adds none.
- **Delivery helper.** `_deliver_with` (`tests/test_merge_watch_typed_result.py`, line 297) is not reused: per the
  1d-2a design section 8, it hard-codes a 2099 deadline and one OPEN state. D18 gets its own helper.
- **Fixtures (1d-2b-ii).**
  - No file under `tests/fixtures/histories/` contains `merge-watch-terminal-reconcile` (grep, empty).
  - `test_execution_request_replay.py:376` globs only `HISTORY_DIR.glob("dev_loop_*.json")`, a flat glob, so a
    `merge_watch/` subdirectory is invisible to it.
  - `tests/fixtures/histories/pre_m1/` and `tools/record_pre_m1_histories.py` are the precedent for a subdirectory plus
    a recorder.

### Restart

`orchestrator/temporal/start.py:33` sets `DEV_LOOP_ID_REUSE_POLICY = ALLOW_DUPLICATE_FAILED_ONLY` (intake). The
dispatcher uses `ALLOW_DUPLICATE`. The operator restart reads Completed runs only. So a Failed end can be restarted by
intake and by the dispatcher, but not by an operator restart.

### Deployed state checked

- `mctl_get_service_config(team=admins, service=mctl-agents-worker)`: `imageTag: 1.117.0`.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker{,-exec,-implement}/values.yaml`: `image.tag: "1.117.0"` for all
  three workers.
- `.release-please-manifest.json` in the clone: `1.117.0`. The release line therefore predates the 1b marker commit,
  and no deployed worker has recorded `merge-watch-terminal-reconcile`. Caveat: the clone is shallow, and `git tag
  --contains 883b3a1bf` could not resolve the commit. The release-line claim rests on the manifest and the deployed
  tags, not on a git ancestry check.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/issue-1052-.../design.md` sections 3, 8 and 9, and
  `issue-1051-.../design.md` section 4 and `tasks.md` D1-D17: read for the spec and the test catalogue.
- `gh pr view 1053 --comments`: review findings E2 (`_gate_ran_head` not carried) and the unread
  `MERGE_WATCH_RECONCILE_UNRECORDED`, plus the 1d-2a mutation results.

## Proposed solution

### 1. Wiring in `_watch_pr`

Declare `watch_end = ""` and `decision_kind = ""` beside `watch_ended`. Add an `else:` to the existing `while`:

```python
while workflow.now() < deadline and not self._abandoned:
    ...                                                   # unchanged
else:
    if watch.terminal_reconcile and not self._abandoned:  # R7 (unpatched: no command), R6 (ordinary abandon: "")
        decision = await self._decide_watch_end("deadline", watch, service, slug)
        decision_kind = decision.kind
        if decision.last is not None:
            watch.last = decision.last
        if decision.kind == "final":
            return _WatchOutcome(last=decision.last, watch_end=WATCH_END_FINAL_READ)
        if decision.kind == "open":
            watch_end = WATCH_END_FINAL_READ
        elif decision.kind == "abandoned":
            watch_end = WATCH_END_ABANDONED_UNVERIFIED
        # "unrecorded": the flag stays True; finally retains the claim
```

A Python `while ... else` runs only when the condition goes false. `break` and `return` skip it, so the hop, #516,
MERGED/CLOSED, read-error and grace-polls exits are untouched (R8).

After `finally` and before the `if hopping:` return:

```python
if decision_kind == "unrecorded":
    raise ApplicationError(
        "merge watch deadline: pull-request state not established; claim retained",
        type=MERGE_WATCH_RECONCILE_UNRECORDED,
        non_retryable=True,
    )
```

The final return becomes `_WatchOutcome(last=watch.last, ended=watch_ended, watch_end=watch_end)`. The `_watch_pr`
docstring's "Observational, fail-open ... later slices mark such ends" paragraph is corrected for the deadline exit.

**Decision Q-A: map an ordinary abandon to `""`.** The guard `not self._abandoned` keeps an ordinary operator abandon on
today's path. Four reasons:

1. Commands are byte-identical to today, so the existing abandon tests stay unedited.
2. The result is identical to today (`watch_end == ""`, `ended` starts `abandoned: `).
3. `abandoned-unverified` keeps one precise meaning: an abandon that interrupted a deadline decision.
4. An abandon before the deadline is not a deadline end, and the 14-day watch was not waiting for a final answer.

D8 asserts `watch_end == ""` and no `get_pr_state` after the signal. Mutation (v), which drops `and not
self._abandoned`, makes the decision run, settle, see `_abandoned` and return `abandoned`. That gives
`abandoned-unverified` and turns D8 red.

### 2. `finally` guards

```python
if not hopping and not self._watch_unrecorded and watch.track_ownership and self._owned_entity_id:
    ...                                                   # unchanged release/terminal
elif not hopping and self._watch_unrecorded and watch.track_ownership:
    workflow.logger.warning(
        "%s repo=%s workflow=%s exit=deadline last=%s",
        MERGE_WATCH_RECONCILE_UNRECORDED, repo_or_none, workflow.info().workflow_id, last_summary,
    )
```

This is the first reader of `MERGE_WATCH_RECONCILE_UNRECORDED`, alongside the `ApplicationError` type. The flag is
True in two cases: (a) an `unrecorded` decision, and (b) an exception or workflow cancel unwinding through the decision
(R11 of 1d-2a). In both cases the claim is kept and the reconciler reaps it at the liveness bound (about 10 h). That
closes S2: a cancel in the settle, backoff or window no longer writes `release`.

**The `_report_claim_abandonment` guard stays as it is (R10).** On an unrecorded end no relinquishing write is
attempted, so `_claim_abandoned` keeps the value of the last real attempt. Reporting it once is still correct.
Suppressing it would hide an abandoned claim carried in from an earlier failed write.

### 3. `_deliver` guard

```python
await workflow.wait_condition(
    lambda: self._abandoned or self._exiting or self._hopping
    or ((self._is_approved() or self._gates_passed) and not self._watch_unrecorded)
)
...
decided = (self._is_approved() or self._gates_passed) and not self._abandoned and not self._watch_unrecorded
```

The guard is placed on the decision terms only, never on the whole predicate. Appending it to the whole predicate would
keep the wait from ever waking after an `unrecorded` end, because the flag stays True and `_settle_deliveries` waits
for every task. The workflow would hang instead of ending Failed.

With the guard placed this way:

- during a decision, a delivery is held; it adds no command and can be delayed by up to about 80 minutes;
- after `final` or `open` it wakes and lands `Succeeded`;
- after `unrecorded`, `run`'s `except` sets `_exiting`, and the delivery lands `Failed`.

### 4. `MergeWatchResume.gate_ran_head`

- Add `gate_ran_head: str = ""` directly after `merge_gate_settled_head`, with a comment.
- Pass `gate_ran_head=self._gate_ran_head` in the hop record next to `merge_gate_settled_head=`.
- Restore `self._gate_ran_head = resume.gate_ran_head` in `_rehydrate_work_context` next to line 4705.
- E2 adds `"gate_ran_head"` to `M1_ADDED["MergeWatchResume"]` and `"gate_ran_head": ""` to `M1_DEFAULTS`.

This closes review finding E2. After a hop, a gate that already ran at the current head still opens the window instead
of producing a premature `open`.

### 5. Marker

No new `workflow.patched` call is added (count stays 37). The decision runs only under `watch.terminal_reconcile`,
which comes from the existing `merge-watch-terminal-reconcile` marker or the carried resume field.

Replay safety rests on three facts:

1. Every committed fixture lacks the marker, so on replay `patched` returns False and the `else:` arm issues nothing.
2. Every deployed worker is 1.117.0, which never recorded the marker, so no production history recorded the marker
   under the inert code.
3. A history recorded in-test by this code replays clean (D15a); the two committed fixtures follow in 1d-2b-ii (D15b).

**Old-worker consequence.** A history recorded after this slice that contains deadline-decision commands fails with
nondeterminism on any worker below it. Rollback below this slice is therefore unsafe for runs that recorded the marker
and reached the decision. That is B4's (#1007) concern, and the release hold stays ON.

### 6. Tests and fixtures

Split (owner, 2026-11-09): 1d-2b-i is this issue; items marked **(ii)** below belong to 1d-2b-ii and are NOT built here.

- **New module.** `tests/test_merge_watch_final_read.py` holds:
  - D3-D14, D15a, D17 and D18 (see tasks.md);
  - **(ii)** D15b and D16, and a recorder `record_final_read(env, *, hop)`, with `MERGE_WATCH_DEADLINE` monkeypatched to
    40 min and, for the hop variant, `MERGE_WATCH_HISTORY_FLOOR = 1`, under `UnsandboxedWorkflowRunner`, following the
    pattern of `test_deadline_is_carried_not_recomputed_across_hops`;
  - **(ii)** a thin `tools/record_merge_watch_final_read.py` in the style of `tools/record_pre_m1_histories.py`.
- **Fixtures (ii).** `tests/fixtures/histories/merge_watch/dev_loop_final_read.json` and `.../dev_loop_final_read_hop.json`.
  D15a records a history in-test and replays it through the Replayer without committing it.
- **Test-only gate double.** An `ActionApprovalWaitWorkflow` double that ignores the first cancel and is released in
  teardown, for D13. It proves the parent's `workflow.wait` and the flag, not real child cancellation.
- **Gap harness.** `tests/test_merge_watch_worker_gap.py` is converted as in section 5 of the #1051 design:
  - scenario A with `terminal_reconcile=True` becomes `test_deadline_in_gap_reads_the_merged_pr_once_more`;
  - a new `test_unpatched_record_keeps_the_legacy_deadline_end` keeps today's assertions with False;
  - the module docstring is updated.
- **Activation pin.** D17a in `tests/test_merge_watch_decision.py` is replaced by an activation pin.

### 7. Sizing

| Part | Estimate |
|---|---|
| Production: wiring | about 25 lines |
| Production: `finally` guard and log | about 12 lines |
| Production: `_deliver` | 2 expressions |
| Production: resume field, carry and rehydrate | about 6 lines |
| Production: docstrings | about 15 lines |
| Production total | about 60-80 lines, below the issue's 80-110 because the 1d-2a helpers already exist |
| Tests (1d-2b-i) | about 450-550 lines |
| Fixtures and recorder | none in 1d-2b-i (2 fixtures, 1 recorder, D15b, D16 move to 1d-2b-ii, about 150-200 lines) |
| Existing-test edits | E1-E3, the gap-harness pin, D17a |
| Mutation runs | 13 |

The owner applied the pre-declared split on 2026-11-09, so this issue is 1d-2b-i:

- 1d-2b-i (#1055): wiring, guards, `_deliver`, `gate_ran_head`, E1-E3, gap conversion, D3-D14, D15a, D17, D18 and every
  mutation in the table;
- 1d-2b-ii (new issue, after 1d-2b-i is merged): fixtures, recorder, D15b, D16.

The implementer does not trim tests and does not start 1d-2b-ii. If 1d-2b-i still cannot finish in one pass, it stops
and reports on #1055 where it stopped. Nothing from 1d-2b-i is released on its own.

## Alternatives

1. **Map an ordinary abandon to `abandoned-unverified` with no command (the #1051 draft).** Not chosen. It changes the
   typed result of every abandoned watch, including ones that were nowhere near the deadline. It gives
   `abandoned-unverified` two meanings, and it buys nothing a reader needs: the PR state at an ordinary abandon is
   already marked as the last observed one by `ended`. It remains a legitimate choice if the owner prefers it. D8 would
   then assert that value instead, and (v) stays killable.
2. **Drop the guard and let an ordinary abandon run the decision.** Rejected. With something in flight, the commands
   are the same as today's `finally` settle, but the result changes to `abandoned-unverified` (1d-2a design section 3).
   This also needs no extra test edit, but the meaning change is unasked for.
3. **A new patch marker instead of reusing `merge-watch-terminal-reconcile`.** Rejected by the owner ruling of
   2026-11-08. It would add a 38th `workflow.patched` call, a second `MergeWatchResume` bool, and another E2-style row,
   to protect against histories that do not exist (no deployed worker records the marker).
4. **Guard the whole `_deliver` predicate with `and not self._watch_unrecorded`.** Rejected: it deadlocks
   `_settle_deliveries` after an `unrecorded` end (section 3).

## Platform impact

- **New Failed end.** A watch whose PR is open at the deadline, with a gate or tick in flight or with `_gate_ran_head`
  equal to the open head, now ends `Failed` with `MergeWatchReconcileUnrecorded`. Its claim is retained for about 10 h
  until the reconciler's liveness bound. Before this slice it ended with `release` and Completed. This is expected to
  be frequent (a merge gate waiting for approval at the deadline). It is fail-closed, and tests pin it (D6, D11).
- **Restart.** A Failed end can be restarted by intake (`ALLOW_DUPLICATE_FAILED_ONLY`) and by the dispatcher
  (`ALLOW_DUPLICATE`), but not by an operator restart (Completed only). Risk: a re-added intake label on an issue whose
  implement succeeded and whose PR is open starts a second full pipeline, where today it hits "already handled".
  Mitigation: undeployed (release hold ON); 1d-3's reconcile record replaces this interim end before any release.
- **Reader compatibility.** No `DevLoopResult` field changes. `watch_end` gains `final-read` and
  `abandoned-unverified`, both already defined and already read by `cli.py`. mctl-api reads `Ended` and `Implemented`
  on Completed runs only.
- **Delivery latency.** A delivery that binds during a decision is held for up to about 80 minutes: two read sets with
  backoff plus the `GATED_ACTIVITY_TIMEOUT` window.
- **Cost.** At most `2 * FINAL_READ_ATTEMPTS` extra `get_pr_state` activities per watch end, and none on unpatched or
  abandoned paths.
- **Replay and rollback.** The existing fixtures replay unchanged. Rollback below this slice is unsafe for runs that
  recorded the marker and reached the decision. Before release that set is empty, so reverting the PR is safe. After
  release, rollback is governed by B4 (#1007).
- **S3 interim limit.** A workflow cancel delivered during a final-read activity is absorbed by `except ActivityError`.
  That is accepted only while undeployed. D13d pins the observed SDK 1.34.0 surface, and 1d-3's re-raise (y) turns it
  red on purpose.
