# Report approved proposals whose execution never started, alongside PR orphans

## Context

`detect_orphans` (`orchestrator/temporal/activities/orphans.py`) only reports a
proposal when it has a PR that is still open and no live DevLoopWorkflow. Both
of its code paths (`_sync_detect_orphans` and `_detect_from_github`) `continue`
on `pr is None`. So an `accepted` / `in-progress` proposal that was approved
and never claimed by an implementer, which therefore has no PR, no `attempt:`
block and no live loop, never becomes an `OrphanSignal`. On 2026-09-19 three
approved proposals (`mctl-api#335`, `mctl-gitops#1278`, `mctlhq/.github#99`)
sat in exactly that state for over two hours. Reconcile reported clean the
whole time. Someone found it only by reading `.status.yaml` by hand.

mctl-agents#412 has since added `ImplementSweepWorkflow` and
`find_stranded_accepted` (`orchestrator/temporal/activities/stranded.py`),
which re-submit such proposals. That fixes the recovery half. If the sweep
itself regresses, is paused (its documented rollback), or keeps failing for
one proposal, the condition is silent again, because the reconcile result
still has no field for it. This proposal adds a second, separately named
signal to the orphan detection result: "approved, never started". It reports
proposals that are stuck past an age threshold, so the window between a
normal approval and its claim never trips the check. The existing PR-based
orphan signal stays as it is.

## User stories

- AS a platform operator I WANT the reconcile tick to report approved proposals that no implementer ever picked up SO THAT a broken promotion or sweep path shows up in the durable result and in the logs instead of being found by hand.
- AS an alert or dashboard author I WANT "never started" and "died mid-flight" to have different reason strings and different result fields SO THAT I can route and phrase them differently.
- AS an operator triaging legacy records I WANT the 69+ unapproved legacy `incident-*` proposals kept out of the new signal SO THAT it is not drowned in records that already have their own quarantine report.

## Acceptance criteria (EARS)

- WHEN `detect_orphans` runs with a known active DevLoop set THE SYSTEM SHALL return, in a new `OrphanDetectionResult.never_started` list, one `NeverStartedSignal` for every proposal that meets all of the following:
  - its status is `accepted` or `in-progress`;
  - it records no `pr:`;
  - it has no unexpired `attempt.expires_at`;
  - it is not `unrunnable` and carries no `blocked` marker;
  - it carries an explicit execution authorization (`proposal_state.execution_authorization`);
  - its derived `dev-loop-*` id is not in the active set;
  - its age is at or above the never-started threshold.
- THE SYSTEM SHALL measure a proposal's age from `approval.approved_at`, and fall back to `updated_at` only when `approved_at` is absent or unparseable.
- IF a proposal's age is below the never-started threshold THEN THE SYSTEM SHALL NOT report it as never started.
- IF a candidate proposal has neither a parseable `approved_at` nor a parseable `updated_at` THEN THE SYSTEM SHALL report it as never started, with `age_minutes` set to `None`. A record with no timestamp cannot prove it is fresh, so it is not suppressed.
- THE SYSTEM SHALL read the never-started threshold from the `NEVER_STARTED_THRESHOLD_MINUTES` environment variable, defaulting to 45 minutes. The default must be larger than the implement-sweep grace period (20 minutes) plus one sweep interval (15 minutes), so a healthy sweep always gets a chance to claim a proposal before it is reported.
- Each `NeverStartedSignal` SHALL carry service, slug, status, `approved_at` (or `None`), `age_minutes`, and the reason string `"approved, no PR, no live DevLoopWorkflow: execution never started"`. This string must differ from the existing orphan reason, `"No active DevLoopWorkflow found for open PR proposal"`.
- WHILE the PR-based orphan predicate runs THE SYSTEM SHALL keep its current inputs, outputs and reason string unchanged.
- THE SYSTEM SHALL count accepted/in-progress candidates that are excluded only because they lack execution authorization, and expose that count as `OrphanDetectionResult.never_started_unauthorized`, rather than listing each one.
- IF `detect_orphans` is called without an explicit active-workflow list (`active_workflow_ids is None`, the unpatched replay branch of `ReconcileWorkflow`) THEN THE SYSTEM SHALL return an empty `never_started` list. An unknown active set must not turn every approved proposal into a false "never started" (#151).
- IF the active-DevLoop visibility query fails THEN THE SYSTEM SHALL produce no never-started signals for that tick, and the existing `skipped_reason` SHALL cover both signals.
- WHEN a never-started signal is produced THE SYSTEM SHALL log one WARNING line per signal, prefixed `NEVER_STARTED`, with service, slug, status, approved_at and age_minutes.
- WHEN `ReconcileWorkflow` completes THE SYSTEM SHALL expose the never-started signals on `ReconcileWorkflowResult.orphans.never_started`.
- WHILE results recorded before this change are deserialized THE SYSTEM SHALL accept them: every new field is defaulted.
- THE SYSTEM SHALL produce the same never-started classification from the local-checkout path (`state_dir_path` set) as from the GitHub path, for the same inputs.

## Out of scope

- Acting on never-started proposals (re-submitting the implementer). `ImplementSweepWorkflow` already does that (#412). This proposal only reports.
- Wiring the new signal into an Alertmanager rule, a Telegram notification or a metric. The log line and result field are the integration point. See Open questions.
- Changing which statuses are actionable for the PR-based orphan, or changing `ADR-005`'s orphan definition beyond documenting the second signal.
- Proposals whose `pr:` points at a PR that is foreign or returns 404. They record a PR, so they are not "never started", and their handling stays as it is today.
- Recovery out of `needs-triage` (#300).

## Open questions

- Alert routing: the issue says "so an alert can tell". Nothing in this repo turns a reconcile result or a worker log line into an alert today. This proposal emits a distinct WARNING log prefix and result field. A follow-up has to decide whether to build a Loki-based alert rule in mctl-gitops, a Prometheus counter, or an incident POST to mctl-api.
- Threshold default: 45 minutes is derived from the sweep's 20-minute grace plus its 15-minute interval, plus margin. The issue gives no number, and an operator may want something tighter or looser.
- Whether `in-progress` is still a status anything writes: no `.status.yaml` in gitops carries it today. It is included because the issue names it and `ACTIONABLE_STATUSES` contains it.
