# Design: issue-1060-devloop-part-m-slice-m2b-1d-2b-ii-merge

## Current state

Production (read only, unchanged by this slice), `orchestrator/temporal/workflows/dev_loop.py` at `0ef0e04`:

- `MERGE_WATCH_RECONCILE_PATCH = "merge-watch-terminal-reconcile"` (line 505). `MERGE_WATCH_DEADLINE = timedelta(days=14)`
  (568), `MERGE_WATCH_HISTORY_FLOOR = 4096` (579), `FINAL_READ_ATTEMPTS = 3`, `FINAL_READ_BACKOFF = 2 min` (636-637).
- `_watch_pr` (6677) evaluates `terminal_reconcile = workflow.patched(MERGE_WATCH_RECONCILE_PATCH)` only in the
  fresh-start arm. A continued run takes `resume.terminal_reconcile` from `MergeWatchResume`, so a hop records no
  marker. The deadline is `workflow.now() + MERGE_WATCH_DEADLINE` on a fresh run and `resume.deadline` on a hop.
- `_decide_watch_end` (6638) settles in-flight work (`_settle_watch_work`, 6593), reads the PR via `_final_pr_read`
  (up to `FINAL_READ_ATTEMPTS`), optionally waits the `GATED_ACTIVITY_TIMEOUT` window and reads again, then writes
  `terminal` (`_terminal_claim`) on MERGED/CLOSED. The deploy observation is `_observe_deploy` (5080), which schedules
  `resolve_deploy_target` first.
- `workflow.patched(` occurs 41 times textually in `dev_loop.py`. `PATCHED_CALLS = 38` in
  `tests/test_merge_watch_decision.py:557` is the pinned count, and this slice leaves it unchanged.

Tests and fixtures:

- `tests/test_merge_watch_final_read.py` (660 lines) holds D3-D6, D6b, D8, D9 (read-OPEN, read-MERGED, backoff),
  D10, D11, D13 and D18. Its docstring says the recorder, D15b and D16 belong to 1d-2b-ii. Harnesses: `_ride_to_deadline`
  (sandboxed, real 14-day deadline, time-skipping) and `_resume_run` (resume record with a short `offset`, optional
  `unsandboxed`, `gate`, `wait_cls`), plus `_StubbornWait` and `_released_gate_run` for the gate window.
- It has no D7, D12, D14, D15a or D9 window variant (grep of test names and docstrings). The 1d-2b-i tasks.md lists
  them, and #1060 lists them as carry-over.
- `tests/test_patch_memoization.py::test_the_terminal_reconcile_marker_is_recorded_once_fresh_and_never_on_a_merge_watch_hop`
  already pins marker 1 vs 0, using a resume record with a 2027 deadline. It does not ride a run to the deadline.
- `tests/test_dev_loop_workflow.py::test_deadline_is_carried_not_recomputed_across_hops` (around line 7884) is the
  pattern the spec names: `MERGE_WATCH_HISTORY_FLOOR = 1`, `MERGE_WATCH_DEADLINE = 40 min`, `UnsandboxedWorkflowRunner`.
- `tools/record_pre_m1_histories.py` is the style reference. It is a pytest file run on demand with an `*_OUT` env var,
  with `_scrub` (blanks `stackTrace`/`identity`), `_canonical_sha256` and `_write`, which registers each file in
  `MANIFEST.json` with its sha256 and `workflow_id`. `tests/test_pre_m1_compat.py` replays the hop chain under
  `UnsandboxedWorkflowRunner` with the floor monkeypatched (lines 373-383), and checks fixtures against the manifest.
- `tests/test_workflow_replay.py::test_every_recorded_fixture_belongs_to_a_scenario` uses
  `Path(HISTORY_DIR).glob("*.json")`, which is non-recursive, so `merge_watch/` is invisible to it, as `pre_m1/` already
  is. `tests/test_temporal_marker_scan.py` and `tests/test_temporal_nondeterminism_scan.py` read named files only.
- `tests/temporal_harness.Worker` forwards `**kwargs` (for example `max_cached_workflows`, `workflow_runner`) to the
  control worker. `tests/conftest.py` evicts cached runs when a worker stops (#912), so a stop-and-restart reprocesses
  the next workflow task from full history.
- SDK: `temporalio==1.34.0` (`pyproject.toml`).

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: image `ghcr.io/mctlhq/mctl-agents`, tag
  `"1.117.0"`. This is consistent with the issue's premise that no deployed worker runs the wired decision. Sibling
  directories `mctl-agents-worker-exec` and `mctl-agents-worker-implement` exist. Their tags were not read, because this
  slice deploys nothing.
- mctl-gitops `agents-state/mctl-agents/proposals/issue-1055-devloop-part-m-m2b-1d-2b-wire-the-merge/{design,tasks}.md`:
  read for section 6, task 9 and tests D7-D18.
- No mctl MCP tool was called. This slice has no runtime surface, and the worker tag above answers the only deployed
  question that matters (whether any production history can contain the wired decision).

## Proposed solution

All changes are under `tests/` and `tools/`. Nothing under `orchestrator/` changes.

### 1. Recorder in `tests/test_merge_watch_final_read.py`

`async def record_final_read(env, *, hop: bool, monkeypatch) -> tuple[WorkflowHandle, str]`:

- Sets `dev_loop.MERGE_WATCH_DEADLINE = timedelta(minutes=40)`. When `hop` is true it also sets
  `dev_loop.MERGE_WATCH_HISTORY_FLOOR = 1`.
- Builds `_fake_activities(released=True)` with a `get_pr_state` that answers `OPEN_PR` before
  `start + 40 min - 5 min` and `MERGED_PR` at or after it. That gives one in-loop OPEN read per 15-min poll, then the
  final read. The fake is clock-based, like `_ride_to_deadline`, not call-count based, so the hop variant gets the same
  answers.
- Runs `Worker(..., workflow_runner=UnsandboxedWorkflowRunner())`, starts with a fixed workflow id
  (`merge-watch-final-read` or `merge-watch-final-read-hop`) so replays with arguments are reproducible, signals approve,
  and awaits the result.
- For `hop=True`, it fetches the latest run (`env.client.get_workflow_handle(wid)` without a run id) and returns it. It
  also exposes the first run's id for D15a. It returns `(handle, workflow_id)`.
- Module constants `FINAL_READ_FIXTURE_DIR = Path(...)/"fixtures"/"histories"/"merge_watch"` and
  `RECORDING_PATCHES = {"MERGE_WATCH_DEADLINE": timedelta(minutes=40), "MERGE_WATCH_HISTORY_FLOOR": 1}` are shared by
  recorder, replay and tool, so the replay setup cannot drift from the recording.

The module docstring is updated: 1d-2b-ii is now here.

### 2. Tool `tools/record_merge_watch_final_read.py`

A thin pytest file in the style of `tools/record_pre_m1_histories.py`. Unlike that tool, it runs in this tree (the
fixtures must come from the current code), so no worktree step is needed:

```
MERGE_WATCH_OUT=tests/fixtures/histories/merge_watch \
  python -m pytest -q tools/record_merge_watch_final_read.py
```

- A module-level `pytestmark = pytest.mark.skipif(not os.environ.get("MERGE_WATCH_OUT"), ...)`, so it never records in
  CI. The `tools/` directory is not in the default test paths. The tool should still verify this, and add the skip
  regardless.
- `test_manifest` writes `{"recorded_from": git HEAD, "temporalio": version, "files": {}}`.
- `test_fresh` and `test_hop` call `record_final_read`, then `_write(name, history.to_json_dict(), workflow_id)`.
  `_scrub`, `_canonical_sha256` and `_write` are the same small functions as in `record_pre_m1_histories.py`. They are
  copied rather than imported, because `tools/` is not a package and that file is pinned to a99c888 semantics.
- The docstring states: recorded from the post-1d-2b-i tree; never re-record without a review that explains why the
  command stream changed.

### 3. Committed fixtures

`tests/fixtures/histories/merge_watch/{dev_loop_final_read.json, dev_loop_final_read_hop.json, MANIFEST.json}`. They are
expected to be small. The 40-minute deadline gives about 3 polls, and the hop run is a single continued run.

### 4. Replay tests (D15, D15a, D15b)

These go in `tests/test_merge_watch_final_read.py`:

- `test_merge_watch_fixtures_replay_clean` (D15b), parametrized over both fixtures. It applies `RECORDING_PATCHES` with
  `monkeypatch` and runs `Replayer(workflows=[DevLoopWorkflow], workflow_runner=UnsandboxedWorkflowRunner())
  .replay_workflow(WorkflowHistory.from_json(manifest_wid, text))`.
- `test_merge_watch_fixtures_are_not_vacuous`: marker count 1 (fresh) and 0 (hop); at least one `get_pr_state` scheduled
  after the last `TIMER_FIRED`; the `terminal` ownership activity scheduled after it; `resolve_deploy_target` scheduled
  once; the run `WORKFLOW_EXECUTION_COMPLETED`.
- `test_merge_watch_manifest_matches`: the sha256 of every file matches, and the directory listing equals the manifest
  keys plus `MANIFEST.json`.
- `test_final_read_marker_once_fresh_zero_continued` (D15). It counts markers on the two in-test recordings from the
  recorder (fresh run, last hop run), using the `_markers_named` logic from `test_patch_memoization.py`, which is
  imported.
- `test_unpatched_record_across_the_deadline_makes_no_final_read_and_replays` (D15). It uses `_resume_run` with a record
  built with `terminal_reconcile=False`. That needs a `terminal_reconcile` keyword on `_resume_run`, default True. It
  asserts zero post-deadline reads and `watch_end == ""`, then replays the fetched history.
- `test_in_test_recordings_replay_clean` (D15a). Recorder, then fetch every run of the chain via
  `fetch_history(run_id=...)` for the hop variant, then Replayer, then nothing written.
- The four named suites stay green unedited. They are verified by running them, not by editing them.

### 5. Duplicate delivery (D16)

`test_duplicate_delivery_of_the_final_read_task` is parametrized over two modes:

- `nocache`: the recorder's run with `max_cached_workflows=0` on the control worker, so every workflow task, including
  the one carrying the final-read result, is processed by a full replay.
- `restart`: the fake `get_pr_state` sets an event on the post-deadline read. The test then exits the worker context
  (conftest evicts the cached run), starts a fresh `Worker` with the same activities, and awaits the result. The task
  carrying the read result is delivered to a worker with no cached state.

Assertions in both modes: exactly one `terminal` in the fake's `ops`, `resolve_deploy_target` scheduled once in history,
the run Completed with `pr.state == "MERGED"`, and the Replayer over the fetched history raises nothing. A replay that
issued an extra command would raise a nondeterminism error, because Replayer compares the command stream.

### 6. Carry-over coverage

- D7, two tests. (a) `test_final_read_ordering_from_history`: parametrized over D3-D6 outcomes via `_ride_to_deadline`.
  It finds the first post-deadline `get_pr_state` and the `terminal`/`release` ownership activity, and asserts the
  order. For D6 it asserts no relinquishing write after the read. With nothing in flight the settle issues no command,
  so (a) cannot see the settle and does not claim to. (b) `test_settle_commands_precede_the_first_read`: the in-flight
  gate scenario (`_released_gate_run` with `_StubbornWait`, as D14). The cancel of the gate and the wait for it appear
  in history before the first post-deadline `get_pr_state`, which appears before any relinquishing write. Only (b) can
  turn the swap-settle-and-read mutation (f4) red.
- D9 window variant: `_released_gate_run` with an `on_read`/timer hook that signals abandon after the first read opened
  the window. It asserts one read, `abandoned-unverified`, and `release`.
- D12 bookkeeping: two tests. (a) A final-read OPEN, via queries or the resume record of a following hop, gives
  `_last_pr` equal to the fresh head, `saw_open_pr`, reset counters, and a held claim. (b) A resume record with no
  `owned_entity_id`, and a MERGED final read, gives ops `acquire` then `terminal`.
- D14: `_resume_run(gate=True, wait_cls=_StubbornWait, on_poll=...)`, with abandon signalled while the settle waits. It
  asserts no `get_pr_state` after the settle, `abandoned-unverified`, and `release`.

## Alternatives

1. **Register the fixtures as `SCENARIOS` in `tests/replay_scenarios.py` (top-level `histories/`).** Dropped. Those
   scenarios replay sandboxed with default constants and a prepatch/patched pair. The final-read fixtures need the
   40-minute and floor monkeypatches under the unsandboxed runner, and have no prepatch twin. A subdirectory with its
   own manifest, like `pre_m1/`, keeps them out of the orphan check and makes the special replay setup explicit.
2. **Record with the real 14-day deadline under the sandbox (as `_ride_to_deadline` does).** Dropped. About 1344 polls
   make a multi-megabyte fixture and slow replay. The spec fixes 40 minutes.
3. **Simulate duplicate delivery by completing the activity twice (`AsyncActivityHandle.complete`).** Dropped. The
   server rejects the second completion of a closed activity, so the test would only pin server behaviour. The workflow
   risk is reprocessing the task on a worker without cache, which the two chosen modes exercise directly.

## Platform impact

- No migration, no production code, no marker. `PATCHED_CALLS` stays 38. No deployable artifact changes, and workers stay on
  1.117.0 with the release hold ON.
- Backward compatibility: the new fixtures add replay constraints going forward. A future change to the decision's
  command stream must either keep them replaying or ship behind a new marker, which is the intended guard. Re-recording
  is a reviewed, deliberate act through the tool.
- CI cost: about 10 new time-skipping tests with short deadlines, plus two small replays. The `restart` and `nocache`
  modes add seconds, not minutes.
- Risks: (a) Replay depends on module-global monkeypatches. Mitigation: one shared `RECORDING_PATCHES` constant, and
  the replay test fails loudly (nondeterminism) if they are missing. (b) Flaky timing in `restart` mode. Mitigation:
  stop on an `anyio.Event` set inside the fake activity, with `fail_after` bounds, as other tests in the module do.
  (c) Accidental re-record in CI. Mitigation: the env-var skip.
