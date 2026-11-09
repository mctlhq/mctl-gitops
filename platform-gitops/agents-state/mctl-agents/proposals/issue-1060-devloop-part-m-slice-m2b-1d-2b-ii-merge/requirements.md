# DevLoop Part M, slice M2b-1d-2b-ii: merge-watch final-read fixtures, recorder and replay tests (D15, D16)

## Context

Slice 1d-2b-i (#1055, PR #1058, merge `0ef0e04f5`) wired the merge watch's deadline decision
(`DevLoopWorkflow._decide_watch_end`, `_final_pr_read`, `_settle_watch_work` in
`orchestrator/temporal/workflows/dev_loop.py`). A fresh run whose `merge-watch-terminal-reconcile` marker is recorded
(or a continued run that carries `MergeWatchResume.terminal_reconcile=True`) now reads the PR once more at the deadline
before it lets go of the lifecycle claim. 1d-2b-i explicitly deferred the history half of its spec: the recorder
`record_final_read`, the thin tool `tools/record_merge_watch_final_read.py`, the two committed fixtures under
`tests/fixtures/histories/merge_watch/`, test D15b (the fixtures replay clean) and test D16 (duplicate delivery of the
final-read task). The 1d-2b-i spec lives in mctl-gitops at
`platform-gitops/agents-state/mctl-agents/proposals/issue-1055-devloop-part-m-m2b-1d-2b-wire-the-merge/` (design
section 6, tasks 9, D15 and D16).

This slice is tests and fixtures only. It gives the release gate (B4, #1007) committed evidence that histories
carrying deadline-decision commands replay against today's definitions, and that a redelivered workflow task in the
decision lands the relinquishing write exactly once. No production code changes, so `workflow.patched` stays at 38
(`PATCHED_CALLS` in `tests/test_merge_watch_decision.py`) and no new marker is introduced.

## User stories

- AS the release owner I WANT committed histories that contain a recorded deadline decision SO THAT any later change
  to the decision's command shape fails replay in CI instead of failing in production.
- AS a reviewer I WANT the recorder committed beside the fixtures SO THAT the fixtures can be audited and reproduced.
- AS an operator I WANT proof that a redelivered workflow task in the decision issues one `terminal` and one deploy
  observation SO THAT a worker crash at the deadline cannot double-write the lifecycle store.

## Acceptance criteria (EARS)

Recorder and tool

- WHEN `record_final_read(env, hop=False)` runs THE SYSTEM SHALL drive a fresh `DevLoopWorkflow` under
  `UnsandboxedWorkflowRunner` with `dev_loop.MERGE_WATCH_DEADLINE` monkeypatched to 40 minutes, answer `get_pr_state`
  OPEN before the deadline and MERGED from the deadline on, and return the history of that single run with the
  `final-read` end.
- WHEN `record_final_read(env, hop=True)` runs THE SYSTEM SHALL additionally monkeypatch
  `dev_loop.MERGE_WATCH_HISTORY_FLOOR` to 1, assert the watch continued-as-new at least once, and return the history of
  the last run of the chain (the run that executed the decision), with a fresh OPEN head at the deadline (`final-read`,
  `release` with the fresh head).
- WHEN the tool `tools/record_merge_watch_final_read.py` is run with its output directory set THE SYSTEM SHALL write
  `tests/fixtures/histories/merge_watch/dev_loop_final_read.json`, `.../dev_loop_final_read_hop.json` and a
  `MANIFEST.json` that names the recording commit, the `temporalio` version, the monkeypatched constants, and each
  file's canonical sha256 and workflow id.
- WHEN a fixture is written THE SYSTEM SHALL blank every `stackTrace` and `identity` value, as
  `tools/record_pre_m1_histories.py::_scrub` does.
- WHILE CI runs (`testpaths = ["tests"]`) THE SYSTEM SHALL NOT collect or execute the tool.

D15 (marker and replay)

- WHEN the fresh fixture is read THE SYSTEM SHALL find the `merge-watch-terminal-reconcile` patch id exactly once.
- WHEN the hop fixture is read THE SYSTEM SHALL find that patch id zero times and a start input whose
  `resume.terminal_reconcile` is True.
- WHEN each committed fixture is replayed through `Replayer(workflows=[DevLoopWorkflow],
  workflow_runner=UnsandboxedWorkflowRunner())` under the constants named in its manifest entry THE SYSTEM SHALL
  replay without a nondeterminism error.
- WHEN a fixture's canonical sha256 differs from `MANIFEST.json`, or the manifest lists a file not on disk (or the
  reverse) THE SYSTEM SHALL fail.
- WHEN a fresh run is recorded in-test and replayed in the same test (D15a) THE SYSTEM SHALL replay clean, for both
  the fresh and the hop variant.
- WHEN an unpatched record (`terminal_reconcile=False`) rides across the deadline THE SYSTEM SHALL schedule no
  `get_pr_state` at or after the deadline, and its in-test recording SHALL replay clean.
- WHILE this slice is applied THE SYSTEM SHALL keep `tests/test_workflow_replay.py`,
  `tests/test_execution_request_replay.py`, `tests/test_pre_m1_compat.py` and `tests/test_patch_memoization.py`
  green with no edits to them.

D7 (ordering, read from history)

- WHEN the fresh fixture is read THE SYSTEM SHALL show, after the last pre-deadline `get_pr_state` schedule, the
  first post-deadline `get_pr_state` schedule before the `lifecycle_ownership` schedule that carries the `terminal`
  op, and that `terminal` schedule before the deploy observation (`resolve_deploy_target`).
- WHEN the hop fixture is read THE SYSTEM SHALL show the post-deadline `get_pr_state` schedule before the
  `lifecycle_ownership` schedule that carries `release`.

D16 (duplicate delivery of the final-read task)

- IF the workflow task that processes the MERGED final-read result fails once and is redelivered THEN THE SYSTEM
  SHALL execute exactly one `terminal` ownership op and schedule exactly one deploy observation.
- WHEN that history (containing one `WORKFLOW_TASK_FAILED`) is replayed through the plain `DevLoopWorkflow` THE
  SYSTEM SHALL replay clean, that is, add no command beyond those recorded.

## Out of scope

- 1d-3 (`record_merge_watch_reconcile`, liveness, cancellation re-raise, #1022) and 1d-4 (grace-polls and read-error
  exits, `confirm_no_pr`).
- Any production change in `orchestrator/`, any mctl-api change, any release, tag or deploy. B4 (#1007) stays FAIL,
  the release hold stays ON.
- Carry-over items that are not history-shaped: D9 window variant, D12, D13b-e and D14. They are deferred to a
  separate coverage slice (see Open questions).
- Closing #1029 (owner's call). The PR uses `Refs #1021`, never `Closes`.

## Open questions

- Carry-over split: this proposal takes D15a and D7 (both read recorded histories, so they share this slice's
  harness) and defers D9-window, D12, D13b-e and D14 to a follow-up coverage slice. If the owner wants them here, they
  extend `tests/test_merge_watch_final_read.py` with the existing `_resume_run` / `_released_gate_run` harness and no
  new infrastructure.
- "Duplicate delivery of the final-read task" is read as a redelivered WORKFLOW task (first attempt fails after the
  final-read activity completed, the server retries the task, the worker replays from history). The alternative
  reading, a redelivered `get_pr_state` ACTIVITY task, would by design produce two reads and is not what "one landed
  `terminal`" asserts. This proposal uses the workflow-task reading.
- The hop fixture commits only the last run of the chain (the one holding the decision). The earlier runs carry no
  decision command and continued-as-new chains are already covered by `tests/test_pre_m1_compat.py`. If the owner
  wants the whole chain, name the files `dev_loop_final_read_hop_run<N>.json` like the pre-M1 set.
- Fixture branch choice: fresh = MERGED (`terminal` and deploy observation), hop = OPEN with a fresh head (`release`).
  This covers both relinquishing writes; the unreadable (`unrecorded`) end is not committed as a fixture because it
  is an interim end that 1d-3 replaces.
