# Scheduled dispatch: converge actions, GC undeclared schedules, validate paths

## Context

mctl-agents#559 (PR #560) added weekly Temporal schedules that dispatch GitHub
workflows. Each schedule is generated from one entry in
`orchestrator/temporal/scheduled_dispatch.py::WEEKLY_DISPATCH_TARGETS`. The
review deferred five P3 findings, and issue #561 collects them:

1. `_ensure_schedule` (`orchestrator/temporal/worker.py`) converges only the
   intervals and the overlap policy. If an existing `dispatch-*` schedule's
   `ref` or other action input changes, the new value never reaches it.
2. When a target is removed or renamed, its old `dispatch-*` schedule keeps
   firing forever.
3. `repo` and `workflow_file` go into GitHub URL paths without validation.
4. `report_dispatch_failure` reads only the first page (100 items) of open
   alert-labelled issues. It can miss an existing alert issue and file a
   duplicate.
5. All alerting depends on the GitHub App token, so a token failure is the one
   failure that cannot be reported.

These matter for the same reason as the rest of this file's history: a value
declared in code but never pushed to the cluster is decorative, and a schedule
nobody declares any more is invisible until it does damage.

## User stories

- AS an operator editing `WEEKLY_DISPATCH_TARGETS` I WANT a changed `ref` (or
  other action input) to reach the live schedule on the next deploy SO THAT
  the code is the source of truth.
- AS an operator I WANT removing or renaming a target to stop its old schedule
  SO THAT nothing dispatches workflows that nobody declares.
- AS a maintainer I WANT malformed `repo`/`workflow_file` values rejected before
  they reach any URL SO THAT a typo or crafted value cannot reach a different
  GitHub API path.
- AS an on-call engineer I WANT exactly one alert issue per failing workflow,
  however many alert-labelled issues are open, SO THAT alerts are not
  duplicated.
- AS an on-call engineer I WANT a dispatch failure that cannot be reported to
  GitHub to still be visible somewhere SO THAT a token outage does not hide it.

## Acceptance criteria (EARS)

Action convergence
- WHEN `setup_schedules` runs and a `dispatch-*` schedule exists whose action
  differs from the declared one (workflow type, workflow id, task queue, or
  encoded input arguments, including `ref`), THE SYSTEM SHALL replace the live
  schedule's action with the declared action.
- WHEN the live action already matches the declared action, THE SYSTEM SHALL
  NOT issue an update for the action.
- WHILE converging an action, THE SYSTEM SHALL leave `state` (paused flag and
  note), the spec fields other than `intervals`, and the policy fields other
  than `overlap` unchanged.
- WHEN an update is applied, THE SYSTEM SHALL log which parts converged
  ("spec", "overlap policy", "action").
- IF a caller of `_ensure_schedule` does not opt in to action convergence, THEN
  THE SYSTEM SHALL keep today's behaviour for that schedule (reconcile,
  issue-poll, incidents and implement-sweep are unchanged).

Garbage collection
- WHEN `setup_schedules` has processed every declared dispatch target, THE
  SYSTEM SHALL list the namespace's schedules and delete each one whose id
  matches `dispatch-*-schedule` and is not the `schedule_id` of any current
  `WEEKLY_DISPATCH_TARGETS` entry.
- THE SYSTEM SHALL NOT delete any schedule outside the `dispatch-` id prefix.
- IF listing or deleting schedules fails, THEN THE SYSTEM SHALL log the failure
  at ERROR and continue starting the worker, as `_ensure_schedule` does today.
- WHEN `WEEKLY_DISPATCH_TARGETS` is empty, THE SYSTEM SHALL still garbage-collect
  every `dispatch-*-schedule` schedule.

Path validation
- WHEN a `DispatchTarget` is constructed with a `repo` that is not of the form
  `<owner>/<name>` (characters `[A-Za-z0-9_.-]`, no `.` or `..` segment), or a
  `workflow_file` that is not a bare `[A-Za-z0-9_.-]+\.ya?ml` file name, THE
  SYSTEM SHALL raise `ValueError` at import time.
- WHEN `dispatch_and_observe` or `report_dispatch_failure` receives an invalid
  `repo` or `workflow_file`, THE SYSTEM SHALL raise a non-retryable error before
  making any HTTP request.

Alert-issue pagination
- WHEN `report_dispatch_failure` searches for an existing open alert issue, THE
  SYSTEM SHALL follow the GitHub `Link: rel="next"` header until a matching
  issue is found or there are no more pages, up to a fixed page cap.
- IF the page cap is reached and no match was found, THEN THE SYSTEM SHALL raise
  the retryable `AlertIssueSearchUnreadable` and SHALL NOT create a new issue.
  An incomplete listing is never read as "no issue".
- IF any page is non-200 or malformed, THEN THE SYSTEM SHALL handle it exactly
  as the first page is handled today.

Second alert channel
- IF `report_dispatch_failure` fails terminally (all retries used, or the error
  is non-retryable, including `NoGitHubToken`), THEN `ScheduledDispatchWorkflow`
  SHALL emit one ERROR-level workflow log line with the stable marker
  `scheduled_dispatch_alert_undelivered`, plus the repo, workflow file,
  workflow id, original error type and report error. It SHALL then re-raise the
  original dispatch error.
- THE SYSTEM SHALL increment a worker metric counter
  `scheduled_dispatch_alert_undelivered` (labels: `repo`, `workflow_file`) on
  the same path, so the failure can be alerted on without any GitHub
  credential.

## Out of scope

- Converging actions of the non-dispatch schedules (reconcile, issue-poll,
  incidents, implement-sweep). The opt-in flag makes this easy to add later.
- Converging calendar/cron specs, jitter, catchup window or other schedule
  fields not listed above.
- Adding new dispatch targets or changing the portfolio target's cadence.
- Building an mctl-api incident ingestion endpoint or a Telegram notifier. This
  proposal adds only a log marker and a metric that the existing
  log/metrics pipeline can alert on.
- Alertmanager rules in mctl-gitops for the new metric (a follow-up there).

## Open questions

- Second channel: is a metric plus a stable ERROR log line enough, or does the
  author want a push channel such as an mctl-api incident (authenticated with
  `MCTL_TOKEN` via `orchestrator/temporal/mctl_client.py`)? This proposal goes
  with log plus metric because it needs no new external contract. A push
  channel can be layered on later.
- GC deletes undeclared schedules even if an operator paused them. Treating the
  `dispatch-` prefix as owned by code is the reasonable reading, but a reviewer
  should confirm nobody creates `dispatch-*` schedules by hand.
- Page cap for alert-issue pagination: 10 pages x 100 items. Change it if
  needed.
