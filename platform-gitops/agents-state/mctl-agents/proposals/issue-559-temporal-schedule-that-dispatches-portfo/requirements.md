# Temporal schedule that dispatches portfolio weekly-refresh

## Context

`mctlhq/portfolio`'s `weekly-refresh.yml` produces the weekly Snapshot and org drift report (portfolio#129). It is started only by a GitHub Actions `schedule:` trigger. On Sunday 2026-10-04 that trigger did not fire in either cron slot (`0 5 * * 0` and `0 8 * * 0`). The workflow itself is healthy: manual `workflow_dispatch` runs succeed and the workflow is `active` on `main`. GitHub documents `schedule` as best-effort, and it gives no signal when a slot is dropped. A weekly job that silently does not run is the "could not observe is not the same as observed absent" failure that AGENTS.md forbids.

This proposal moves the **trigger** to the mctl-agents Temporal control plane and leaves the **execution** in GitHub Actions. A new Temporal Schedule, registered in `orchestrator/temporal/worker.py` `setup_schedules()` through `_ensure_schedule`, fires weekly on Sunday at 08:41 UTC. It starts a small, data-driven workflow. That workflow dispatches `weekly-refresh.yml` on `main` and does not count the dispatch as done until a `workflow_dispatch` run has been observed. When a run is not observed, the Temporal workflow fails visibly. It never logs success in that case.

## User stories

- AS a portfolio maintainer I WANT the weekly refresh to start every Sunday even when GitHub drops its cron SO THAT the weekly Snapshot and drift report are never silently missing.
- AS an mctl operator I WANT a skipped or failed weekly dispatch to show up as a failed Temporal workflow SO THAT I learn about it without having to notice that something is absent.
- AS an mctl-agents maintainer I WANT scheduled dispatch targets declared as data (repo, workflow file, ref, weekly fire time) SO THAT a later weekly job is one list entry, not a new workflow class.

## Acceptance criteria (EARS)

- WHEN the worker runs `setup_schedules()` (roles `all` or `control`, per `owns_schedules`) THE SYSTEM SHALL create or converge, through `_ensure_schedule`, one Temporal Schedule per entry in the scheduled-dispatch target list. Portfolio's `weekly-refresh.yml` on `main` shall be the only entry.
- WHEN the portfolio schedule is evaluated THE SYSTEM SHALL fire it once per week, on Sunday at 08:41 UTC.
- WHILE any Temporal schedule is registered THE SYSTEM SHALL keep the existing invariants: no two schedules fire on the same minute (`test_no_two_schedules_fire_on_the_same_minute`), and no schedule fires on an Argo cron minute {0, 15, 30} (`test_no_schedule_lands_on_an_argo_cron_minute`). Both tests shall cover the new schedule.
- WHEN the new schedule is registered THE SYSTEM SHALL declare `overlap=ScheduleOverlapPolicy.SKIP` explicitly, like every other schedule.
- WHEN a scheduled fire starts THE SYSTEM SHALL record a fixed `not_before` timestamp for that fire, once, in workflow code. Every activity attempt for the fire shall reuse it.
- WHEN the dispatch activity starts (on the first attempt and on every retry) THE SYSTEM SHALL list the target workflow's runs with `event=workflow_dispatch` that were created at or after `not_before` minus a fixed clock-skew slack. IF such a run exists THEN THE SYSTEM SHALL treat the fire as satisfied, return that run, and not dispatch again.
- WHEN no run exists for the fire THE SYSTEM SHALL call `POST /repos/{repo}/actions/workflows/{workflow_file}/dispatches` with `{"ref": "<ref>"}`, authenticated with the worker's GitHub App installation token.
- IF the dispatch response is not 2xx THEN THE SYSTEM SHALL raise an error that fails the activity attempt. It shall never return success. A 4xx other than 429 is non-retryable. A 5xx, a 429 or a transport error is retryable.
- WHEN the dispatch returns 2xx THE SYSTEM SHALL poll the runs listing until a matching `workflow_dispatch` run appears, within a bounded observation timeout (default 5 minutes). It shall then return the run's id and html_url.
- IF the runs listing cannot be read (transport error, non-2xx, or malformed body) THEN THE SYSTEM SHALL raise an error. It shall never treat an unreadable listing as "no run" or as success.
- IF no run is observed within the observation timeout after an accepted dispatch THEN THE SYSTEM SHALL raise a non-retryable error that fails the Temporal workflow, so a slow GitHub cannot turn one fire into a second dispatch.
- WHILE one scheduled fire is being handled THE SYSTEM SHALL bound activity retries (maximum 3 attempts). Because every retry runs the pre-dispatch check first, one fire produces at most one accepted dispatch whose run became visible.
- IF no GitHub token is available (both `GITHUB_TOKEN_FILE` and `GITHUB_TOKEN` are empty) THEN THE SYSTEM SHALL fail the activity without making an unauthenticated request, the same refusal the other GitHub-reading activities use.
- WHEN a run is observed THE SYSTEM SHALL log the repo, workflow file, run id and run URL, and return them as the workflow result.

## Out of scope

- Removing the `schedule:` trigger from `portfolio/.github/workflows/weekly-refresh.yml`. That is a separate portfolio change, made after the Temporal schedule has fired successfully once. Until then the GitHub cron stays as a backstop. A double run is harmless: the workflow has a `concurrency` group and upserts the snapshot PR on `fix/weekly-snapshot`.
- Waiting for the dispatched run to complete, or reporting its conclusion. The activity's contract ends at "a run was observed".
- Generalising beyond a weekly `(repo, workflow file, ref, fire time)` target list: no inputs payload, no non-weekly cadences, no multi-ref fan-out.
- Mint or rotation changes to the GitHub App token in mctl-gitops, except where Open question 1 shows a scope gap.

## Open questions

1. **Token scope.** The worker reads its token from `GITHUB_TOKEN_FILE` or `GITHUB_TOKEN` (see `_resolve_token` in `orchestrator/temporal/activities/proposals.py`). `docs/operations/usage-collector.md` says the shared `mctl-agents` App installation token carries `actions:write`. It is not verified in this repo whether that installation covers `mctlhq/portfolio`, or whether the worker's mounted secret is the unscoped token or a narrowed one. Assumption: it is the shared unscoped token and covers the org. If it does not, a separate mctl-gitops change must add `mctlhq/portfolio` / `actions:write` to the worker's token target before the post-deploy acceptance check can pass.
2. **Cadence representation.** The issue describes the target list as `(repo, workflow file, ref, cron)`. `_ensure_schedule._converge_spec` compares and converges only `spec.intervals`, and both minute-collision tests iterate only `spec.intervals`. A cron or calendar spec would therefore never be converged on redeploy and would be invisible to the collision tests. This proposal expresses "Sunday 08:41 UTC" as a `ScheduleIntervalSpec(every=7 days, offset=3 days 8 hours 41 minutes)`. The Unix epoch, 1970-01-01, is a Thursday, so the offset lands on Sunday 08:41 UTC. The target list therefore carries a weekday/hour/minute triple from which the interval is derived, not a cron string. A reviewer who prefers a real cron string would also need to extend `_converge_spec` and the collision tests to cron specs.
3. **Attribution of a run.** The dispatch API returns 204 with no run id, so "the run for this fire" means any `workflow_dispatch` run created at or after `not_before` minus the slack (60 s). A manual dispatch by a human in that window would be taken as this fire's run. That is accepted, because either way the job ran.
4. **Initial pause state.** This proposal ships the schedule unpaused, consistent with implement-sweep's reasoning in `worker.py`, because pausing would reproduce the "never fires" defect. The documented rollback is `temporal schedule pause`.
