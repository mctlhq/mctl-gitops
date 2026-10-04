# Tasks: issue-561-scheduled-dispatch-converge-actions-gc-u

- [ ] 1. In `orchestrator/temporal/scheduled_dispatch.py`, add
  `DISPATCH_SCHEDULE_PREFIX = "dispatch-"`, `DISPATCH_SCHEDULE_SUFFIX = "-schedule"`,
  `validate_repo` and `validate_workflow_file` (regexes in design section 3), and
  `DispatchTarget.__post_init__` validating repo, workflow_file, ref
  (non-empty, no whitespace or control characters), weekday, hour and minute.
  Build `schedule_id` from the prefix and suffix constants.
  DoD: the existing portfolio target still imports; bad values raise
  `ValueError`; `schedule_id` is unchanged for the existing target.
- [ ] 2. (depends on 1) In `orchestrator/temporal/activities/workflow_dispatch.py`,
  add the non-retryable `InvalidDispatchTarget` and a `_validated(repo, workflow_file)`
  helper. Call it first in `dispatch_and_observe` and `report_dispatch_failure`,
  before `_token()`. Add `"InvalidDispatchTarget"` to `DISPATCH_NON_RETRYABLE`
  and `REPORT_NON_RETRYABLE` in `orchestrator/temporal/workflows/scheduled_dispatch.py`.
  DoD: invalid input makes zero HTTP requests and fails non-retryably.
- [ ] 3. Paginate the alert-issue search in `report_dispatch_failure`: follow
  `resp.links["next"]` up to `ALERT_SEARCH_MAX_PAGES = 10`; refuse a `next`
  URL that does not start with `GITHUB_API`; raise `AlertIssueSearchUnreadable`
  when the cap is hit without a match; keep per-page status and parse handling
  identical to today. DoD: a match on page 2 is commented on, and no issue is
  created.
- [ ] 4. In `orchestrator/temporal/worker.py::_ensure_schedule`, add the
  keyword-only `converge_action: bool = False`, the helpers
  `_action_fingerprint_live` (reads `raw_info`) and `_action_fingerprint_desired`
  (encodes via `client.data_converter`, computed once before `update`), action
  replacement inside the update callback when stale, `"action"` in `changed`,
  and updated log text. A fingerprint error logs a WARNING and skips only the
  action. DoD: positional call shape unchanged; `tools/diagram_facts.py`
  output unchanged.
- [ ] 5. (depends on 1, 4) In `setup_schedules`, pass `converge_action=True` in
  the dispatch loop. Add `_gc_dispatch_schedules(client, declared)` (collect
  first, then delete; errors logged at ERROR and never raised) and call it after
  the loop. DoD: undeclared `dispatch-*-schedule` ids are deleted; nothing
  else is touched.
- [ ] 6. In `ScheduledDispatchWorkflow.run`, on report failure log the
  `ALERT_UNDELIVERED_MARKER = "scheduled_dispatch_alert_undelivered"` line at
  ERROR with repo, workflow_file, workflow_id, error_type and report error, and
  increment the `workflow.metric_meter()` counter
  `scheduled_dispatch_alert_undelivered{repo,workflow_file}`. Still re-raise the
  original error. DoD: covered by a workflow test; replay-safe.
- [ ] 7. Update the docstrings in `scheduled_dispatch.py`, `workflow_dispatch.py`
  and `_ensure_schedule` (code owns the prefix; action convergence; pagination;
  second channel). Add a CHANGELOG entry if the repo convention needs one.
  DoD: the docs describe the new behaviour; no stale claims ("converges only
  the spec") remain.

- **[Operator note 2026-10-04, retry]** While implementing, run only the test files you touch: `uv run --frozen python -m pytest tests/test_worker_schedules.py tests/test_workflow_dispatch_activity.py tests/test_scheduled_dispatch_workflow.py -q`, plus the diagram-facts test if present. Do NOT run the whole `tests/` suite inside the agent: it takes more than 5 minutes, and on 2026-10-04 the first attempt was killed as an orphaned sub-agent while a full-suite run was still going. CI runs the full suite on the PR.

## Tests

- [ ] T1. `tests/test_worker_schedules.py`: with `converge_action=True` and a live
  action whose `raw_info` encodes `ref="main"`, a desired `ref="release"` yields
  exactly one update with the new action, and `state.paused` and `state.note`
  are preserved. The fake handle must expose `raw_info`; build it with the real
  converter (`DataConverter.default`) and the Temporal protos.
- [ ] T2. An identical live and desired action with `converge_action=True`
  yields no update. An action-only difference with `converge_action=False`
  (default) yields no update.
- [ ] T3. A spec, policy and action that are all stale yield one update, and the
  log names "spec and overlap policy and action". The callback re-run
  (optimistic retry) does not double-count `changed`.
- [ ] T4. `_gc_dispatch_schedules`: given listed ids
  {`dispatch-a-x-schedule` (declared), `dispatch-b-y-schedule` (undeclared),
  `reconcile-mctl-agents-schedule`, `dispatch-foo` (no suffix)}, only
  `dispatch-b-y-schedule` is deleted. A list failure deletes nothing and does
  not raise. A delete failure on one id still attempts the others. An empty
  declared set deletes every dispatch schedule.
- [ ] T5. `setup_schedules` with the fake client runs GC after registration. The
  existing policy-count test still passes; extend `_FakeClient` with
  `list_schedules` returning an async iterator.
- [ ] T6. `DispatchTarget` validation: `mctlhq/portfolio` + `weekly-refresh.yml`
  passes; `mctlhq/../x`, `a/b/c`, `mctlhq/portfolio?x`, `wf.yml/../dispatches`,
  `wf.txt`, `.yml`, `ref=""`, `weekday=7` and `minute=60` raise. All
  `WEEKLY_DISPATCH_TARGETS` schedule ids are unique and match the prefix and
  suffix.
- [ ] T7. `tests/test_workflow_dispatch_activity.py`: an invalid repo or
  workflow_file in either activity raises `InvalidDispatchTarget` with zero
  requests recorded by the MockTransport, and the token is not even resolved.
- [ ] T8. Pagination: a match on page 2 via the `Link` header is commented on,
  with no create. No match on two pages ending without `next` creates an issue.
  Eleven pages without a match raise `AlertIssueSearchUnreadable`, with no
  create. A foreign-host `next` URL raises without following it. A 500 on
  page 2 raises `AlertIssueSearchUnreadable`.
- [ ] T9. `tests/test_scheduled_dispatch_workflow.py`: when both dispatch and
  report fail (e.g. a report raising `NoGitHubToken` on every attempt), the
  workflow logs the `scheduled_dispatch_alert_undelivered` marker and still
  fails with the original dispatch error type.
- [ ] T10. `tools/diagram_facts.py` still extracts the same schedules (existing
  diagram-facts test, if present, stays green).

## Rollback

Every change is code-only, with no migration. Revert the PR and redeploy the
worker. After the revert:
- Action convergence stops. Live schedules keep whatever action was last
  pushed, which is a declared one, so this is harmless.
- GC stops. Any schedule already deleted stays deleted; re-adding its
  `WEEKLY_DISPATCH_TARGETS` entry and redeploying re-creates it.
- If only GC misbehaves in production (for example it deletes a hand-made
  schedule), the narrower fix is to make `_gc_dispatch_schedules` a no-op
  behind a one-line change and re-create the schedule with
  `temporal schedule create`. Pausing is not a GC safeguard, because GC
  deletes paused undeclared schedules too.
- If action convergence loops (an update on every boot), set
  `converge_action=False` at the dispatch call site.
