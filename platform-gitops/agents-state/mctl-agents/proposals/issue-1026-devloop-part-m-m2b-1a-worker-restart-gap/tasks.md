# Tasks: issue-1026-devloop-part-m-m2b-1a-worker-restart-gap

- [ ] 1. Create `tests/test_merge_watch_gap_harness.py` with `pytestmark = pytest.mark.anyio`, a local `env` fixture (`WorkflowEnvironment.start_time_skipping()`), and imports of `_fake_activities`, `MERGED_PR`, `IssueRef` and `DevLoopWorkflow` from `tests.test_dev_loop_workflow`, plus `MERGE_WATCH_DEADLINE` and `MERGE_POLL_INTERVAL` from `orchestrator.temporal.workflows.dev_loop`. DoD: the module collects; `git diff origin/main -- orchestrator agents config` is empty.
- [ ] 2. (depends on 1) Add the `_SwitchablePRState` fake: a current state, a call log and a first-read event. Its `get_pr_state` replaces the entry with the same activity name in the list from `_fake_activities(released=True)`. DoD: the replacement is by activity name and every other fake is unchanged.
- [ ] 3. (depends on 2) Add the history helpers: fetch the events, find watch start (the `WorkflowTaskStarted` before the first `get_pr_state` `ActivityTaskScheduled`), and return the `WorkflowTaskStarted` events with identities and the timers started after a timestamp. DoD: the helpers use only `handle.fetch_history()` and `handle.describe()`.
- [ ] 4. (depends on 3) Add the driver `_run_gap(env, *, gap, switch_to_merged=True, stop_worker=True, do_sleep=True)`. It uses a unique task queue, worker 1 (`identity="gap-worker-1"`) through approve and the first read, never calls `handle.result()` before the gap, records `gap_start` and `gap_end` with `env.get_current_time()`, and runs worker 2 (`identity="gap-worker-2"`) with `handle.result()` under `anyio.fail_after`. DoD: it returns the result, the run ids, the history, the gap bounds and the fake log.
- [ ] 5. (depends on 4) Scenario A, `test_deadline_inside_worker_gap_misses_merged_on_baseline`: `gap = MERGE_WATCH_DEADLINE + 1h`, with the interruption, same-execution, absolute-deadline and pin assertions from design.md. The docstring says the test pins the current defect and a later #1021 slice inverts it. DoD: it passes on the baseline.
- [ ] 6. (depends on 4) Scenario B, `test_short_worker_gap_observes_merged`: `gap = MERGE_POLL_INTERVAL + 1min`. Assert a post-gap `get_pr_state`, a `MERGED` read and `result.pr.state == "MERGED"`. DoD: it passes on the baseline.
- [ ] 7. (depends on 5, 6) Run the evidence: one run, then 20 consecutive repeats in batches under the 300 s bound with every batch reported, the existing merge-detection tests and `tests/test_worker_teardown_eviction.py`. DoD: 20 of 20 passes, or a STOP report on #1026.
- [ ] 8. (depends on 7) Run the five mutations from design.md locally. Record the failing test and message for each, and revert each one. DoD: the five rows are recorded, and `git diff origin/main` contains only `tests/test_merge_watch_gap_harness.py` (and `tests/temporal_harness.py` only if it was unavoidable).
- [ ] 9. (depends on 8) Open one PR, a single commit, with the commands, batch outputs and mutation table. Verify that GitHub reports it as blocked (the code-owner hold from #1020) and stop if it is not. No merge, release or flag change. DoD: the PR exists and is blocked, or a negative report is on #1026 with no PR.

## Tests

- [ ] T1. `uv run --locked pytest tests/test_merge_watch_gap_harness.py -q`: both scenarios pass.
- [ ] T2. 20 consecutive repeats of T1 with 20 passes, in batches, every batch reported.
- [ ] T3. `uv run --locked pytest tests/test_dev_loop_workflow.py -q -k merge_detection`: green.
- [ ] T4. `uv run --locked pytest tests/test_worker_teardown_eviction.py -q`: green.
- [ ] T5. Mutations 1 to 5 each fail the intended assertion and are reverted.

## Rollback

Test-only change: revert the single commit, or delete `tests/test_merge_watch_gap_harness.py`. No production, gitops, deployment or replay state is affected. If a STOP condition is hit, no PR is opened, and the negative finding on #1026 is the outcome.
