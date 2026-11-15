# DevLoop Part M, slice M2b-1b: reconcile patch marker, carried resume field, and pure refactors of the merge watch

## Context

Issue mctlhq/mctl-agents#1036 asks for slice M2b-1b of the sequential plan recorded on #1021. It covers tasks 3
and 4 of the approved #1021 proposal and nothing else. The #1021 proposal lives in mctl-gitops at
`platform-gitops/agents-state/mctl-agents/proposals/issue-1021-devloop-part-m-m2b-feedback-tick-and-dea/`, approved
digest `sha256:e833d2af0ce3ce1e30699e6a77d221ba34af8948175c1ad75f2f0acd566fb144`. It is the specification for both
tasks and is not edited. Task 3 adds the patch marker `MERGE_WATCH_RECONCILE_PATCH = "merge-watch-terminal-reconcile"`
and the carried field `MergeWatchResume.terminal_reconcile`. Task 4 is a behaviour-neutral refactor of
`DevLoopWorkflow._watch_pr` in `orchestrator/temporal/workflows/dev_loop.py`:
- it extracts the found branch's bookkeeping into `_apply_found_state`;
- it extracts the MERGED/CLOSED ownership write into `_terminal_claim`;
- it moves the watch's poll locals into a per-run `watch` record.

Later slices build on this. M2b-1c adds the activities. M2b-1d adds the final read at the deadline exit, which turns
the gap harness of #1029 (`tests/test_merge_watch_worker_gap.py`) green. This slice lays the foundation only. It
records the marker decision and carries it across continue-as-new hops, but no behaviour depends on it yet. The
refactor gives 1c/1d named seams (`_apply_found_state`, `_terminal_claim`, the `watch` record) without changing a
single command in any recorded or future history. The #1029 harness must still show the defect afterwards: scenario A
ends on a stale `OPEN` with no final read.

## User stories

- AS the DevLoop maintainer I WANT the terminal-reconcile decision recorded once, when a watch starts fresh, and carried
  verbatim across hops SO THAT M2b-1d can gate the final read on it without a hop ever changing a watch's answer.
- AS a reviewer I WANT the found-branch refactor to be command-identical, proven by unchanged replay fixtures and by
  mutation evidence, SO THAT M2b-1d's wiring can reuse `_apply_found_state` and `_terminal_claim` safely.
- AS the owner of the B4 rollback analysis (#1007) I WANT the new marker name and its rollback consequence stated SO
  THAT B4 can account for histories that carry it.

## Acceptance criteria (EARS)

- WHEN `_watch_pr` runs with `resume is None` (fresh-start arm) THE SYSTEM SHALL evaluate
  `workflow.patched(MERGE_WATCH_RECONCILE_PATCH)` exactly once, right after
  `workflow.patched(PROPOSAL_TERMINAL_PATCH)`, and store the result in the watch's `terminal_reconcile`.
- WHEN `_watch_pr` runs with a `resume` record THE SYSTEM SHALL take `terminal_reconcile` from
  `resume.terminal_reconcile` and SHALL NOT call `workflow.patched(MERGE_WATCH_RECONCILE_PATCH)`.
- WHILE `_resume_merge_watch` executes THE SYSTEM SHALL NOT call `workflow.patched` for `MERGE_WATCH_RECONCILE_PATCH`.
- WHEN a fresh DevLoop run reaches the merge watch THE SYSTEM SHALL record the `merge-watch-terminal-reconcile` marker
  exactly once in that run's history.
- WHEN a run starts from a `MergeWatchResume` THE SYSTEM SHALL record the `merge-watch-terminal-reconcile` marker zero
  times in that run's history.
- WHEN the merge watch hops via continue-as-new THE SYSTEM SHALL write the current `terminal_reconcile` into the
  `MergeWatchResume` it returns, unchanged.
- WHEN the merge watch hops THE SYSTEM SHALL write the first run's absolute `deadline` into that record, unchanged and
  never recomputed from `workflow.now()`.
- IF a `MergeWatchResume` predates this change (no `terminal_reconcile` key) THEN THE SYSTEM SHALL decode it as
  `terminal_reconcile=False`.
- WHILE `terminal_reconcile` is True or False THE SYSTEM SHALL behave identically: no command, timer, activity,
  return value or ownership write depends on it in this slice.
- WHEN a poll finds a PR (`state.found`) THE SYSTEM SHALL issue the same commands in the same order as before the
  refactor. Through `_apply_found_state` it SHALL perform these steps in order:
  1. set `last` and `self._last_pr`;
  2. reset `polls_without_pr` and `terminal_status_polls`;
  3. set `saw_open_pr` for a non-terminal state;
  4. increment the heartbeat index and `await self._track_ownership(state)` under the same guard.
  Then, for MERGED/CLOSED, `_terminal_claim` SHALL issue the same `terminal` `_ownership` write and the same
  `_finish_claim`, followed by the same return.
- WHILE the poll loop runs THE SYSTEM SHALL keep `last`, `polls_without_pr`, `terminal_status_polls`, `saw_open_pr`,
  `tick_task`, `gate_task`, `track_ownership` and `poll_index` in a per-run, never-serialized `watch` record. The hop
  record, the `finally` block and every return SHALL read them from that record.
- WHEN any existing replay fixture under `tests/fixtures/histories/` (including `pre_m1/`) is replayed THE SYSTEM SHALL
  replay it green with no fixture edit and no re-recording. No existing fixture contains the new marker.
- WHEN `tests/test_merge_watch_worker_gap.py` runs THE SYSTEM SHALL pass with the file unchanged. Scenario A still ends
  on the pre-gap `OPEN` with no read after the gap.
- WHEN `tests/test_patch_memoization.py` runs THE SYSTEM SHALL pass.
- WHEN the new `MergeWatchResume.terminal_reconcile` field is added THE SYSTEM SHALL make exactly these three edits, and
  no others, to the existing file `tests/test_pre_m1_compat.py`. They extend that file's own pin table for a carried
  dataclass and change no assertion (amendment v2, see "Amendment v2" below):
  1. add `"terminal_reconcile"` to `M1_ADDED["MergeWatchResume"]`;
  2. add `"terminal_reconcile": False` to `M1_DEFAULTS`;
  3. add `terminal_reconcile=True` to the `MergeWatchResume(...)` sample in `_m1_values()`, next to
     `deferred_resume_contract=True`, because `test_unsupported_direction_pre_m1_decoder_silently_drops_m1_fields`
     asserts that every `M1_ADDED` field changes on the pre-M1 round trip.
  `tests/fixtures/pre_m1/dataclass_fields.json` SHALL NOT be edited or regenerated: it is the recorded pre-M1 truth.
- IF making any of the above true would require editing any other existing test or fixture, a non-command-identical
  refactor, a change to the gap harness, or any M2b-1c/1d behaviour (final read, new activity, typed result) THEN THE
  SYSTEM change SHALL NOT be made, and the implementer SHALL stop and report on #1036. The three sanctioned edits above
  are the only exception, and the PR body SHALL list them explicitly.
- WHEN the implementer PR is opened THE SYSTEM SHALL be verified as blocked by GitHub (the code-owner hold from #1020).
  If it is not blocked, the implementer SHALL stop. No autonomous merge, admin bypass, release, deployment or flag
  change.

## Amendment v2 (2026-11-07)

The first implementer attempt (run `mctl-agents-implement-5b5707bc`) stopped without commits, correctly. Adding the
field breaks four existing tests in `tests/test_pre_m1_compat.py`, which pins the field set of every carried dataclass,
and the first version of this proposal forbade any test edit. A sweep of the whole suite on `bd3f51a` (all 209 test
files, in batches under `timeout 300`, no batch timed out) with the change applied found exactly these four tests and
nothing else, all fixed by the three edits above, with `tests/test_pre_m1_compat.py` at 109 passed and the complete
suite green afterwards. No history fixture needs re-recording. This amendment sanctions those three edits and nothing
more, and records the B4 coupling raised by the B4 owner:

- WHEN the PR is prepared THE SYSTEM SHALL state that `merge-watch-terminal-reconcile` is a new Temporal marker that the
  B4 marker classification (MS-1) must classify as MARKER_PRESENT, MARKER_ABSENT or MARKER_UNKNOWN before the build
  carrying it ships.
- WHEN the PR is prepared THE SYSTEM SHALL state that the forward-only rollback boundary moves up to the first build
  that carries the marker: a rollback below that build is unsafe for fresh watches, and the B4 scenario "the fixed
  worker does not start" must cover this marker.
- WHEN the PR is prepared THE SYSTEM SHALL state the observed old-worker decode result (see design.md, Platform impact)
  and SHALL NOT claim that an old worker can replay a history containing the new marker; that is unverified.
- Worker Versioning (B4 option A) does not block shipping this slice under the forward-only baseline.

## Out of scope

- M2b-1c: `confirm_no_pr`, `NoPrProof`, `record_merge_watch_reconcile` and their dataclasses.
- M2b-1d: `_settle_watch_work`, `_final_pr_read`, `_decide_watch_end`, `_record_reconcile`, the final read at any exit,
  decision wiring, `DevLoopResult.watch_end` or any typed result, CLI, new replay fixtures.
- Turning `tests/test_merge_watch_worker_gap.py` scenario A green.
- Other `MergeWatchResume` fields named by #1021 for later slices (`gate_ran_head`, `tick_blocked_until`).
- Any hop or continue-as-new behaviour change beyond carrying the new field.
- Editing the #1021 proposal files; restarting #1021's DevLoop; umbrella #993; B4 (#1007), the release hold, #1003,
  gitops#2394, mctl-api#934.
- Any worker image bump, deployment, or flag change (`services/admins/mctl-agents-worker*` stays as is).

## Open questions

- The #1021 design names the terminal helper with two signatures: `_terminal_claim(fresh, watch)` in the pseudocode
  and `_terminal_claim(state, track_ownership)` in the helper list. This proposal uses `_terminal_claim(state, watch)`
  and reads `watch.track_ownership`. Either way it issues the same write. Reviewers may prefer the other signature;
  it does not change commands.
- The #1021 `watch` record also mentions "settled tasks" and later fields (`tick_blocked_until`). This slice moves only
  the eight locals the issue lists. `cadence`, `shepherd_in_loop`, `concurrent_ticks`, `proposal_terminal_end`,
  `shepherd_ticks`, `hops`, `polls_this_run`, `hopping`, `resume_record` and `watch_ended` stay locals. The new
  `terminal_reconcile` is also stored on the record, so 1d can read it there. Moving more is deferred to 1d.
- Exact name of the per-run record class (`_MergeWatchRun` is proposed) is not fixed by #1021.
