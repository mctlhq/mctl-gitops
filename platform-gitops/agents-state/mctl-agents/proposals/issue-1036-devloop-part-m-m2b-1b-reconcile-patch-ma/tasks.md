# Tasks: issue-1036-devloop-part-m-m2b-1b-reconcile-patch-ma

All code changes are in `orchestrator/temporal/workflows/dev_loop.py`. New tests go in `tests/test_patch_memoization.py`
(T1) and `tests/test_dev_loop_workflow.py` (T2-T4). No existing fixture is edited. The only sanctioned edits to an
existing test are the three pin-table edits in `tests/test_pre_m1_compat.py` listed in task 2a (amendment v2). Base:
`bd3f51a`. To run the suite in a worktree outside the workspace, symlink a sibling `mctl-gitops` checkout first, or
four test files fail on the baseline as well (see design.md, Risks).

- [ ] 1. Write the new tests T1-T4 first and run them against `bd3f51a`. Capture red output (`timeout 300 uv run pytest
  <ids> -q`) for the PR - DoD: each new test fails for the stated reason (missing constant/field/helper/record), output
  pasted.
- [ ] 2. Add `MERGE_WATCH_RECONCILE_PATCH = "merge-watch-terminal-reconcile"` beside `PROPOSAL_TERMINAL_PATCH`, with a
  comment stating the rule:
  - evaluated only in the fresh-start arm;
  - carried in `MergeWatchResume.terminal_reconcile`;
  - never evaluated in `_resume_merge_watch`;
  - consumed by nothing until M2b-1d.
  Add `terminal_reconcile: bool = False` to `MergeWatchResume` after `proposal_terminal_end` (depends on 1) - DoD:
  module imports; an old-shape `MergeWatchResume(...)` without the key decodes `False`.
- [ ] 2a. Make the three sanctioned edits in `tests/test_pre_m1_compat.py` and nothing else in that file (depends on 2):
  - add `"terminal_reconcile"` to `M1_ADDED["MergeWatchResume"]`;
  - add `"terminal_reconcile": False` to `M1_DEFAULTS`;
  - add `terminal_reconcile=True` to the `MergeWatchResume(...)` sample in `_m1_values()`.
  Do not touch `tests/fixtures/pre_m1/dataclass_fields.json`. DoD: `timeout 300 uv run --locked pytest
  tests/test_pre_m1_compat.py -q` shows 109 passed; the diff of that file is exactly these three hunks; the red output
  of the four affected tests before the edits (3 on adding the field, plus the silent-drop test after the first two
  edits) is pasted in the PR.
- [ ] 3. Wire the marker in `_watch_pr` (depends on 2):
  - fresh arm: `terminal_reconcile = workflow.patched(MERGE_WATCH_RECONCILE_PATCH)` immediately after the
    `PROPOSAL_TERMINAL_PATCH` line;
  - resume arm: `terminal_reconcile = resume.terminal_reconcile`;
  - hop record: `terminal_reconcile=...`.
  No reader of the flag is added, and no `patched` call goes into `_resume_merge_watch` - DoD: T1, T2 green;
  `tests/test_patch_memoization.py` green.
- [ ] 4. Add the private mutable dataclass `_MergeWatchRun` with these fields:
  - `last`, `polls_without_pr`, `terminal_status_polls`, `saw_open_pr`;
  - `track_ownership`, `poll_index`, `terminal_reconcile`;
  - `tick_task`, `gate_task`.
  Build it in `_watch_pr` after both arms. Replace every use of those locals with `watch.<name>`: the loop, the hop
  record, `_finish_gate`/`_settle_gate` args, the `finally` block and every `_WatchOutcome` return. No statement moves
  across an `await` (depends on 3) - DoD: T4 green; every existing test listed under Tests green.
- [ ] 5. Extract `_apply_found_state(state, watch)` and `_terminal_claim(state, watch)` from the found branch. Keep
  the statements, guards, arguments and order verbatim, and move the existing comments with them. The found branch
  becomes three steps: apply, then terminal-claim-and-return for MERGED/CLOSED, then the unchanged tick and gate
  blocks (depends on 4) - DoD: T3 green; replay suite green with `git diff --stat tests/` showing only additions of new
  tests plus the three sanctioned hunks in `tests/test_pre_m1_compat.py`.
- [ ] 6. Run the full evidence batches, each under `timeout 300`, and record the exact commands and outputs (depends
  on 5):
  - `tests/test_patch_memoization.py`;
  - `tests/test_workflow_replay.py tests/test_pre_m1_compat.py tests/test_execution_request_replay.py
    tests/test_implement_sweep_replay.py`;
  - `tests/test_merge_watch_worker_gap.py`;
  - `tests/test_temporal_marker_scan.py`;
  - `tests/test_dev_loop_workflow.py`, in `-k` batches that each fit 300 s;
  - `ruff check` and the repo's type check, if configured in `pyproject.toml`.
  Then run `git diff --exit-code bd3f51a -- tests/fixtures tests/test_merge_watch_worker_gap.py`, and `grep -rl
  merge-watch-terminal-reconcile tests/fixtures`, which must find nothing - DoD: all green; both checks empty.
- [ ] 7. Mutation proof (depends on 6). Apply each mutation locally, run the named test, paste the red output, then
  revert. None appears in the diff.
  - M-a: also call `workflow.patched(MERGE_WATCH_RECONCILE_PATCH)` in `_resume_merge_watch`. Expected red: T1 (resumed
    run marker count 1 != 0).
  - M-b: write `deadline=(workflow.now() + MERGE_WATCH_DEADLINE)` into the hop record. Expected red: T2 (deadline
    assertion).
  - M-c: drop `terminal_reconcile=` from the hop record. Expected red: T2 (carried True becomes False).
  - M-c2: the resume arm evaluates `workflow.patched(...)` instead of reading `resume.terminal_reconcile`. Expected
    red: T1.
  - M-d1: call `_terminal_claim` before `_apply_found_state`. Expected red: replay of
    `tests/fixtures/histories/dev_loop_resumed.json` (and the other fixtures with a fresh watch) in
    `tests/test_workflow_replay.py`, plus the existing `ops[-1].op == "terminal"` ownership tests in
    `tests/test_dev_loop_workflow.py`.
  - M-d2: drop `await self._track_ownership(state)` from `_apply_found_state`. Expected red: the same replay fixtures
    and the ownership tests.
  - M-e: omit `watch.saw_open_pr = True` in `_apply_found_state`. Expected red: T3 and the existing #516 once-open-PR
    tests in `tests/test_dev_loop_workflow.py`.
  DoD: seven red outputs pasted; a final clean run green.
- [ ] 8. Open the PR and write its body (depends on 7). The body states:
  - this proposal and its approved digest, and #1021 as the specification;
  - the red/green evidence, the mutation table and the explicit replay statement ("all existing fixtures replay
    unchanged; none contains the marker");
  - the new marker name and its rollback consequence for B4 (#1007), and the unknown-key decode check result;
  - that `tests/test_merge_watch_worker_gap.py` is unchanged and still shows the defect;
  - that M2b-1c/1d are not started.
  Verify on GitHub that the PR is blocked by the code-owner hold (#1020); if not blocked, stop and report on #1036.
  No merge, bypass, release, deploy or flag change - DoD: PR open, blocked, evidence complete.

STOP and report on #1036, with no workaround, if:
- any existing test other than the three sanctioned `tests/test_pre_m1_compat.py` edits, or any fixture, needs editing
  or re-recording;
- the refactor cannot be made command-identical;
- the gap harness needs a change;
- any 1c/1d behaviour (final read, new activity, typed result) turns out to be needed.

## Tests

- [ ] T1. `tests/test_patch_memoization.py`, modelled on
  `test_the_deferred_resume_marker_is_recorded_once_fresh_and_never_on_a_merge_watch_hop`. A fresh `DevLoopWorkflow.run`
  driven to a merged PR records `merge-watch-terminal-reconcile` exactly once. A run started from a `MergeWatchResume`
  records it zero times (#1021 T-11, marker part).
- [ ] T2. `tests/test_dev_loop_workflow.py`, hop carry. Force a hop with the existing
  `_FakeContinueAsNewInfo(suggested=True, ...)` monkeypatch, starting from a resume record with
  `terminal_reconcile=True` and a fixed absolute `deadline`. The continued run's input carries
  `terminal_reconcile=True` and the identical `deadline` string. A fresh-started watch that hops carries the value
  `patched` returned (True on the test server). A record built without the key decodes `False`.
- [ ] T3. `tests/test_dev_loop_workflow.py`, unit test of `_apply_found_state` and `_terminal_claim` on a workflow
  instance with fake `_track_ownership`/`_ownership`/`_finish_claim`:
  - for an OPEN state it sets `last`, `_last_pr`, zeroes both counters, sets `saw_open_pr`, increments the heartbeat
    index and calls `_track_ownership` once;
  - for MERGED it does not set `saw_open_pr`;
  - `_terminal_claim` issues exactly one `terminal` write and one `_finish_claim` only when `track_ownership and
    _owned_entity_id`.
- [ ] T4. `tests/test_dev_loop_workflow.py`, structural check: `_MergeWatchRun` exists, is not frozen, and has
  exactly the fields listed in task 4. `MergeWatchResume` does not contain it (the record is never serialized).
- [ ] T5. Unchanged (apart from the sanctioned edits to `tests/test_pre_m1_compat.py`) and green, as pins: `tests/test_merge_watch_worker_gap.py` (scenario A still ends on `OPEN` with no
  read after the gap), all of `tests/test_workflow_replay.py`, `tests/test_pre_m1_compat.py`,
  `tests/test_execution_request_replay.py`, `tests/test_patch_memoization.py`, `tests/test_temporal_marker_scan.py`,
  and every existing `_watch_pr` test in `tests/test_dev_loop_workflow.py`.

## Rollback

- **Before merge.** Close the PR; nothing is deployed.
- **After merge, before any image carrying it is deployed.** Revert the merge commit. No history anywhere contains
  the marker, so the revert is free.
- **After a later, separately approved deployment.** Fresh merge watches will have recorded
  `merge-watch-terminal-reconcile`. A plain revert-and-redeploy could make those histories non-deterministic on
  replay. The safe rollback is one of two options:
  - a forward fix that keeps the `patched` call and adds nothing;
  - a `workflow.deprecate_patch(MERGE_WATCH_RECONCILE_PATCH)` release first, waiting for marker-carrying executions to
    drain, measured with a marker scan like `tools/temporal_marker_scan.py`.
  This is the input B4 (#1007) needs; this slice decides nothing for B4.
- **The refactor alone.** It emits identical commands, so reverting it has no replay consequence.
