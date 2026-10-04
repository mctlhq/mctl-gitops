# Design: issue-559-temporal-schedule-that-dispatches-portfo

## Current state

- **Schedules.** `orchestrator/temporal/worker.py` `setup_schedules(client)` registers four schedules through `_ensure_schedule(client, schedule_id, desired, label)`:
  - `reconcile-mctl-agents-schedule`: 15 min, offset 3, fires :03/:18/:33/:48.
  - `issue-poll-mctl-agents-schedule`: 15 min, fires :07/:22/:37/:52.
  - `incidents-mctl-agents-schedule`: 1 h, offset 11.
  - `implement-sweep-mctl-agents-schedule`: 15 min, offset 12, fires :12/:27/:42/:57.

  Every schedule is a `ScheduleIntervalSpec` with `policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP)`.
- **Convergence.** `_ensure_schedule` creates a schedule when it is absent. On `ScheduleAlreadyRunningError` it runs `_converge_spec`, which compares **only** `schedule.spec.intervals` and `schedule.policy.overlap` and assigns those fields in place. That preserves the paused state, the note and the rest of the spec. A failure is logged and is not fatal.
- **Who owns schedules.** Only roles `all` and `control` call `setup_schedules` (`owns_schedules`).
- **Collision tests.** `tests/test_worker_schedules.py` builds `setup_schedules` against `_FakeClient` and has two collision tests:
  - `test_no_two_schedules_fire_on_the_same_minute` scans `lcm` of all periods.
  - `test_no_schedule_lands_on_an_argo_cron_minute` checks `_minutes_of_hour(interval)` against `{0, 15, 30}`.

  Both iterate `schedule.spec.intervals` only.
- **Worker registration.** `worker_plans(role)` builds the control-queue `short_activities` list and the `workflows` list. `tests/test_worker_roles.py` pins that specific activities and workflows are on the control plan and absent from execution and implementation plans (for example `merge_pull_request_gated`, `ImplementSweepWorkflow`).
- **GitHub access from activities.** Activities call the GitHub REST API directly with `httpx.AsyncClient`, for example:
  - `orchestrator/temporal/activities/deploy_state.py`
  - `pr_state.py`
  - `issue_state.py`

  They resolve the token with `_resolve_token()` (`activities/proposals.py`: `GITHUB_TOKEN_FILE` first, then `GITHUB_TOKEN`), refuse to make unauthenticated calls, and use `REQUEST_TIMEOUT_SECONDS = 20.0`. Tests patch `httpx.AsyncClient` with a `MockTransport` (`tests/test_lifecycle_activity.py`).
- **Workflow shape.** Thin orchestrating workflows such as `workflows/reconcile.py` and `workflows/incidents.py` import activities under `workflow.unsafe.imports_passed_through()` and declare module-level `RetryPolicy` and timeout constants.
- **Portfolio today.** Nothing in mctl-agents triggers portfolio. Its weekly job depends entirely on GitHub's best-effort cron.

## Proposed solution

### 1. Target list (data, not code)

New module `orchestrator/temporal/scheduled_dispatch.py`. It has no Temporal imports, so workflows, activities and worker can all import it.

```python
@dataclass(frozen=True)
class DispatchTarget:
    repo: str            # "mctlhq/portfolio"
    workflow_file: str   # "weekly-refresh.yml"
    ref: str             # "main"
    weekday: int         # 6 = Sunday (datetime.weekday())
    hour: int            # 8   (UTC)
    minute: int          # 41

    @property
    def schedule_id(self) -> str: ...   # "dispatch-mctlhq-portfolio-weekly-refresh-schedule"
    @property
    def workflow_id(self) -> str: ...   # "dispatch-mctlhq-portfolio-weekly-refresh"

    def interval(self) -> ScheduleIntervalSpec  # every=7d, offset computed

WEEKLY_DISPATCH_TARGETS: tuple[DispatchTarget, ...] = (
    DispatchTarget("mctlhq/portfolio", "weekly-refresh.yml", "main", weekday=6, hour=8, minute=41),
)
```

`interval()` returns `ScheduleIntervalSpec(every=timedelta(days=7), offset=timedelta(days=(weekday - 3) % 7, hours=hour, minutes=minute))`. Temporal interval schedules are aligned to the Unix epoch, and 1970-01-01 was a Thursday (`weekday()==3`), so Sunday gives an offset of 3 days 08:41.

The cadence is an interval rather than a cron or calendar spec for two reasons, both found in the code:
- `_converge_spec` converges only `intervals`, so a calendar spec would never be updated on redeploy.
- Both collision tests read only `intervals`, so a calendar spec would pass them vacuously.

With the interval form, the new schedule converges and is collision-checked through the existing code paths with no changes to them.

`ScheduleIntervalSpec` comes from `temporalio.client`. If importing that from a module the workflow imports causes sandbox friction, the implementer may move `interval()` into `worker.py` as `_weekly_interval(target)`. The dataclass itself stays plain.

### 2. Minute check

The new schedule fires at :41. That clears:
- reconcile (:03/:18/:33/:48)
- issue-poll (:07/:22/:37/:52)
- incidents (:11)
- implement-sweep (:12/:27/:42/:57)
- the Argo cron minutes {0, 15, 30}

For the test math, `lcm(15, 60, 10080) = 10080` minutes, a one-week scan, which is cheap. `_minutes_of_hour` handles the 10080-minute period correctly, since 10080 is divisible by 60.

### 3. Activity: `dispatch_and_observe`

New module `orchestrator/temporal/activities/workflow_dispatch.py`.

```python
@dataclass(frozen=True)
class DispatchInput:
    repo: str
    workflow_file: str
    ref: str
    not_before: datetime   # UTC, fixed per fire by the workflow

@dataclass(frozen=True)
class DispatchResult:
    run_id: int
    html_url: str
    dispatched: bool       # False when a pre-existing run satisfied the fire
```

Errors are subclasses of a module error type, raised as `ApplicationError`:
- `DispatchRejected`: 4xx other than 429. Non-retryable.
- `DispatchFailed`: 5xx, 429 or transport error. Retryable.
- `RunsListingUnreadable`: retryable.
- `RunNotObserved`: non-retryable.

Algorithm:

1. Resolve the token with `asyncio.to_thread(_resolve_token)`. If it is empty, raise a non-retryable error, matching the "refusing an unauthenticated lookup" convention.
2. **Pre-check.** `GET /repos/{repo}/actions/workflows/{workflow_file}/runs?event=workflow_dispatch&branch={ref}&created=>={iso(not_before - SKEW_SLACK)}&per_page=20`.
   - Non-2xx, a transport error, or a body without a `workflow_runs` list raises `RunsListingUnreadable`.
   - If any run is found, return it with `dispatched=False`.
3. **Dispatch.** `POST /repos/{repo}/actions/workflows/{workflow_file}/dispatches` with `{"ref": ref}`.
   - 2xx means accepted. The success code is 204; a 200 is also accepted, in case GitHub returns run details.
   - 429 or 5xx raises `DispatchFailed`.
   - Any other non-2xx raises `DispatchRejected`, with the status code and the first 500 characters of the response body.
4. **Observe.** Repeat the step-2 listing every `POLL_INTERVAL` (10 s), calling `activity.heartbeat()` on each loop, until `OBSERVE_TIMEOUT` (5 min).
   - The first run found returns `dispatched=True`.
   - A listing failure during this phase raises `RunsListingUnreadable`. The listing is never interpreted as empty.
   - If the timeout passes with no run, raise `RunNotObserved` (non-retryable).

Headers are `Authorization: Bearer <token>`, `Accept: application/vnd.github+json` and `X-GitHub-Api-Version: 2022-11-28`. `SKEW_SLACK` is 60 s.

### 4. Workflow: `ScheduledDispatchWorkflow`

New module `orchestrator/temporal/workflows/scheduled_dispatch.py`.

```python
@workflow.defn
class ScheduledDispatchWorkflow:
    @workflow.run
    async def run(self, target: ScheduledDispatchInput) -> DispatchResult:
        not_before = workflow.now()          # deterministic, fixed for this fire
        return await workflow.execute_activity(
            dispatch_and_observe,
            DispatchInput(target.repo, target.workflow_file, target.ref, not_before),
            start_to_close_timeout=timedelta(minutes=8),
            heartbeat_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=30),
                                     non_retryable_error_types=["DispatchRejected", "RunNotObserved", "NoGitHubToken"]),
        )
```

`ScheduledDispatchInput` holds `repo`, `workflow_file` and `ref`, so the schedule action's arguments stay plain data. The workflow does not catch the activity error: an `ActivityError` propagates and the workflow execution is marked **Failed**. That failed execution is the visible signal, and it appears in Temporal visibility and in the worker's Prometheus metrics (`telemetry_config`).

Why this is bounded to one dispatch per fire:
- Every attempt runs the pre-check first.
- `RunNotObserved` is non-retryable, so an accepted dispatch whose run is merely slow to appear is never re-dispatched.
- At most 3 attempts.

### 5. Registration in `worker.py`

- In `setup_schedules`, after implement-sweep:

  ```python
  for target in WEEKLY_DISPATCH_TARGETS:
      await _ensure_schedule(client, target.schedule_id, Schedule(
          action=ScheduleActionStartWorkflow(ScheduledDispatchWorkflow.run,
              ScheduledDispatchInput(target.repo, target.workflow_file, target.ref),
              id=target.workflow_id, task_queue=TASK_QUEUE),
          spec=ScheduleSpec(intervals=[target.interval()]),
          policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP),
      ), f"ScheduledDispatchWorkflow[{target.repo}:{target.workflow_file}]")
  ```

  Add a comment block explaining the :41 choice and the epoch-Thursday offset, in the style of the existing comments.
- Add `dispatch_and_observe` to `short_activities`, because it makes bounded HTTP calls and does no Argo or mutex wait. Add `ScheduledDispatchWorkflow` to `workflows`. Both land on the control queue only.
- Update the module docstring's workflow list.

### 6. Post-deploy verification

Run `temporal schedule trigger --schedule-id dispatch-mctlhq-portfolio-weekly-refresh-schedule` in namespace `mctl-agents`. Confirm the workflow completes with a `DispatchResult`, then confirm the `workflow_dispatch` run in `mctlhq/portfolio` succeeds.

## Alternatives

1. **Calendar or cron spec (`ScheduleSpec(cron_expressions=["41 8 * * 0"])` or `ScheduleCalendarSpec`).** This is closest to the issue's wording. It was dropped because `_converge_spec` and both collision tests understand only `intervals`. Supporting it would mean widening convergence logic that already has subtle, hard-won rules (the field-only assignment and the retry-verdict handling in `TestConvergenceRetries`), plus extending the tests. The interval form is exactly equivalent for a UTC weekly fire. Recorded as Open question 2.
2. **Fire-and-forget dispatch (POST, then return on 204).** This is simpler, but it repeats the original defect: a 204 is not evidence that a run started. The issue explicitly requires observing the run.
3. **Argo CronWorkflow in mctl-gitops that runs `gh workflow run`.** This would keep the trigger in a second cron system with no retry or observation semantics and no Temporal visibility. It would also add a cross-repo change for a feature the issue places in the Temporal control plane.
4. **A dedicated `PortfolioWeeklyRefreshWorkflow` class.** This was rejected in favour of the target list, per the issue, so that the next weekly job is one tuple entry.

## Platform impact

- **Migrations.** None. The new schedule is created on the first control or `all` worker start after deploy. No existing schedule, workflow type or activity changes, so replay compatibility of existing histories is unaffected (new types only).
- **Backward compatibility.** Additive. The four existing schedules and their tests keep their behaviour. The GitHub `schedule:` cron in portfolio stays as a backstop. A double run is harmless (portfolio `concurrency` group, upserted `fix/weekly-snapshot` PR).
- **Resources.** One workflow per week, at most about 3 short activity attempts with up to roughly 30 GitHub API requests (5 min at 10 s polling). This is negligible against the installation's rate limit and adds nothing to `mctl-gitops-main-writes` contention, since no gitops write is made.
- **Risks and mitigations.**
  - *Token lacks `actions:write` on portfolio.* The dispatch returns 403 or 404, raises `DispatchRejected`, and the workflow fails visibly. Fix the token target in mctl-gitops (Open question 1). This is verified by the manual trigger before the portfolio cron is removed.
  - *GitHub run-listing lag beyond 5 min.* The result is `RunNotObserved`, a visible failure. The portfolio run may still start, and the backstop cron still exists. The timeout is a module constant and can be tuned.
  - *Worker clock skew against GitHub `created` timestamps.* Mitigated by the 60 s `SKEW_SLACK`.
  - *A schedule created in a wrong shape by a buggy first deploy.* `_ensure_schedule` converges intervals and overlap on the next deploy. A pause survives redeploys.
  - *Duplicate dispatch.* Bounded by the pre-check, the non-retryable `RunNotObserved`, max 3 attempts, and overlap SKIP.
