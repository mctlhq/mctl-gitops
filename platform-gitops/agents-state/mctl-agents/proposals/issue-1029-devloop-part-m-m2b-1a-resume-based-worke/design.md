# Design: issue-1029-devloop-part-m-m2b-1a-resume-based-worke

## Current state

All references are to the read-only clone of `mctlhq/mctl-agents`.

- `orchestrator/temporal/workflows/dev_loop.py`
  - `MergeWatchResume` (around line 1598) is a flat dataclass. Its comment
    says `deadline` is "the ABSOLUTE merge-watch deadline the FIRST run
    computed. A continued run parses it with _as_utc and must never
    recompute". The decision flags are carried rather than re-derived:
    `fast_cadence`, `shepherd_in_loop`, `concurrent_ticks`, `track_ownership`,
    `proposal_terminal_end` and `deferred_resume_contract`. The record also
    carries `saw_open_pr`, `poll_index`, the ownership fields,
    `merge_gate_settled_head`, the abandon state and the work-context binding.
  - `DevLoopWorkflow.run` (around line 3561) calls `_run_loop`. When
    `issue.resume is not None`, `_run_loop` returns
    `_resume_merge_watch(issue)` directly (around line 3625).
  - `_resume_merge_watch` (around line 4504) rehydrates the instance state,
    sets `_approved`/`_gates_passed`/`_initialized` to True, calls
    `self._watch_pr(resume.service, resume.slug, resume=resume)`, and then
    either continues as new, if `outcome.resume` is set, or calls
    `_finish_after_watch`.
  - `_watch_pr` (around line 6348):
    - `deadline = _as_utc(resume.deadline)` on resume, otherwise
      `workflow.now() + MERGE_WATCH_DEADLINE` (14 days).
    - The cadence and the flags come from `resume` instead of
      `workflow.patched(...)`.
    - `hop_enabled = workflow.patched("merge-watch-continue-as-new")` and
      `gate_enabled = workflow.patched(MERGE_GATE_PATCH)` are still evaluated.
    - The loop is `while workflow.now() < deadline and not self._abandoned:`.
      Inside it come the hop check, then
      `execute_activity(get_pr_state, ...)`, then the found/terminal handling,
      the ownership tracking (`_track_ownership`), the shepherd tick
      (`poll_index > 1`), the merge-gate start (`_gate_may_start`, around line
      5341, false when `head_sha == self._gate_settled_head`), and finally
      `await workflow.sleep(cadence.poll_interval)`.
    - There is no read after the loop exits on the deadline. That is the
      #1021 path: a poll timer that fires after the deadline ends the watch
      with `last` = the pre-gap state.
  - `MERGE_POLL_INTERVAL = timedelta(minutes=15)` and
    `MERGE_WATCH_DEADLINE = timedelta(days=14)` (around line 540).
    `CADENCE.poll_interval` is `MERGE_POLL_INTERVAL`.
- `orchestrator/temporal/activities/pr_state.py`: `PRState(found, pr_url,
  repo, number, state, merged, merge_commit, merged_at, head_sha, ...)`.
- `tests/temporal_harness.py`: `Worker` wraps `temporalio.worker.Worker` for
  the control, execution and implementation queues and forwards `**kwargs`
  to each SDK worker, so `identity=` and `max_cached_workflows=` pass through.
  It evicts the runs a stopped worker still caches (`evict_left_over_runs`,
  #912).
- `tests/test_execution_request_resume.py` (for example
  `test_a_resume_delivered_after_the_implement_step_is_deferred_not_succeeded`)
  already starts a real loop with `IssueRef(..., resume=MergeWatchResume(...))`
  on the time-skipping environment. `tests/test_dev_loop_workflow.py`
  `_fake_activities(released=True, pr_states=..., ownership_*=...)` provides
  every activity fake the loop needs, including `get_pr_state` and the
  lifecycle-ownership fakes. `tests/test_execution_request_dispatch.py`
  `_loop_activities` shows how individual fakes are replaced by activity
  name.
- `tests/test_b4_update_outage_e2e.py` covers a worker outage on a real dev
  server without time skipping, for the delivery Update rather than the merge
  watch.
- The clone has no test for #1026 or #1021 (a grep for those numbers and for
  "M2b" over `*.py`/`*.md` found nothing relevant).
- `temporalio==1.34.0` (`pyproject.toml`).

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/` lists `mctl-agents-worker`,
  `mctl-agents-worker-exec` and `mctl-agents-worker-implement`. They are the
  deployed workers that run `DevLoopWorkflow`. This proposal adds only a test
  module, so no deployed configuration is read further or changed.
- No mctl MCP tool was called. The change does not touch any deployed
  service, so no runtime fact is asserted.

## Proposed solution

Add one new test module, `tests/test_merge_watch_worker_gap.py`, and nothing
else.

### Harness shape

1. **Environment.** The module uses `WorkflowEnvironment.start_time_skipping()`
   in the same fixture style as the existing resume tests.
2. **Switchable fake.** It registers its own `@activity.defn(name="get_pr_state")`,
   which replaces the factory's sequence fake (the `_loop_activities`
   replace-by-name pattern). It returns `holder.state`, appends every call to
   `holder.calls`, and records `MERGED` returns separately. All other
   activities come from `_fake_activities(released=True, ...)`.
3. **Resume record.** `MergeWatchResume` is built to look like a record
   `_watch_pr` itself would produce at a hop:
   - `service`/`slug` set, and `deadline = (t0 + D).isoformat()` with a `Z`
     suffix. `t0` is read from `env.get_current_time()` before the start, and
     `D` is 10 min (A) or 20 min (B).
   - `last_pr = OPEN_PR` and `saw_open_pr = True`.
   - `poll_index = 0`, so this run's first poll makes it 1 and no shepherd
     tick can start (`poll_index > 1`).
   - `fast_cadence = True`, so the interval is 15 min.
   - `shepherd_in_loop = True`, `concurrent_ticks = True` and
     `track_ownership = True`, with `owned_entity_id`/`owner_epoch` set and
     the factory's healthy ownership fakes. These are the values an ordinary
     production watch on the current patches has. If a flag needs a fake the
     factory cannot supply, that flag is set False and the difference is
     recorded.
   - `proposal_terminal_end = True` and `deferred_resume_contract = True`.
   - `merge_gate_settled_head = OPEN_PR.head_sha`, so `_gate_may_start` is
     false and no child approval workflow (with its own timers) starts.
   - `investigate`/`implement`/`approve` set to Succeeded `WorkflowResult`s.
   - `hops = 0`.
4. **Worker 1.** It runs with `Worker(..., identity="gap-worker-1",
   max_cached_workflows=0)` (see Open questions). The test starts the
   workflow and waits by polling `fetch_history()` with real-time sleeps,
   never `env.sleep`, until the history holds the `get_pr_state`
   `ActivityTaskCompleted`, a `TimerStarted` and a `WorkflowTaskCompleted`
   after that timer. Then it leaves worker 1's `async with`.
5. **Gap.** The test sets `holder.state = MERGED_PR`, records `gap_start =
   env.get_current_time()`, calls `await env.sleep(timedelta(minutes=12))`
   (past the 10-min deadline and before the 15-min timer) and records
   `gap_end`. No workflow task is pending and no timer fires in that window,
   so the time-skipping lock is not engaged. That is exactly the condition
   #1026 lacked.
6. **Worker 2.** It runs with `identity="gap-worker-2"`; the test then calls
   `await handle.result()`. Time skips to the timer. Worker 2 replays the
   history, where the `OPEN` result comes from history and the fake is not
   called, and evaluates `workflow.now() < deadline`:
   - **A:** false, so the watch exits with `last = OPEN`, with no read.
   - **B:** true (deadline +20), so it reads `MERGED` and returns. The tail
     (`_finish_after_watch`, deploy observation) runs on the factory fakes.

### Assertions from history

These come from `fetch_history()` plus the `WorkflowExecutionStarted` input,
decoded with the client's data converter.

- Identities: the set of `workflow_task_started_event_attributes.identity`
  values before `gap_start` is {worker-1's}, the set after `gap_end` is
  {worker-2's}, and the two differ.
- Silence in the gap: no `WorkflowTaskScheduled`/`WorkflowTaskStarted` event
  and no `ActivityTaskScheduled` with `activity_type.name == "get_pr_state"`
  has an `event_time` within [gap_start, gap_end].
- Identity of the run: the handle's `run_id` before the gap equals
  `describe().run_id` after it, `first_execution_run_id` matches, and no
  `EVENT_TYPE_WORKFLOW_EXECUTION_CONTINUED_AS_NEW` event exists.
- Deadline unchanged: the decoded `resume.deadline` equals the string the
  test set. Scenario A also asserts `first_post_gap_task_started.event_time
  >= deadline`.
- Scenario A pin: exactly one `get_pr_state` `ActivityTaskScheduled` in the
  history, `holder.merged_returns == 0`, and `result.pr.state == "OPEN"`.
- Scenario B control: two `get_pr_state` schedules, the second after
  `gap_end`, and `result.pr.state == "MERGED"`.

### Resume-record verification

This is a separate test function. It decodes the started input and asserts
every field the test set, one by one, against the constructed record. It
also checks that, through history, the run took the resume branch:

- no `investigate`/`submit_and_wait` activity was scheduled;
- the first scheduled activity of the merge-watch phase is `get_pr_state`,
  or the ownership acquire/heartbeat when `track_ownership` causes it, which
  is stated as such;
- the poll timer's `start_to_fire_timeout` equals `MERGE_POLL_INTERVAL`,
  which proves `fast_cadence` took effect.

### Mapping against an ordinary production watch

The mapping goes in the module docstring and in the PR body. Statements
executed by this run:

- `_as_utc(resume.deadline)` runs instead of `now + MERGE_WATCH_DEADLINE`.
  This is a difference: production computes the deadline once, 14 days out,
  on its first run.
- The flags come from `resume`, not from `workflow.patched`. This is a
  difference: an ordinary first run evaluates `fast-shepherd-cadence`,
  `shepherd-in-loop` plus `_shepherd_is_pinned()`, `concurrent-shepherd-tick`,
  `lifecycle-ownership` and `PROPOSAL_TERMINAL_PATCH`. In a hopped
  production run the flags come from `resume` exactly as here.
- `hop_enabled` and `gate_enabled` are evaluated the same way as in
  production.
- The loop condition, `get_pr_state`, the found/`OPEN` branch, ownership
  tracking and `workflow.sleep(cadence.poll_interval)` are the same as in
  production.
- The shepherd tick is not reached (`poll_index` 1). This is a difference:
  production reaches it from poll 2 onward.
- The merge gate is suppressed by `merge_gate_settled_head`. This is a
  difference: production would ask a human for an un-settled head.
- The deadline exit with no read is the same code path as production. Only
  the length of the gap differs: 12 virtual minutes, not 14 days.
- The run is a single run without continue-as-new. That is the same as a
  production watch that never hops; production hops only on history size.
- Worker configuration (`max_cached_workflows=0`, if used) is a difference,
  because production workers use the SDK default cache.

There is one honest limit, stated in the docstring. In scenario A the
deadline exit without a read happens whether or not the worker gap occurs,
because the timer fires after the deadline in both cases. The gap is proven
by the interruption assertions, not by the pin. This matches the mutation
list in the issue: keeping worker 1 running through the gap fails the
interruption assertions, not the pin.

### Evidence procedure (PR body)

- One run: `uv run pytest tests/test_merge_watch_worker_gap.py -q`.
- 20 consecutive repeats in batches that each finish under 300 s, for
  example `for i in $(seq 1 5); do uv run pytest ... -q || break; done`
  repeated four times. Every batch's output is reported.
- Four local mutations, each shown failing and then reverted, and absent
  from the diff:
  1. A temporary `get_pr_state` read after the `while` loop in `_watch_pr`
     makes the scenario A pin fail.
  2. Not stopping worker 1, so a single worker spans the gap, makes the
     identity and silence assertions fail.
  3. A scenario A deadline of +20 min makes the pin fail.
  4. Not switching the fake to `MERGED` makes scenario B fail.

## Alternatives

1. **Repeat #1026's 14-day gap with time skipping.** This was dropped because
   the test server's `lockTimer("scheduleWorkflowTask")` stops virtual time
   at the first timer in a worker-less gap. That is the documented negative
   result.
2. **A real dev server without time skipping (the
   `test_b4_update_outage_e2e.py` style), waiting out a short deadline in
   wall-clock time.** This was dropped because the merge-watch interval is a
   15-minute module constant. Shortening it needs a production change, which
   is a STOP condition, and waiting 15 real minutes per run breaks the 300 s
   per-command bound.
3. **Calling `_watch_pr` directly with a mocked workflow context.** This is
   forbidden by the issue (no direct method calls and no substitute for
   Temporal execution), and it could not prove a worker stop and start.

## Platform impact

- **Migrations / compatibility:** none. The change is a new test file only,
  with nothing under `orchestrator/`, `agents/` or `config/`, and no patch
  marker, so the replay of existing histories is unaffected.
- **Resources:** the suite gains two time-skipping scenarios plus one
  record-verification test, a few seconds each. The 20-repeat evidence runs
  are local and one-off.
- **Risks and mitigations:**
  - Sticky-queue or schedule-to-start behaviour after worker 1 stops could
    stall the time-skipping server. Mitigation: `max_cached_workflows=0`, plus
    the 20/20 requirement. Anything less is a negative result.
  - A background timer from the gate, a tick or a delivery could fire during
    the gap and re-engage the lock. Mitigation: the resume record keeps
    `poll_index` 0, settles the gate head and carries no open deliveries. The
    silence assertion catches any regression.
  - The test could be read as proof of a 14-day outage. Mitigation: the
    docstring and the PR state explicitly that it covers only the
    deadline-in-gap path.
- **Release:** the PR must be confirmed as blocked by the #1020 code-owner
  hold. There is no autonomous merge, release, deployment or flag change. B4
  stays FAIL.
