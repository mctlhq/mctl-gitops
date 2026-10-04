# Design: issue-561-scheduled-dispatch-converge-actions-gc-u

## Current state

- `orchestrator/temporal/scheduled_dispatch.py` defines the frozen dataclass
  `DispatchTarget(repo, workflow_file, ref, weekday, hour, minute)`.
  `schedule_id` (`dispatch-<repo-slug>-<workflow-stem>-schedule`) and
  `workflow_id` are derived from `repo` and `workflow_file` only. `ref` is not
  part of the id. `WEEKLY_DISPATCH_TARGETS` currently holds one entry
  (`mctlhq/portfolio`, `weekly-refresh.yml`, `main`, Sunday 10:01 UTC). Field
  values are not validated.
- `orchestrator/temporal/worker.py::setup_schedules` (lines ~429-444) loops over
  `WEEKLY_DISPATCH_TARGETS` and calls
  `_ensure_schedule(client, target.schedule_id, Schedule(action=ScheduleActionStartWorkflow(ScheduledDispatchWorkflow.run, ScheduledDispatchInput(repo, workflow_file, ref), id=target.workflow_id, task_queue=TASK_QUEUE), ...), "ScheduledDispatchWorkflow")`.
  Nothing ever lists or deletes schedules. `setup_schedules` runs once per boot
  of a worker whose role owns schedules (`owns_schedules(args.role)`, line ~726).
- `_ensure_schedule` (worker.py:134) tries `create_schedule`. On
  `ScheduleAlreadyRunningError` it calls `handle.update(_converge_spec)`, which
  compares and assigns only `schedule.spec.intervals` and
  `schedule.policy.overlap`, and records what changed in `changed`. The
  callback resets `changed` because `update()` may retry. All errors are logged
  at ERROR and never raised. `schedule.action` is never compared, so a new `ref`
  stays declared but never reaches the cluster.
- In temporalio 1.31, a described schedule's action is
  `ScheduleActionStartWorkflow("<unset>", raw_info=NewWorkflowExecutionInfo)`
  (`ScheduleActionStartWorkflow._from_proto`). Workflow type, id, task queue
  and input payloads are therefore only available on `raw_info`, as protos.
- `orchestrator/temporal/activities/workflow_dispatch.py`:
  - `_find_run` and `_post_dispatch` interpolate `inp.repo` and
    `inp.workflow_file` into `/repos/{repo}/actions/workflows/{file}/...`
    without validation.
  - `report_dispatch_failure` interpolates `rep.repo` into the label, issue and
    comment paths. It makes one `GET /repos/{repo}/issues?state=open&labels=scheduled-dispatch-failed&per_page=100`
    and matches by title on that page only, so a match on page 2 or later is
    missed and a duplicate issue is filed.
  - Every call uses `_token()` (the GitHub App token via
    `proposals._resolve_token`). `NoGitHubToken` is retryable.
- `orchestrator/temporal/workflows/scheduled_dispatch.py::ScheduledDispatchWorkflow`
  catches the dispatch failure and runs `report_dispatch_failure`. If that also
  fails, it only does `workflow.logger.error("failed to file the dispatch-failure alert issue: ...")`
  and re-raises the original error. Non-retryable lists:
  `DISPATCH_NON_RETRYABLE = ["DispatchRejected", "RunNotObserved"]` and
  `REPORT_NON_RETRYABLE = ["AlertReportRejected"]`.
- Tests: `tests/test_worker_schedules.py` (a fake client and handle; the
  callback receives `SimpleNamespace(description=SimpleNamespace(schedule=...))`),
  `tests/test_workflow_dispatch_activity.py` (httpx MockTransport via `_drive`)
  and `tests/test_scheduled_dispatch_workflow.py`.
- `tools/diagram_facts.py::_SCHEDULE_RE` greps for
  `_ensure_schedule(client, \w+, \w+, "(\w+)"`. The call shape must stay
  compatible: extra arguments must be keyword arguments placed after the label.

## Proposed solution

### 1. Opt-in action convergence in `_ensure_schedule`

Signature: `_ensure_schedule(client, schedule_id, desired, label, *, converge_action: bool = False)`.
The dispatch loop passes `converge_action=True`. The other four call sites are
unchanged.

The action is compared as normalized protos:
- Add a helper `_action_fingerprint_live(action) -> tuple | None`. It reads
  `action.raw_info` and returns
  `(workflow_type.name, workflow_id, task_queue.name, tuple((p.metadata, p.data) for p in input.payloads))`.
  If `raw_info` is missing, it returns `None`.
- Add a helper `async _action_fingerprint_desired(client, action) -> tuple`. It
  builds the same tuple from the desired `ScheduleActionStartWorkflow`: the
  workflow name via `temporalio.workflow._Definition.must_from_run_fn` (or the
  `workflow` string if it is already a string), `id`, `task_queue`, and
  `await client.data_converter.encode(action.args)`. This is the same converter
  the client uses for `create_schedule`, so the encoding is identical. The
  payload metadata maps are compared as sorted items.
- Compute the desired fingerprint once, before `handle.update`. The update
  callback stays effectively pure and retry-safe.
- Inside `_converge_spec` (renamed `_converge`): if `converge_action` is set
  and the live fingerprint is `None` or differs from the desired one, set
  `schedule.action = desired.action` and append `"action"` to `changed`. The
  whole action object is replaced on purpose. Code owns every field of a
  dispatch action, and no operator workflow edits it (unlike `state`).
- Update the log messages ("spec, overlap policy and action are current").
- If the fingerprint cannot be computed (for example an encoder error), log a
  WARNING, skip action convergence, and still converge spec and policy.

Why a fingerprint rather than a memo or a hash in the id: `ScheduleUpdate`
cannot change the schedule memo. Putting the `ref` into `schedule_id` would
create a second, orphaned schedule. That problem is solved by GC (section 2),
but it turns every edit into a delete-and-create and loses the schedule's
pause state.

### 2. Garbage-collect undeclared `dispatch-*` schedules

New `async def _gc_dispatch_schedules(client, declared: set[str]) -> None` in
`worker.py`, called at the end of `setup_schedules` with
`{t.schedule_id for t in WEEKLY_DISPATCH_TARGETS}`:

```
DISPATCH_SCHEDULE_PREFIX = "dispatch-"
DISPATCH_SCHEDULE_SUFFIX = "-schedule"
try:
    stale = [s.id async for s in await client.list_schedules()
             if s.id.startswith(PREFIX) and s.id.endswith(SUFFIX) and s.id not in declared]
except Exception as exc: logger.error(...); return
for sid in stale:
    try: await client.get_schedule_handle(sid).delete(); logger.warning("Deleted undeclared ...")
    except Exception as exc: logger.error(...)
```

- The candidate list is collected first and deleted afterwards, so a listing
  failure deletes nothing.
- The prefix constants move to `scheduled_dispatch.py` next to `DispatchTarget`.
  `schedule_id` is built from them, so the producer and the collector cannot
  drift apart.
- A `DispatchTarget` whose `schedule_id` does not match the prefix and suffix
  fails an assertion in a unit test.
- `list_schedules` uses Temporal visibility, which is eventually consistent. A
  schedule created moments ago is in `declared` anyway, so it is never a
  candidate. A just-deleted schedule may still be listed, and the resulting
  NotFound on delete is logged and ignored.
- Duplicate ids: `DispatchTarget` adds no check, but a test asserts that the
  `schedule_id` values of `WEEKLY_DISPATCH_TARGETS` are unique. Two targets
  sharing an id would make one silently overwrite the other.

### 3. Validate `repo` / `workflow_file`

New module-level validators in `scheduled_dispatch.py` (pure, importable from
activities without the worker):

```
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_WORKFLOW_FILE_RE = re.compile(r"^[A-Za-z0-9_.-]+\.ya?ml$")
def validate_repo(v): fullmatch and no segment in {".", ".."} else ValueError
def validate_workflow_file(v): fullmatch and v not in {".yml", ".yaml"} else ValueError
```

- `DispatchTarget.__post_init__` calls both and also checks
  `0 <= weekday <= 6`, `0 <= hour <= 23` and `0 <= minute <= 59`, so a bad
  entry fails at import time, in CI.
- `workflow_dispatch.py` gets `_validated(repo, workflow_file)`, called first
  in `dispatch_and_observe` and `report_dispatch_failure` (before `_token()`).
  On error it raises the new non-retryable `InvalidDispatchTarget(ApplicationError, type="InvalidDispatchTarget")`.
  Inputs come from schedules and can be stale or hand-edited, so the activity
  does not trust import-time validation alone.
- `InvalidDispatchTarget` is added to both `DISPATCH_NON_RETRYABLE` and
  `REPORT_NON_RETRYABLE` in `workflows/scheduled_dispatch.py`. When the report
  fails this way, the workflow falls through to the second channel (section 5),
  which is the correct outcome: a repo that cannot be named in a URL cannot
  take an alert issue either.
- `ref` is sent only as a query parameter (`branch=`) and as a JSON body field,
  both encoded by httpx, so it is not path-validated. It gets a light sanity
  check (non-empty, no whitespace or control characters) in `DispatchTarget`.

### 4. Paginate the alert-issue search

In `report_dispatch_failure`, replace the single GET with a loop:

```
url, params = f"/repos/{repo}/issues", {...per_page: 100}
for _ in range(ALERT_SEARCH_MAX_PAGES):   # 10
    resp = await _call("issue search", client.get(url, params=params))
    <same status handling as today>
    <same parse/match as today>; if match: break
    nxt = resp.links.get("next", {}).get("url")
    if not nxt: break (complete, no match)
    url, params = nxt, None
else: raise AlertIssueSearchUnreadable("issue search exceeded N pages without a match")
```

- `next` URLs are absolute `https://api.github.com/...`. httpx accepts an
  absolute URL on a client that has a `base_url`, and the URL keeps the auth
  header because the host is the same. The loop verifies that `next` starts
  with `GITHUB_API` before following it, and raises
  `AlertIssueSearchUnreadable` otherwise, so the token never goes to another
  host.
- Hitting the cap is treated as unreadable (retryable) rather than as "no
  issue", which matches the module docstring: an incomplete listing is never
  read as absence.

### 5. Second alert channel, independent of the GitHub App token

In `ScheduledDispatchWorkflow.run`, the `except Exception as report_exc` branch
becomes:

```
workflow.logger.error(
    "scheduled_dispatch_alert_undelivered repo=%s workflow_file=%s workflow_id=%s error_type=%s report_error=%s",
    ...)
workflow.metric_meter().create_counter("scheduled_dispatch_alert_undelivered", ...).add(
    1, {"repo": inp.repo, "workflow_file": inp.workflow_file})
```

- `workflow.metric_meter()` is replay-safe: temporalio suppresses metrics
  during replay. Metrics already reach `:METRICS_PORT/metrics` through
  `telemetry_config()` in worker.py, so neither the counter nor the log line
  needs GitHub credentials.
- The marker string goes in a module constant `ALERT_UNDELIVERED_MARKER` so
  tests and future alert rules can reference it.
- The original dispatch error is still re-raised, unchanged.

## Alternatives

1. Always converge actions for every schedule, not just opt-in. Dropped for
   now. `implement_sweep` derives its input from env
   (`implement_sweep_grace_minutes()`), and the reconcile and incidents actions
   have run for months without action convergence. Turning it on everywhere in
   a P3 cleanup widens the blast radius: a converter or metadata mismatch would
   cause an update on every boot for every schedule. The flag makes the later
   switch a one-line change.
2. Encode `ref` (or an input hash) into `schedule_id`, and rely on GC to delete
   the old schedule. Dropped. Any edit then means delete plus create, which
   loses the pause state and the schedule's recent-action history, and the
   GC/visibility lag can leave both schedules running briefly.
3. Use GitHub's search API (`/search/issues?q=repo:... label:... in:title`)
   instead of paginating the listing. Dropped. Search has a separate, tighter
   rate limit, is eventually consistent (it may miss an issue just filed by a
   retry), and its title match is fuzzy. Paginating the authoritative listing
   keeps today's semantics.
4. Second channel via an mctl-api incident POST. Deferred (see Open
   questions). The repo has a read client only (`list_service_incidents`), and
   no ingestion endpoint is known from this clone. Adding a new external
   contract in a P3 cleanup is speculative. The metric plus log need no new
   contract.

## Platform impact

- Migrations: none. On the first deploy the existing
  `dispatch-mctlhq-portfolio-weekly-refresh-schedule` is compared by
  fingerprint. It was created from the same action, so it should be current
  and no update is expected. If the converter metadata differs, one update
  replaces the action with an identical one, which is harmless.
- Backward compatibility: `_ensure_schedule`'s positional signature is
  unchanged, so `tools/diagram_facts.py::_SCHEDULE_RE` still matches.
  `DispatchTarget` gains validation only, and the current entry passes it.
- Resources: one `ListSchedules` call per worker boot, plus at most one delete
  per orphan. Alert search makes at most 10 GETs, and only on the failure path.
- Risks and mitigations:
  - GC deletes a hand-made `dispatch-*` schedule. The prefix is documented as
    code-owned in `scheduled_dispatch.py`, every deletion is logged at WARNING
    with the id, and the narrow prefix plus suffix match limits the reach.
  - Rolling deploy: an old pod booting after a new pod can re-create a removed
    target's schedule. The next boot of a new pod deletes it again, and
    schedule-owning roles are a single control deployment, so the window is one
    rollout.
  - A fingerprint mismatch loop (an update on every boot). The convergence log
    names "action", which makes the loop visible. Fallback: set the flag to
    False.
  - Validation rejects a legitimate repo or file name. The patterns follow
    GitHub's own allowed characters, and unit tests cover realistic names.
