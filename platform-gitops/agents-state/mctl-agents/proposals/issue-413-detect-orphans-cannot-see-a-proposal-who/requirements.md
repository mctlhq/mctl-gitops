# Report proposals whose execution never started, not only orphans that have a PR

## Context

`orchestrator/temporal/activities/orphans.py` defines an orphan as "an actionable
proposal with a valid GitHub PR that has no matching DevLoopWorkflow running in
Temporal", and both detection paths enforce the PR requirement with the same
early `continue` (`_sync_detect_orphans`, orphans.py:57-60, and
`_detect_from_github`, orphans.py:108-110). `accepted` is in `ACTIONABLE_STATUSES`
(orphans.py:25), so an approved proposal that no implementer ever claimed does
reach the loop — and is then dropped, because `find_pr_for_proposal` /
`fetch_pr_snapshots` return nothing for a proposal that has no `pr:` and no
implementer branch. The sweep therefore covers "execution started and then died"
and is structurally unable to report "execution never started".

On 2026-09-19 `mctl-api#335`, `mctl-gitops#1278` and `mctlhq/.github#99` sat at
`accepted` with no `attempt:` block for over two hours (#412). Every reconcile
tick reported clean, no signal fired, and the condition was found only by reading
`.status.yaml` by hand. Orphan detection is the only thing in the platform that
looks for work that is not progressing, and today it can only see the half of
that problem that already opened a pull request. This proposal adds the missing
half as a second, separately named signal so a consumer can tell "died" from
"never started".

## User stories

- AS a platform operator I WANT the reconcile sweep to report proposals that were
  approved but never picked up SO THAT a regression in the approve-to-implement
  path is visible within one tick instead of being found by hand hours later.
- AS an on-call engineer I WANT "execution never started" and "execution died
  mid-flight" to carry distinct, stable reason slugs SO THAT an alert or a
  log-derived metric can route and count them separately.
- AS a maintainer of `ReconcileWorkflow` I WANT the new signal delivered without
  scheduling a new activity command SO THAT in-flight executions replay cleanly
  and no `*.prepatch.json` history has to be re-recorded.
- AS an operator of a freshly approved proposal I WANT a grace window before a
  proposal is called stalled SO THAT the normal gap between approval and claim
  does not produce a signal on every tick.

## Acceptance criteria (EARS)

- WHEN `detect_orphans` runs with a known active DevLoopWorkflow set and finds a
  proposal whose status is in `{accepted, in-progress}`, that has no open,
  merged or closed PR, that has no matching active DevLoopWorkflow ID, that has
  no unexpired `attempt:` lease, and whose last forward-progress timestamp is
  older than the configured threshold, THE SYSTEM SHALL emit a `StalledSignal`
  for it carrying `service`, `slug`, `status`, the timestamp used, the computed
  age in minutes, and the reason slug `execution-never-started`.
- WHEN `detect_orphans` emits any `StalledSignal`, THE SYSTEM SHALL log one line
  per signal at INFO in the same loop that logs `ORPHAN` today
  (orphans.py:154-162), prefixed `STALLED` and carrying
  `service`, `slug`, `status`, `age_minutes` and `reason`.
- WHEN a proposal in `{accepted, in-progress}` has no PR and no active
  DevLoopWorkflow but carries no parseable progress timestamp at all, THE SYSTEM
  SHALL still report it, with the reason slug
  `execution-never-started-unknown-age` and a null age, rather than dropping it.
- IF a proposal's last forward-progress timestamp is newer than the threshold,
  THEN THE SYSTEM SHALL NOT emit a `StalledSignal` for it.
- IF a proposal carries an `attempt:` block whose `expires_at` is in the future
  and which has no `finished_at`, THEN THE SYSTEM SHALL NOT emit a
  `StalledSignal` for it, because an implementer holds a live claim and has not
  yet had the chance to open a PR.
- IF `detect_orphans` is called without an active DevLoopWorkflow set (the
  `active_workflow_ids is None` case reached by `ReconcileWorkflow`'s unpatched
  replay branch, reconcile.py:170-175), THEN THE SYSTEM SHALL emit no
  `StalledSignal`s, because an unknown active set cannot distinguish a stalled
  proposal from a running one.
- WHILE a proposal has an open PR THE SYSTEM SHALL continue to evaluate it under
  the existing PR-based orphan predicate only, and SHALL NOT emit a
  `StalledSignal` for it.
- WHILE the active-DevLoop visibility query is failing and the tick sets
  `skipped_reason` (reconcile.py:110-122) THE SYSTEM SHALL report an empty
  stalled list, exactly as it already reports an empty orphan list.
- WHEN `ReconcileWorkflow` completes, THE SYSTEM SHALL surface the stalled
  signals on its result alongside the orphans, reachable from
  `ReconcileWorkflowResult` without a new workflow-level field.
- WHEN an `OrphanDetectionResult` recorded before this change is deserialized,
  THE SYSTEM SHALL accept it and treat its stalled list as empty.
- WHEN the change ships, THE SYSTEM SHALL have its new behaviour reflected in
  `docs/adr/005-temporal-reconcile.md` (the orphan definition at lines 127-136),
  `docs/adr/010-lifecycle-ownership-contract.md:48` (the "logged only" row), and
  `docs/temporal-flow.md` plus `docs/diagrams/temporal-flow-schedules.mmd`.

## Out of scope

- Fixing the promotion gap itself. That is #412; this proposal only makes a
  future regression in that path visible.
- Any write, takeover, retry or recovery action. The new signal is reported and
  logged only, the same contract the existing `OrphanSignal` has
  (docs/adr/010-lifecycle-ownership-contract.md:48). Recovery out of
  `needs-triage` is #300.
- Wiring an alert, a Telegram notification or a Prometheus metric. No such
  consumer exists for orphans today; this proposal produces the distinguishable
  signal an alert would need, not the alert.
- Widening the status set beyond `accepted` and `in-progress`. A proposal at
  `implemented` or `review-fixing` with no PR is a different corruption and is
  not addressed here.
- Changing the existing PR-based orphan predicate, its reason string, or its log
  line in any way.
- Changing the lifecycle ownership sweep (`activities/lifecycle_reconcile.py`) or
  the ADR-010 ownership records.

## Open questions

- The threshold value. `MIN_AGE_MINUTES` in `run_incident_responder.py:52` is the
  closest precedent (30 minutes, env-overridable); ADR-010 lines 208-240 require
  a bound to exceed twice the cadence of the thing it measures. The
  approve-to-claim cadence is the `mctl-agents-implement` cron, which lives in
  mctl-gitops and is not readable from this repo. Proceeding with a default of
  60 minutes, overridable via `STALLED_NEVER_STARTED_MINUTES`, which is four
  ticks of the 15-minute reconcile schedule and well under the two hours that
  went unnoticed in #412. An operator can tune it without a code change.
- Which timestamp is authoritative for "last forward progress". `approval.approved_at`
  is present on only 122 of 371 live status files and is written solely by
  `cwft-mctl-agents-approve.yaml`, never by this repo. Proceeding with the first
  parseable of `attempt.finished_at`, `attempt.started_at`,
  `approval.approved_at`, `updated_at` — `updated_at` is written on every status
  write (`orchestrator/proposal_state.py:167-168`) and is currently read by
  nothing, so this becomes its first reader.
- Whether the signal should eventually carry the entity identity used by ADR-010
  ownership records so the two can be correlated. Not required by the issue;
  recorded and deferred.
