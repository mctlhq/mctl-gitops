# Restart a Failed DevLoop run whose implementer provably produced no commits

## Context

`POST /api/v1/agents/dev-loop/start` and `mctl_trigger_issue(use_temporal=true)`
go through `startDevLoop` in `internal/api/handlers_dev_loop.go`. When the
issue's DevLoopWorkflow already has a closed run, `restartIfAbandoned`
(mctl-api#640) starts a new run only if that run is `Completed`, its result
says `ended: "abandoned: ..."` and its `implement` is null. Every other closed
status, `Failed` included, is reported `already_exists` without reading
anything. Because the legacy approver relay is off (mctl-gitops#1913) and a
standalone approve carries no grant, a running DevLoop is the only way to
implement a proposal. So an implementer that fails with `no-commits` closes
the issue to DevLoop for good. The concrete case is
`dev-loop-mctlhq-mctl-agents-746`: the implementer
`mctl-agents-implement-70aeec81` ended `deterministic_failure` /
`no_commits` / `head_sha: null`, the workflow is `Failed`, and a new trigger
returns `already_exists`.

The issue asks for the single-issue route to also restart a `Failed` run
when the authoritative implementer completion record proves the implementer
left nothing behind (`outcome: deterministic_failure`,
`stop_reason: no_commits`, `head_sha: null`). The outcome is reported as
`restarted_after_failure` with the failed run as `previous_run_id`. The rule
that refuses to restart after implement exists because a PR is left behind.
That reason does not hold when no commit was ever made. Any evidence that is
missing, unbound to the failed run, or unreadable keeps the old refusal.

## User stories

- AS a platform admin I WANT to re-trigger a DevLoop for an issue whose
  implementer failed without producing any commits SO THAT the amended
  proposal can still be implemented on the issue that carries its audit trail
  and consumed grant, instead of opening a new slice issue.
- AS an auditor I WANT the restart to record both the failed run and the new
  run, plus the evidence it relied on, SO THAT the history of the issue stays
  continuous and every restart can be explained.
- AS a platform operator I WANT a Failed run that may have left a branch or PR
  behind never to be restarted SO THAT a fresh investigate never runs over
  unfinished work it cannot resume.

## Acceptance criteria (EARS)

- WHEN the start route describes an existing execution with status `Failed`
  and a non-empty run id, AND the gitops checkout holds exactly one proposal
  directory `agents-state/<repo>/proposals/issue-<N>-*` whose `.status.yaml`
  has a `completion.authoritative` block with `outcome: deterministic_failure`,
  `stop_reason: no_commits` and an explicitly null `head_sha`, AND the newest
  `implementer` agent execution recorded for the workflow id was created at or
  after the failed run's start time and names the same Argo workflow as
  `completion.run_id`, THE SYSTEM SHALL start a new run on the same workflow
  id. It SHALL respond 202 with `outcome: restarted_after_failure`,
  `started: true`, the new `run_id` and the failed run as `previous_run_id`.
- WHEN a restart after failure succeeds THE SYSTEM SHALL write one
  `dev-loop-start` audit entry with status `succeeded`, parameters
  `outcome=restarted_after_failure` and `previous_run_id`, and a message
  naming the failed run, the new run, the implementer Argo run and the gitops
  revision the completion was read from.
- IF the completion record's `head_sha` is present and not null THEN THE
  SYSTEM SHALL NOT restart. It SHALL report `already_exists` (200) and give the
  reason in the audit entry's not-restarted suffix.
- IF the completion record is missing (no proposal directory, no `completion`
  or `completion.authoritative` block, or no `head_sha` key), or its outcome or
  stop reason is anything other than `deterministic_failure` / `no_commits`,
  THEN THE SYSTEM SHALL NOT restart. It SHALL report `already_exists` with the
  reason recorded.
- IF the newest implementer execution for the workflow id is absent, predates
  the failed run's start time, or names a different Argo workflow than
  `completion.run_id`, THEN THE SYSTEM SHALL NOT restart. It SHALL report
  `already_exists`, recording that the completion record is not bound to the
  failed run.
- IF reading the completion fails (gitops checkout unsynced or unreadable,
  more than one matching proposal directory, a non-regular or symlinked
  `.status.yaml`, undecodable YAML) or listing agent executions fails, THEN
  THE SYSTEM SHALL NOT restart. It SHALL report `failed` (502) with an error
  that names the read failure, because an unreadable completion is not a
  no-commit one.
- IF the gitops reader or the agent registry is not configured THEN THE
  SYSTEM SHALL NOT restart a Failed run. It SHALL report `already_exists`,
  with the reason recorded, which is the behaviour from before this change.
- IF the restart call errors, returns a different workflow id, or returns the
  failed run's own run id THEN THE SYSTEM SHALL report `failed` (502) with
  `previous_run_id` set and SHALL NOT report a restart.
- WHILE the existing execution is `Completed`, THE SYSTEM SHALL keep the
  mctl-api#640 abandon behaviour byte-for-byte, with the same outcomes and
  messages.
- WHILE the existing execution is `Terminated`, `TimedOut`, `Canceled`,
  `ContinuedAsNew` or `Unknown`, THE SYSTEM SHALL report `already_exists`
  without reading any evidence.
- WHILE handling a roadmap wave (`ExecuteRoadmapWave`), THE SYSTEM SHALL NOT
  restart Failed runs. The wave route keeps reporting them `already_exists`.

## Out of scope

- Restarting Failed runs that failed before the implement step (investigator
  failure, approval-path errors). Those have no completion record and stay
  `already_exists`.
- Restarting after a `Failed` implementer that pushed commits
  (`head_sha != null`), after review/merge-watch failures, or after
  `Terminated` / `TimedOut` / `Canceled` runs.
- Any change to the roadmap wave route, to mctl-agents' DevLoopWorkflow, or
  to the format of `.status.yaml` written by mctl-agents.
- Changing Temporal reuse policies for the plain start
  (`StartDevLoopWorkflow` keeps `REJECT_DUPLICATE`).
- Re-using or re-binding the consumed approval grant
  (`aar_90abec5a5c3c4a0b8325cede2b464c4b`). The new run re-investigates and
  needs a fresh human approval.

## Open questions

- The issue speaks of "the authoritative completion record" without naming
  its source. Temporal returns no result for a Failed run, and the clone has
  no Temporal-side carrier for it. The only copy found is
  `completion.authoritative` in the proposal's `.status.yaml` in mctl-gitops
  (verified for issue 746). This proposal reads that file and binds it to the
  run through the agent-registry execution record. If mctl-agents also
  attaches the completion to the workflow failure (ApplicationError details),
  reading it from there would be stronger. Confirm with mctl-agents.
- Should `completion.primary_observed: true` also be required? The proposal
  does not require it, because the issue lists only outcome, stop_reason and
  head_sha.
- Does a `Failed` DevLoopWorkflow release its lifecycle-ownership row and end
  its canonical `we_` execution, as the abandon path does? If not, the new
  run's acquire or its approval could hit a conflict or `execution_ambiguous`.
  The owner-run live acceptance on a throwaway test issue (reaching the
  approval gate and being approvable) is the check; #746 itself is not
  restarted. A failure there needs a follow-up
  in mctl-agents, not in this route.
- Freshness: the completion is read from mctl-api's periodically refreshed
  gitops checkout. A trigger made before the refresh may see no completion and
  report `already_exists`. Retrying after the refresh is the expected remedy.
