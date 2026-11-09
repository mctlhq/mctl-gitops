# Design: issue-1026-devloop-part-m-m2b-1a-worker-restart-gap

## Current state

**The merge watch** (`orchestrator/temporal/workflows/dev_loop.py`):

- `MERGE_WATCH_DEADLINE = timedelta(days=14)` (line 542), `MERGE_POLL_INTERVAL = timedelta(minutes=15)` (line 540), `LEGACY_MERGE_POLL_INTERVAL = 30 min` (line 541), `PR_STATE_TIMEOUT = 2 min` (line 606), `MERGE_WATCH_HISTORY_FLOOR = 4096` (line 553).
- `DevLoopWorkflow._watch_pr` (line 6348) computes the absolute deadline once: `deadline = workflow.now() + MERGE_WATCH_DEADLINE` (line 6394). A continue-as-new hop carries the same deadline (`_as_utc(resume.deadline)`).
- The loop is `while workflow.now() < deadline and not self._abandoned:` (around line 6520). Each iteration calls `workflow.execute_activity(get_pr_state, ...)` and returns on `MERGED`/`CLOSED`. It ends with `await workflow.sleep(cadence.poll_interval)`, a fixed interval that is not clamped to the remaining time.
- The consequence, which is the defect premise of #1021: when the post-sleep workflow task first runs after `deadline` (because no worker was polling when the timer fired), `workflow.now()`, the task's start time, is already past the deadline. The `while` condition is false, the loop exits without a final `get_pr_state`, and the last observed state (`OPEN`) is returned. The code supports the premise. The test exists to demonstrate it end to end.

**The harness** (`tests/temporal_harness.py`):

- `Worker` wraps `temporalio.worker.Worker` for the control queue and adds execution-queue and implementation-queue workers when routed activities are registered. It forwards `**kwargs` to all of them, so `identity=` reaches every worker. `__aexit__` stops them in reverse order.
- The #912 teardown eviction (`evict_left_over_runs`, `evicting_after_shutdown`) is installed suite-wide by `tests/conftest.py::_evict_cached_runs_when_a_worker_stops`. `_unevicted_runs_fail_the_test` fails any test whose stopped worker left an unevictable run. Stopping worker 1 mid-watch is exactly the case this machinery evicts, so worker 2 replays from history and gets no cached instance.

**The existing baseline test** (`tests/test_dev_loop_workflow.py`):

- `TestDevLoopWorkflow.test_merge_detection_deadline_returns_last_open_state` (line 4058) runs one worker through the whole 14 days and asserts `result.pr.state == "OPEN"`.
- The `env` fixture (line 227) is `WorkflowEnvironment.start_time_skipping()`, and `TASK_QUEUE = "test-mctl-dev-loop"` (line 223).
- `_fake_activities(released=True, pr_states=[...])` (line 332) returns `(activities, calls, investigate_ran, ownership_ops)`. Its `get_pr_state` fake (line 567 onwards) consumes a fixed sequence, so it cannot be switched mid-test. The new test must replace that one activity in the list by name with a mutable fake.
- Other test modules already import from `tests.test_dev_loop_workflow` (for example `tests/test_deferred_resume_m2a.py` and `tests/test_patch_memoization.py`), so reusing `_fake_activities`, `MERGED_PR`, `TASK_QUEUE`, `IssueRef` and `DevLoopWorkflow` from there follows existing convention.
- `env.sleep(timedelta(days=...))` is already used in that module (for example lines 1877 and 1964).

Deployed state checked:

- No mctl MCP tool and no `$MCTL_GITOPS_ROOT` path was consulted. This proposal makes no claim about any deployed service, tenant, hostname or configuration. The change is a test file run in CI and the implementer's sandbox only, so there is no deployed state to check.

## Proposed solution

Add a single test module, `tests/test_merge_watch_gap_harness.py`. Production code is unchanged.

**Building blocks**, all in the test module:

1. `_SwitchablePRState`: a small fake that holds the current `PRState` (start `OPEN`, built like `open_pr` in the baseline test from `MERGED_PR` fields), a call log of `(worker_tag, returned_state)`, and an `asyncio.Event` set on the first read. Its `@activity.defn(name="get_pr_state")` replaces the entry with the same activity name in the list `_fake_activities(released=True)` returns. The replacement is by name, so no other fake changes.
2. Two `Worker(env.client, task_queue=queue, workflows=[DevLoopWorkflow], activities=activities, identity=...)` contexts, `gap-worker-1` and `gap-worker-2`. Each test uses a unique queue (`f"merge-watch-gap-{uuid4()}"`) so no ghost poller from another test can take its tasks.
3. A history reader: `await handle.fetch_history()`, then the events with their `event_time` and `event_type`, `WorkflowTaskStarted` identities, and `ActivityTaskScheduled` events whose `activity_type.name == "get_pr_state"`.

**Scenario A (deadline inside the gap):**

1. Inside worker 1: start `DevLoopWorkflow.run`, wait for `investigate_ran`, signal `approve` (`{"approval_ref": "aar_test"}`), then wait (with `anyio.fail_after`) until the fake has recorded at least one read, and then, polling `handle.fetch_history()`, until a `TimerStarted` follows the `ActivityTaskCompleted` of the first `get_pr_state`. The fake's event fires inside the activity, while the result is still on its way back, so worker 1 still has a workflow task to run at that point. Any activity the iteration runs after the read, such as `_track_ownership`, also finishes before the timer at the bottom of the loop starts, and a `TimerStarted` is only recorded when its workflow task completes. Do not call `handle.result()` while worker 1 is up: under the time-skipping server that would unlock skipping and run the watch to the end. Record `run_id` from `handle.describe()`.
2. Leave the worker 1 context. The harness stops all three SDK workers and the #912 eviction drops the cached run. Only now record `gap_start = await env.get_current_time()` and the read count, so a workflow task worker 1 finished before it stopped cannot fall inside the gap. With `stop_worker=False` the driver records them at the same point without leaving the context.
3. Set the fake to the `MERGED` state (`MERGED_PR`). Call `await env.sleep(MERGE_WATCH_DEADLINE + timedelta(hours=1))`. Record `gap_end`.
4. Inside worker 2 (same queue): `result = await handle.result()` under `anyio.fail_after`.

**Assertions on A:**

- Interruption: no `WorkflowTaskStarted` event has `gap_start < event_time < gap_end`. `TimerFired`, `WorkflowTaskScheduled` and a sticky `WorkflowTaskTimedOut` are permitted. The identities of the last task started before the gap and the first after it are `gap-worker-1` and `gap-worker-2`. The fake's call count at `gap_end` equals the count at `gap_start`.
- Same execution: `handle.describe().run_id` after the run equals the recorded one, and there is no `WorkflowExecutionContinuedAsNew` event.
- Absolute deadline: watch start is the `event_time` of the `WorkflowTaskStarted` that precedes the first `get_pr_state` `ActivityTaskScheduled`. That task's `workflow.now()` is the base of the deadline. Assert `watch_start + MERGE_WATCH_DEADLINE < first_post_gap_task_started.event_time`. Assert also that no `TimerStarted` after the gap has `start_to_fire_timeout >= MERGE_WATCH_DEADLINE`, and that the workflow completes, so no new 14-day wait is armed.
- Baseline miss (the pin): no `get_pr_state` `ActivityTaskScheduled` after the gap, and the fake log has no `MERGED` read. `result.pr.state == "OPEN"` and `result.pr.merged is False`. A docstring states that this pins the defect and that a later #1021 slice inverts it.

**Scenario B (control):** identical, except `env.sleep(MERGE_POLL_INTERVAL + timedelta(minutes=1))`, longer than one poll interval so the parked timer has fired, and far shorter than the deadline. Assert that a `get_pr_state` was scheduled after the gap, that the fake recorded a `MERGED` read, and that `result.pr.state == "MERGED"`. This shows that the switched state is observable after a restart, so A's miss comes from the deadline and not from the harness. To make the mutation table straightforward, A and B share one parametrised driver `_run_gap(env, *, gap, switch_to_merged=True, stop_worker=True, do_sleep=True)`.

**Mutation proof** (local only, each reverted):

1. Keep worker 1 running through the gap (`stop_worker=False`): the interruption assertions fail, because tasks start during the gap and the read count moves.
2. Use a gap shorter than the deadline in scenario A: the deadline assertion and the pin fail.
3. Skip `env.sleep`: the deadline assertion fails.
4. Do not switch the fake to `MERGED` in scenario B: B's merged assertion fails.
5. Add a temporary final `get_pr_state` read at `_watch_pr`'s deadline exit in `dev_loop.py`: the scenario A pin fails. This patch is reverted and must not be in the diff.

**Reproducibility:** run `uv run --locked pytest tests/test_merge_watch_gap_harness.py -q` 20 consecutive times, in batches that respect the 300 s per-command bound (for example `for i in $(seq 1 5); do uv run --locked pytest tests/test_merge_watch_gap_harness.py -q || break; done`, four batches), and report every batch. Also run `uv run --locked pytest tests/test_dev_loop_workflow.py -q -k merge_detection` and `uv run --locked pytest tests/test_worker_teardown_eviction.py -q`.

**STOP handling:** any of the issue's STOP conditions ends the run with a report on #1026 and no success-shaped PR. The conditions are: fewer than 20 of 20 passes, worker 2 never receiving the task, a post-restart read on the baseline, needing direct calls or mocks, or a production change appearing necessary.

## Alternatives

- **A direct unit test of `_watch_pr` on a bare instance (`_bare_loop()`) with a patched `workflow.now`.** Rejected: the issue forbids bypassing Temporal workflow execution, and it would prove nothing about whether a real stop and restart is expressible.
- **Reuse one worker and simulate the gap with an activity that blocks past the deadline.** Rejected: the worker keeps polling, so this is not a worker-restart gap, and `PR_STATE_TIMEOUT` and the retry policy would shape the outcome instead of the deadline.
- **Extend `tests/temporal_harness.Worker` with a stop/start API.** Rejected for now: two sequential `async with Worker(...)` blocks express the stop and start with the existing API. The issue allows a harness helper only if the test file cannot hold it.

## Platform impact

- No migrations, no production code, no patch markers, no replay impact, and no deployed resource change. `git diff origin/main -- orchestrator agents config` stays empty.
- CI cost: two time-skipped workflow runs, a few seconds each, judging by comparable merge-detection tests. This is well under the 300 s per-command bound.
- Risk: the sticky queue or the time-skipping server behaves differently than assumed, and worker 2 never runs the task. Mitigation: a bounded `anyio.fail_after` on the result, and the STOP condition. No workaround such as resetting stickiness through the API is allowed.
- Risk: the #912 eviction fails on the mid-watch stop. Mitigation: `_unevicted_runs_fail_the_test` surfaces it, and it is reported rather than suppressed.
- Risk: if worker 1 were stopped or `gap_start` recorded right after the first read, the workflow task that processes the read's result would race with both, and the interruption assertion could fail for a reason unrelated to the harness, which would be a false STOP. Mitigation: the `TimerStarted` wait in step 1 and recording `gap_start` after the exit in step 2. A timeout on that wait is itself a STOP condition.
- Risk: the first workflow task's `WorkflowTaskStarted` time is misidentified as the watch start. Mitigation: anchor on the task that scheduled the first `get_pr_state`. If timestamps differ by a sub-second amount, the assertion keeps a full-hour margin (the sleep overshoots the deadline by one hour).
- Merge: the PR must be verified as blocked by GitHub (the code-owner hold from #1020) before anything else happens to it. No autonomous merge.
