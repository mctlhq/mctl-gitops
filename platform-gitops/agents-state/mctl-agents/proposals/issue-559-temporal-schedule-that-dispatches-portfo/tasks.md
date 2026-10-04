# Tasks: issue-559-temporal-schedule-that-dispatches-portfo

- [ ] 1. Add `orchestrator/temporal/scheduled_dispatch.py` with the frozen `DispatchTarget` dataclass (`repo`, `workflow_file`, `ref`, `weekday`, `hour`, `minute`), the `schedule_id` and `workflow_id` properties, the weekly `interval()` derivation (`every=7d`, `offset=((weekday-3)%7) days + hour + minute`, epoch Thursday), and `WEEKLY_DISPATCH_TARGETS` with the single portfolio entry (`mctlhq/portfolio`, `weekly-refresh.yml`, `main`, Sunday 08:41 UTC). — DoD: the module imports with no Temporal worker dependency, and the docstring explains the epoch-Thursday offset and why the cadence is an interval rather than a cron (`_converge_spec` and the collision tests read only `intervals`).
- [ ] 2. Add `orchestrator/temporal/activities/workflow_dispatch.py` with `DispatchInput`, `DispatchResult` and the `dispatch_and_observe` activity, which runs pre-check, dispatch, then observe (depends on 1). — DoD:
  - Token comes from `_resolve_token`. An empty token gives a non-retryable refusal and no unauthenticated request.
  - Dispatch: 429/5xx/transport errors are retryable; other 4xx raise non-retryable `DispatchRejected`.
  - An unreadable runs listing raises `RunsListingUnreadable` and is never read as empty.
  - No run within `OBSERVE_TIMEOUT` (5 min) raises non-retryable `RunNotObserved`.
  - The activity heartbeats while polling.
  - Constants are named at module level: `POLL_INTERVAL`, `OBSERVE_TIMEOUT`, `SKEW_SLACK`.
- [ ] 3. Add `orchestrator/temporal/workflows/scheduled_dispatch.py` with `ScheduledDispatchInput` and `ScheduledDispatchWorkflow` (depends on 2). — DoD:
  - The workflow fixes `not_before = workflow.now()` once and calls the activity with `RetryPolicy(maximum_attempts=3, non_retryable_error_types=[...])`, `start_to_close_timeout` of 8 min and `heartbeat_timeout` of 1 min.
  - It does not swallow activity errors, so a failure fails the workflow execution.
  - The activity is imported under `workflow.unsafe.imports_passed_through()`.
- [ ] 4. Register the new pieces in `orchestrator/temporal/worker.py` (depends on 1-3). — DoD:
  - `setup_schedules` loops over `WEEKLY_DISPATCH_TARGETS` and calls `_ensure_schedule` with `ScheduleActionStartWorkflow(ScheduledDispatchWorkflow.run, ...)`, `id=target.workflow_id`, `task_queue=TASK_QUEUE`, `ScheduleSpec(intervals=[target.interval()])` and an explicit `SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP)`.
  - A comment explains why :41 clears every Temporal and Argo minute.
  - `dispatch_and_observe` is added to `short_activities` and `ScheduledDispatchWorkflow` to `workflows`.
  - The module docstring lists the new workflow.
- [ ] 5. Confirm the token scope (depends on 4). — DoD: someone has confirmed that the token the worker mounts (`GITHUB_TOKEN_FILE` / `GITHUB_TOKEN`) can dispatch workflows in `mctlhq/portfolio` (`actions:write`). If it cannot, an mctl-gitops PR that widens the worker's token target is opened and linked from the implementation PR.
- [ ] 6. Verify after deploy (depends on 4, 5). — DoD: `temporal schedule trigger --schedule-id dispatch-mctlhq-portfolio-weekly-refresh-schedule --namespace mctl-agents` produces a Completed `ScheduledDispatchWorkflow` whose result names a `workflow_dispatch` run of `weekly-refresh.yml` in `mctlhq/portfolio`, and that run concludes `success`. Record the result on issue #559. Only then open the follow-up portfolio change that removes the `schedule:` trigger.

## Tests

Each test must fail when the guard it covers is removed.

- [ ] T1. `tests/test_worker_schedules.py`: the new schedule spec. Using `_FakeClient`, find `dispatch-mctlhq-portfolio-weekly-refresh-schedule` in `client.created`. Assert one interval with `every == timedelta(days=7)`. Compute `epoch + offset` and the next fire after a fixed reference instant, and assert `weekday() == 6`, `hour == 8`, `minute == 41` (UTC). It fails if the weekday arithmetic (epoch Thursday) or the time changes.
- [ ] T2. `tests/test_worker_schedules.py`: the existing `test_no_two_schedules_fire_on_the_same_minute` and `test_no_schedule_lands_on_an_argo_cron_minute` pass with the new schedule included. Add an assertion that the weekly schedule's id appears among the scanned specs, so a future change to a non-interval spec cannot make it vacuously invisible. Check manually: moving the minute to :00 or :12 makes the relevant test fail.
- [ ] T3. `tests/test_worker_schedules.py` (`TestOverlapPolicy`): the existing "every schedule declares SKIP explicitly" test covers the new schedule.
- [ ] T4. `tests/test_worker_roles.py`: `dispatch_and_observe` is in `control.activity_names` and absent from the execution and implementation plans. `ScheduledDispatchWorkflow` is in the control plan's workflows and absent from the others.
- [ ] T5. New `tests/test_workflow_dispatch_activity.py`, patching `httpx.AsyncClient` with `httpx.MockTransport` as `tests/test_lifecycle_activity.py` does. Patch the clock and sleep helpers so the tests run without real waiting. Cases:
  - Dispatch 422 raises a non-retryable `DispatchRejected`.
  - Dispatch 500 and dispatch 429 raise a retryable `DispatchFailed`.
  - Runs listing 500 or malformed JSON, in both the pre-check and the observe phase, raises `RunsListingUnreadable`. No POST is made when the pre-check fails.
  - 204 followed by empty listings until the timeout raises a non-retryable `RunNotObserved`.
  - 204 followed by a run on the second poll returns `DispatchResult(dispatched=True, run_id=...)`.
  - A pre-check that finds a run returns `dispatched=False` and makes **no** POST. This is the retry-idempotency guard.
  - An empty token raises before any request is made.
  - The request carries `event=workflow_dispatch`, `branch=main` and a `created>=` filter derived from `not_before - SKEW_SLACK`.
- [ ] T6. New `tests/test_scheduled_dispatch_workflow.py`, using the existing `tests/temporal_harness.py` time-skipping environment with a mocked activity. Cases:
  - A successful activity gives a workflow result equal to the activity result.
  - An activity raising `RunNotObserved` gives a Failed workflow (`WorkflowFailureError`), after exactly one attempt.
  - An activity raising `DispatchFailed` is retried and stops at 3 attempts.
  - `not_before` is identical across attempts.

## Rollback

- Immediate, no deploy: `temporal schedule pause --schedule-id dispatch-mctlhq-portfolio-weekly-refresh-schedule --namespace mctl-agents`. `_ensure_schedule` never touches `state`, so the pause survives redeploys. The portfolio GitHub `schedule:` cron is still in place as the backstop, so pausing restores the pre-change behaviour exactly.
- Full: revert the implementation PR, then `temporal schedule delete --schedule-id dispatch-mctlhq-portfolio-weekly-refresh-schedule`. Removing the target from `setup_schedules` does not delete an existing schedule, and with the workflow type unregistered, any later fire would fail to start.
- Do not remove portfolio's `schedule:` trigger until task 6 has passed. That keeps rollback free of cross-repo coordination.
