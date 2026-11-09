# DevLoop Part M, slice M2b-1d-2b-ii: merge-watch final-read fixtures, recorder and replay tests (D15, D16)

## Context

Slice 1d-2b-i (#1055, PR #1058, merge `0ef0e04`) wired the merge watch's deadline decision
(`DevLoopWorkflow._decide_watch_end` in `orchestrator/temporal/workflows/dev_loop.py`) into `_watch_pr`. Its
spec (mctl-gitops `platform-gitops/agents-state/mctl-agents/proposals/issue-1055-devloop-part-m-m2b-1d-2b-wire-the-merge/`,
design section 6, tasks 9, D15b and D16) deferred the committed-fixture half to this slice: a recorder, a thin recording
tool, two committed histories under `tests/fixtures/histories/merge_watch/`, the replay test over them (D15b), and the
duplicate-delivery test (D16). `tests/test_merge_watch_final_read.py` on main says so in its module docstring.

This slice is tests, fixtures and one test-support tool only. It adds no production code, no `workflow.patched` call
(the count stays 38, pinned by `PATCHED_CALLS` in `tests/test_merge_watch_decision.py`), and no release. It also takes a
subset of the coverage items 1d-2b-i did not write (D7, D9 window variant, D12, D14, D15a). D13b-e are deferred to 1d-3
(see Out of scope). The aim is that a recorded history of the deadline decision becomes a permanent replay input, so a
later change that alters the decision's command stream fails CI instead of wedging an in-flight execution.

## User stories

- AS the DevLoop owner I WANT committed histories of a fresh and of a hopped watch that reach the deadline decision
  SO THAT every later change to `_watch_pr` and `_decide_watch_end` is replayed against them in CI.
- AS a reviewer I WANT the recorder and the tool that produced the fixtures committed beside them SO THAT the fixtures
  can be audited and re-recorded on purpose, never by accident.
- AS the DevLoop owner I WANT proof that a workflow task carrying the final-read result, processed twice, gives exactly
  one relinquishing write and one deploy observation SO THAT a worker restart at the deadline cannot double-write the
  lifecycle claim.

## Acceptance criteria (EARS)

Recorder and tool

- WHEN `record_final_read(env, hop=False)` runs THE SYSTEM SHALL drive a fresh `DevLoopWorkflow` under
  `UnsandboxedWorkflowRunner` with `MERGE_WATCH_DEADLINE` monkeypatched to 40 minutes, answer OPEN to every in-loop
  poll and MERGED to the post-deadline read, and return the completed handle.
- WHEN `record_final_read(env, hop=True)` runs THE SYSTEM SHALL additionally monkeypatch `MERGE_WATCH_HISTORY_FLOOR`
  to 1, so the watch continues-as-new before the deadline, and return a handle to the last run of the chain (the run
  that executes the decision).
- WHEN `tools/record_merge_watch_final_read.py` is run with `MERGE_WATCH_OUT` set THE SYSTEM SHALL write
  `dev_loop_final_read.json` and `dev_loop_final_read_hop.json` into that directory, with stack traces and worker
  identities scrubbed, and register each file's canonical sha256, workflow id, recording commit and temporalio version
  in `tests/fixtures/histories/merge_watch/MANIFEST.json`.
- IF `MERGE_WATCH_OUT` is unset THEN the tool SHALL skip and write nothing, so a plain `pytest` run never re-records.

Fixtures (D15b)

- THE SYSTEM SHALL commit `tests/fixtures/histories/merge_watch/dev_loop_final_read.json` and
  `tests/fixtures/histories/merge_watch/dev_loop_final_read_hop.json`.
- WHEN each committed fixture is replayed by `Replayer(workflows=[DevLoopWorkflow],
  workflow_runner=UnsandboxedWorkflowRunner())` with the recording's monkeypatches applied THE SYSTEM SHALL replay
  it without a nondeterminism error.
- THE SYSTEM SHALL assert that each fixture is not vacuous: the fresh fixture records the
  `merge-watch-terminal-reconcile` marker exactly once, the hop fixture zero times; each has at least one
  `get_pr_state` scheduled after the last in-loop poll timer, and a `terminal` ownership write after it.
- THE SYSTEM SHALL assert that each fixture's canonical sha256 matches `MANIFEST.json`, and that every `*.json` in
  `merge_watch/` other than the manifest is listed in it.

Marker and replay (D15, including the D15a carry-over)

- WHEN a fresh run reaches the deadline THE SYSTEM SHALL record the marker once; WHEN a continued run reaches it THE
  SYSTEM SHALL record it zero times.
- WHEN a run whose resume record carries `terminal_reconcile=False` rides past the deadline THE SYSTEM SHALL make no
  post-deadline read, and its history SHALL replay clean.
- WHEN a history is recorded in-test by today's code (fresh and hop) THE SYSTEM SHALL replay it clean without
  committing it (D15a).
- WHILE this slice is applied `tests/test_workflow_replay.py`, `tests/test_execution_request_replay.py`,
  `tests/test_pre_m1_compat.py` and `tests/test_patch_memoization.py` SHALL stay green without edits, and the
  `merge_watch/` subdirectory SHALL NOT be picked up by the top-level orphan check in `test_workflow_replay.py`.

Duplicate delivery (D16)

- WHEN the workflow task that carries the final-read MERGED result is processed twice (a worker with
  `max_cached_workflows=0`, and separately a worker restarted between the read's completion and the next task) THE
  SYSTEM SHALL issue exactly one `terminal` ownership write, schedule the deploy observation (`resolve_deploy_target`)
  exactly once, and end Completed.
- WHEN the resulting history is replayed THE SYSTEM SHALL issue no command beyond those recorded.

Carry-over coverage

- WHEN D3, D4, D5 and D6 runs end THE SYSTEM SHALL show in history: the settle commands, then the first post-deadline
  read, then the relinquishing write where one exists (D7).
- WHEN the final read answers OPEN THE SYSTEM SHALL set `_last_pr` and `saw_open_pr`, reset the poll counters and hold
  the claim; WHEN a MERGED is first seen by the final read with no claim THE SYSTEM SHALL write `acquire` then
  `terminal` (D12).
- IF an abandon arrives while `_settle_watch_work` waits on an in-flight gate THEN THE SYSTEM SHALL make no read after
  the settle, end `abandoned-unverified` and write `release` (D14).
- IF an abandon arrives during the gate window THEN THE SYSTEM SHALL wake at once, make no further read, end
  `abandoned-unverified` and write `release` (D9 window variant).

## Out of scope

- Any production change (`orchestrator/`), any new `workflow.patched` marker, any mctl-api change.
- Any release, tag or deploy. B4 (#1007) stays FAIL and the release hold stays ON. Workers stay on 1.117.0.
- 1d-3: `record_merge_watch_reconcile`, liveness, cancellation re-raise (#1022). The cancellation pins D13b-e are
  deferred to 1d-3, because 1d-3 changes the cancellation surface they would pin (the 1d-2b-i spec says 1d-3's (y)
  turns D13d red).
- 1d-4: grace polls, read-error exits, `confirm_no_pr`.
- Closing #1029. The PR uses `Refs #1021`, not `Closes`.
- Re-recording any existing fixture under `tests/fixtures/histories/` or `pre_m1/`.

## Open questions

- Carry-over split: this proposal takes D7, D9 window, D12, D14 and D15a, and defers D13b-e to 1d-3. The owner may
  move D13b-e back in, or move all carry-over to 1d-3, without changing the D15/D16 core.
- "Duplicate delivery of the final-read task" is read as a workflow task redelivered or reprocessed by a worker that lost
  its cache. The read is a read-only activity, and the server deduplicates activity completions. Both forms
  (cache-disabled worker, worker restart) are proposed. If the owner meant a different form, only T7 changes.
- The hop fixture is one file, but a hop chain has several runs. This proposal commits the last run, the one that
  executes the decision with the carried `terminal_reconcile=True` and no marker. Earlier runs are covered by D15a's
  in-test replay, not committed.
- A 40-minute deadline cannot be patched under the sandboxed runner, because the sandbox re-imports the module (see the
  comment above `DEADLINE` in `tests/test_merge_watch_final_read.py`). The fixtures can therefore only be replayed
  unsandboxed with the same monkeypatches. This matches how `test_pre_m1_compat.py` replays the pre-M1 hop chain.
