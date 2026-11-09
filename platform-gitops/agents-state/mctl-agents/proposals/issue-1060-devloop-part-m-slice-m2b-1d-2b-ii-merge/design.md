# Design: issue-1060-devloop-part-m-slice-m2b-1d-2b-ii-merge

## Current state

Baseline: `main` at `0ef0e04` (merge of PR #1058, slice 1d-2b-i).

### The decision under test

`orchestrator/temporal/workflows/dev_loop.py` (7287 lines):

- `MERGE_WATCH_RECONCILE_PATCH = "merge-watch-terminal-reconcile"` (line 505), `MERGE_WATCH_DEADLINE =
  timedelta(days=14)` (568), `MERGE_WATCH_HISTORY_FLOOR = 4096` (579), `FINAL_READ_ATTEMPTS = 3`,
  `FINAL_READ_BACKOFF = 2 min` (636-637).
- `_watch_pr` (6677) computes `deadline = workflow.now() + MERGE_WATCH_DEADLINE` only in the fresh arm and takes
  `_as_utc(resume.deadline)` and `resume.terminal_reconcile` from a `MergeWatchResume` on a continued run (6721-6748).
  The hop predicate reads `info.get_current_history_length() >= MERGE_WATCH_HISTORY_FLOOR` (6536).
- `_decide_watch_end` (6638) settles in-flight work (`_settle_watch_work`, 6593), reads the PR with
  `_final_pr_read` (6612, up to `FINAL_READ_ATTEMPTS` `get_pr_state` activities), and on MERGED/CLOSED calls
  `_terminal_claim` before returning `final`; an OPEN read returns `open` (relinquished by `release` in `finally`).
  The watch end is `WATCH_END_FINAL_READ` (7165). A MERGED end is followed by `_observe_deploy` (4815, 5080), which
  schedules `resolve_deploy_target`.
- Ownership writes go through the `lifecycle_ownership` activity (fake at `tests/test_dev_loop_workflow.py:606`,
  which records each op in the `ops` list `_fake_activities` returns).
- No `@workflow.defn(failure_exception_types=...)` is set on `DevLoopWorkflow` (1888), so a non-`FailureError`
  exception raised in workflow code fails the workflow TASK (retried by the server), not the workflow.

### Tests that exist after 1d-2b-i

- `tests/test_merge_watch_final_read.py` (660 lines): D3-D6 (`_ride_to_deadline`, sandboxed, real 14-day deadline
  fast-forwarded), D6b, D8, D9 (three of four cases), D10, D11, D13, D18. Its docstring says "The committed-fixture
  half of the slice (recorder, D15b, D16) is 1d-2b-ii and is not here." Not written: D7, D9 window case, D12,
  D13b-e, D14, D15a.
- `tests/test_patch_memoization.py::test_the_terminal_reconcile_marker_is_recorded_once_fresh_and_never_on_a_merge_watch_hop`
  (303) already pins "marker once fresh, zero on a continued run", using `_markers_named` (289).
- `tests/test_merge_watch_worker_gap.py::test_unpatched_record_keeps_the_legacy_deadline_end` (329) pins "unpatched
  record makes no final read", but does not replay its history.
- `tests/test_merge_watch_decision.py:557` `PATCHED_CALLS = 38`.
- `tests/test_dev_loop_workflow.py::test_deadline_is_carried_not_recomputed_across_hops` (7884) is the precedent for
  monkeypatching `MERGE_WATCH_DEADLINE` to 40 min and `MERGE_WATCH_HISTORY_FLOOR` to 1 under
  `UnsandboxedWorkflowRunner`.

### Fixture conventions

- `tools/record_pre_m1_histories.py` is a pytest file, not collected by CI (`pyproject.toml` `testpaths =
  ["tests"]`), output directory from an env var, `_scrub` blanks `stackTrace` / `identity`, `_write` registers each
  file in `MANIFEST.json` with a canonical sha256 and workflow id, and `test_manifest` writes `recorded_from` and the
  `temporalio` version first.
- `tests/test_pre_m1_compat.py` checks manifest-vs-disk, per-file hash, no identity/stack trace, and replays hop runs
  with `MERGE_WATCH_HISTORY_FLOOR` monkeypatched to 1 and `UnsandboxedWorkflowRunner` (375-384). This is the precedent
  for replaying a history recorded under patched module constants.
- Every glob over `tests/fixtures/histories` is non-recursive: `tests/test_workflow_replay.py:607`
  (`test_every_recorded_fixture_belongs_to_a_scenario`), `tests/test_execution_request_replay.py` (376, 433, 476, 534,
  686, 731). The marker and nondeterminism scans (`tests/test_temporal_marker_scan.py`,
  `tests/test_temporal_nondeterminism_scan.py`) name explicit files. A `merge_watch/` subdirectory is therefore
  invisible to all of them, exactly like `pre_m1/`.
- `temporalio==1.34.0` (`pyproject.toml:62`).

### Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: `tag: "1.117.0"`.
- `.../admins/mctl-agents-worker-exec/values.yaml`: `tag: "1.117.0"`.
- `.../admins/mctl-agents-worker-implement/values.yaml`: `tag: "1.117.0"`.
- So no deployed worker runs the 1d-2b-i wiring; no production history holds decision commands. This slice changes
  no deployed artefact. mctl MCP tools were not needed beyond this and were not called.
- mctl-gitops `.../proposals/issue-1055-devloop-part-m-m2b-1d-2b-wire-the-merge/` (design.md section 6, tasks.md
  task 9, D15a, D15b, D16): status `merged`, `merge_commit: 0ef0e04f5...`.

## Proposed solution

Test and fixture files only. No file under `orchestrator/` changes.

### 1. Recorder in `tests/test_merge_watch_final_read.py`

Add a new section (and update the module docstring to drop "is not here"):

```python
FINAL_READ_DEADLINE = timedelta(minutes=40)
MERGE_WATCH_DIR = Path(__file__).resolve().parent / "fixtures" / "histories" / "merge_watch"

async def record_final_read(env: WorkflowEnvironment, *, hop: bool) -> tuple[dict[str, Any], str]:
    """Returns (history JSON dict of the run that executed the decision, workflow id)."""
```

- The caller (test or tool) sets the constants with `monkeypatch`; a helper `_final_read_constants(monkeypatch, *,
  hop)` sets `dev_loop.MERGE_WATCH_DEADLINE = 40 min` and, when `hop`, `dev_loop.MERGE_WATCH_HISTORY_FLOOR = 1`. Both
  the recorder and the replay tests call the same helper so recording and replay cannot drift.
- Worker: `Worker(..., workflows=[DevLoopWorkflow], workflow_runner=UnsandboxedWorkflowRunner())` with
  `_fake_activities(released=True)` and a `get_pr_state` replacement: OPEN (`OPEN_PR`) while `now < start +
  FINAL_READ_DEADLINE - 5 min` (same cutoff technique as `_ride_to_deadline`), then MERGED (`hop=False`) or an OPEN
  state with `head_sha="fresh999"` (`hop=True`).
- Fresh: start `DevLoopWorkflow.run(IssueRef(...))`, wait for investigate, signal `approve`, await the result.
  Assert `watch_end == "final-read"`, exactly one post-deadline read, `ops.count("terminal") == 1`, no `release`.
  Return `handle.fetch_history().to_json_dict()`.
- Hop: same start; follow `first_execution_run_id` and `workflowExecutionContinuedAsNewEventAttributes.newExecutionRunId`
  as `tools/record_pre_m1_histories.py::test_dev_loop_hop_chain` does. Assert at least two runs, the last run's
  result has `watch_end == "final-read"` and one `release` with `version == "fresh999"`. Return the LAST run's history.
- If the merge gate is still in flight at the deadline in either recording (it would add the window), the recorder's
  "exactly one post-deadline read" assertion fails loudly; the fix is to settle the gate in the fake
  (`gate_results` / `merge_gate_settled_head`), not to accept a different shape.

Shared helpers moved beside the recorder (or imported from the tool, see 2): `_scrub`, `_canonical_sha256`, and a
reader `_patch_ids(events)` matching `core_patch` markers by payload id (same logic as
`tests/test_workflow_replay.py::_patch_ids`).

### 2. Tool `tools/record_merge_watch_final_read.py`

A pytest file in the style of `tools/record_pre_m1_histories.py` (`# ruff: noqa: S101, S607` header, docstring with
the exact command, `pytestmark = pytest.mark.anyio`):

- `OUT` from `MERGE_WATCH_OUT`; `test_manifest` writes `{"recorded_from": <git sha>, "temporalio": <version>,
  "files": {}}`.
- `test_fresh(env, monkeypatch)` and `test_hop(env, monkeypatch)` call `_final_read_constants` then
  `record_final_read(env, hop=...)` and `_write(name, history, workflow_id, constants)`, where the manifest entry adds
  `{"constants": {"MERGE_WATCH_DEADLINE": "PT40M", "MERGE_WATCH_HISTORY_FLOOR": 1 | null}}`.
- The tool imports from `tests.test_merge_watch_final_read`; it holds no recording logic of its own. Command, from the
  repo root: `MERGE_WATCH_OUT=tests/fixtures/histories/merge_watch uv run --locked pytest -q -p tests.conftest
  tools/record_merge_watch_final_read.py`. (`-p tests.conftest` loads the autouse stubs that `tests/` relies on. If that
  does not load cleanly, the documented fallback is the pre-M1 one: copy the file to `tests/test_zz_record_merge_watch.py`,
  run it, delete it.) The implementer records which command was used in the docstring and the PR.
- Unlike the pre-M1 recorder, this one records from the CURRENT tree. The docstring says so, and says to re-record
  only when the decision's command shape is MEANT to change.

### 3. Fixtures

`tests/fixtures/histories/merge_watch/dev_loop_final_read.json`, `.../dev_loop_final_read_hop.json`,
`.../MANIFEST.json`. JSON written with `indent=2, sort_keys=True` and a trailing newline, as pre-M1.

### 4. Tests (all in `tests/test_merge_watch_final_read.py`)

- D15b content and integrity: manifest lists exactly the files on disk; every hash matches; no identity or stack
  trace; fresh fixture has `merge-watch-terminal-reconcile` once; hop fixture has it zero times and a start input
  (`workflowExecutionStartedEventAttributes.input`) whose `resume.terminal_reconcile` is true.
- D15b replay: parametrized over the manifest, sets the manifest's constants with `monkeypatch`, then
  `Replayer(workflows=[DevLoopWorkflow], workflow_runner=UnsandboxedWorkflowRunner()).replay_workflow(
  WorkflowHistory.from_json(workflow_id, text))`.
- D15a: record each variant in-test with `record_final_read`, replay it at once in the same test (nothing written).
  Plus the unpatched variant: run `tests/test_merge_watch_worker_gap.py`'s scenario A record with
  `terminal_reconcile=False` (reuse `_resume_record` and its harness), assert no post-deadline `get_pr_state`
  schedule, and replay its history clean.
- D7: on the committed fixtures (pure JSON reads), the event order described in requirements.md. The ops for
  `lifecycle_ownership` are identified from the scheduled activity's input payload (`op` field), decoded with the
  default payload converter.
- D16: a test-only subclass, in the style of `_UnrecordedLoop`:

  ```python
  _DUP: dict[str, bool] = {}

  @workflow.defn(name="DevLoopWorkflow", sandboxed=False)
  class _CrashAfterFinalRead(DevLoopWorkflow):
      @workflow.run
      async def run(self, issue: IssueRef) -> Any:
          return await super().run(issue)

      async def _final_pr_read(self, watch, service, slug):
          read = await super()._final_pr_read(watch, service, slug)
          if read.fresh is not None and read.fresh.state == "MERGED" and not _DUP.get("raised"):
              _DUP["raised"] = True
              raise RuntimeError("simulated worker crash after the final read")
          return read
  ```

  Driven by the fresh recording path (40-min deadline, unsandboxed, MERGED at the deadline), with the worker started
  with `max_cached_workflows=0` so the retried task replays from history. Expect: exactly one
  `EVENT_TYPE_WORKFLOW_TASK_FAILED`; exactly one `get_pr_state` schedule after the deadline (the activity result is in
  history, so the retry does not re-read); `ops.count("terminal") == 1`; `_scheduled(run, "resolve_deploy_target")
  == 1`; `watch_end == "final-read"`. Then replay the history through the PLAIN `DevLoopWorkflow` (Replayer,
  unsandboxed, same constants): clean, which proves the redelivered task added no command. The flag lives at module
  level (outside the workflow) so the retry does not raise again; it is reset in the test.

### 5. What stays unchanged

`tests/test_workflow_replay.py`, `tests/test_execution_request_replay.py`, `tests/test_pre_m1_compat.py`,
`tests/test_patch_memoization.py`, `tests/test_merge_watch_decision.py` (`PATCHED_CALLS = 38`) are not edited.

## Alternatives

1. Record under production constants (14-day deadline, sandboxed). Rejected: the sandbox re-imports the module so the
   fresh deadline cannot be shortened, and a 14-day fresh history is about 1344 polls, a multi-megabyte fixture. The
   precedent (`test_pre_m1_compat.py` hop runs) already replays under monkeypatched constants; the manifest records
   them so the replay reproduces them.
2. Record from a `MergeWatchResume` (the `_resume_run` harness) instead of a fresh start. Rejected for the fresh
   fixture: it would not carry the `merge-watch-terminal-reconcile` marker, which is exactly what D15 must show once.
   It is effectively what the hop fixture's last run is, but reached through a real hop so the carried
   `terminal_reconcile` and deadline come from production code, not from a hand-built record.
3. D16 by redelivering the `get_pr_state` activity (heartbeat timeout / retry). Rejected: an activity retry is a second
   read by design and says nothing about the decision's commands; the risk being pinned is a redelivered workflow
   task re-issuing `terminal`. Killing worker 1 mid-task (gap-harness style) was also considered; it is timing
   dependent, whereas a one-shot exception in a test subclass fails exactly the task that holds the read result.

## Platform impact

- Migrations: none. Backward compatibility: no production code changes; no marker added; `PATCHED_CALLS` stays 38.
- Resources: two JSON fixtures (expected tens of KB each at a 40-min deadline and 15-min cadence) and a manifest.
  Test time: four to six additional time-skipping runs, each seconds.
- Risk: a future change to the decision's command shape turns D15b red. That is the intent; the fix is a deliberate
  re-record with the tool, reviewed like the pre-M1 set.
- Risk: replay under monkeypatched constants could mask a dependence on the real 14-day value. Mitigation: the only
  readers of those constants are the fresh-arm deadline and the hop predicate, both already exercised by the
  sandboxed 14-day tests D3-D6.
- Risk: a fixture placed at the top level of `tests/fixtures/histories/` would break
  `test_every_recorded_fixture_belongs_to_a_scenario` and the marker sweeps in `test_execution_request_replay.py`.
  Mitigation: the fixtures live only in `merge_watch/`.
- Release posture: B4 (#1007) stays FAIL, the release hold stays ON, #1022 still blocks any release of this line.
  Nothing is released, tagged or deployed.
