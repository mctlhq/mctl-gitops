# Directive comments on issues must start a run and always answer

## Context

A human who comments `@MCTL Please reinvestigate and rewrite the durable proposal
for this issue` on a GitHub issue believes a re-investigation is queued. Nothing is.
`orchestrator/run_issue_poller.py` discovers work with a single
`gh search issues --owner mctlhq --label agents:intake` call and removes the label
after dispatch (`remove_label`, line 133); it never reads comments. The only
`issue_comment` handler in `.github/workflows/` is `claude-review.yml`, which is the
PR reviewer. So the gesture is not a broken trigger — it is an absent one. On
mctl-agents#395 two such comments (15:37:00Z, 17:16:56Z) produced no run and no
reply, while `.status.yaml` stayed at `updated_at: 2026-09-19T15:18:29Z` for over
four hours.

Re-investigation itself is already supported: `run_issue_investigator.resolve_slug`
keys a proposal directory on the issue NUMBER and reuses whatever directory exists,
and `investigate()` overwrites a proposal whose status is in
`_OVERWRITABLE_STATUSES = {"proposed"}` (line 189) while carrying forward files the
agent did not rewrite. Only the trigger and the acknowledgement are missing. The
failure is silent in both directions — nothing runs, and nothing says nothing ran —
so the issue reads as "waiting on the investigator" indefinitely. This proposal makes
the gesture real and makes every outcome of it, including every refusal, audible.

## User stories

- AS a maintainer reviewing a `proposed` proposal I WANT to ask for a rewrite by
  commenting a documented directive on the issue SO THAT I get a fresh proposal
  without an out-of-band `mctl_trigger_issue` dispatch or a label round-trip.
- AS a maintainer who posted a directive I WANT a reply naming the run that was
  started SO THAT I have a durable handle instead of inferring progress from silence.
- AS a maintainer whose directive cannot be honoured I WANT an explicit refusal
  naming the reason SO THAT I retry or escalate in minutes rather than hours.
- AS a platform operator I WANT each directive to cost at most one investigator run
  SO THAT a repeated request, a retried poll cycle, or a comment storm cannot
  multiply agent spend.
- AS a platform operator I WANT a directive that never became a run to be surfaced by
  the reconcile tick SO THAT a discovery gap is reported rather than absorbed.

## Acceptance criteria (EARS)

Recognition and authorization

- WHEN a comment on an open issue under `mctlhq` begins with the configured directive
  mention and a recognised verb THE SYSTEM SHALL treat it as a directive request
  identified by that comment's GitHub node id.
- WHEN a comment begins with the directive mention followed by an unrecognised verb
  THE SYSTEM SHALL reply on the issue that it is not a recognised instruction and
  SHALL list the recognised verbs, and SHALL NOT start any run.
- IF a directive-shaped comment's author is a bot (login ending in `[bot]`) THEN THE
  SYSTEM SHALL ignore it entirely and SHALL NOT reply, so the acknowledgement cannot
  trigger itself.
- IF a directive-shaped comment's `authorAssociation` is not one of `OWNER`,
  `MEMBER`, `COLLABORATOR` THEN THE SYSTEM SHALL NOT start a run and SHALL record the
  refusal in the poll log.
- WHILE a comment does not begin with the directive mention THE SYSTEM SHALL ignore
  it, however the mention appears later in its body.

Dispatch

- WHEN an authorized `reinvestigate` directive is recognised on an issue whose durable
  proposal exists at status `proposed` THE SYSTEM SHALL start exactly one
  DevLoopWorkflow bound to that proposal's existing slug, with a workflow id derived
  from the directive comment's id.
- WHEN the same directive comment is observed on a later poll cycle THE SYSTEM SHALL
  NOT start a second run for it.
- WHEN two distinct directive comments are posted on the same issue THE SYSTEM SHALL
  treat each as its own request, and SHALL refuse the second with a reply naming the
  live run IF a run started by the first is still RUNNING.
- WHILE dispatching directives THE SYSTEM SHALL NOT add, remove, or otherwise modify
  any issue label.
- IF the issue has no durable proposal THEN THE SYSTEM SHALL reply that a first
  investigation is started by the `agents:intake` label, and SHALL NOT start a run.
- IF the durable proposal's status is not in
  `run_issue_investigator._OVERWRITABLE_STATUSES` THEN THE SYSTEM SHALL reply naming
  that status and stating that a rewrite would clobber in-flight work, and SHALL NOT
  start a run.
- IF the issue's repository is not in `config.settings.SERVICES` THEN THE SYSTEM SHALL
  reply that the repository is not a known service, and SHALL NOT start a run.
- IF the issue owns more than one proposal directory (`ProposalAmbiguityError`) THEN
  THE SYSTEM SHALL reply naming both directories, and SHALL NOT start a run.

Acknowledgement and provenance

- WHEN a directive produces a run THE SYSTEM SHALL reply on the issue naming the
  workflow id, the service and the slug the run is bound to.
- WHEN any reply is posted in answer to a directive THE SYSTEM SHALL embed that
  directive's comment id in the reply as a machine-readable marker, and SHALL treat
  the presence of such a marker as proof the directive was already answered.
- IF a run was started but its reply could not be posted THEN THE SYSTEM SHALL count
  the directive as failed and SHALL retry the reply on the next cycle without
  starting a second run.
- WHEN a directive-initiated investigation publishes its proposal THE SYSTEM SHALL
  record the requester's login, the directive comment url, and the directive comment
  id in the proposal's `.status.yaml` as an additive block that no existing reader
  interprets.

Bounds and backstop

- WHILE more authorized directives are pending than the configured per-cycle cap THE
  SYSTEM SHALL dispatch at most the cap, SHALL log the remainder, and SHALL leave
  them answerable by a later cycle.
- IF the directive trigger is disabled by configuration THEN THE SYSTEM SHALL skip
  the directive pass entirely and SHALL leave the `agents:intake` label path
  unchanged.
- WHEN the reconcile tick inspects an issue-sourced proposal whose issue carries a
  directive-shaped comment newer than the proposal's `updated_at` and carrying no
  answer marker THE SYSTEM SHALL report it as an unactioned directive in the tick's
  result, without writing anything.
- WHILE a directive pass fails for one issue THE SYSTEM SHALL continue with the
  remaining issues and SHALL NOT fail the poll cycle.

## Out of scope

- A GitHub Actions `issue_comment` workflow installed across the fifteen `SERVICES`
  repositories for sub-minute latency. Considered in design.md and deliberately
  deferred; the 15-minute poll tick matches the existing label path.
- Directive verbs other than `reinvestigate` (no `reimplement`, `abandon`, `status`).
- Directives on pull requests. `claude-review.yml` and pr-steward own PR comments.
- Making `investigate()` able to overwrite a proposal past `proposed`. The refusal
  becomes audible here; the guard itself is unchanged.
- Any change to the `agents:intake` label semantics, to `remove_label`, or to the
  canonical `dev-loop-{owner}-{repo}-{issue}` workflow id used by the label path.
- Teaching mctl-api's `mctl_get_dev_loop` to resolve directive-suffixed workflow ids
  (cross-repo follow-up; recorded as a risk in design.md).

## Open questions

- "Exactly one investigator run bound to that proposal's slug" versus "one run per
  request" leaves the double-post case ambiguous. Interpretation taken: each distinct
  comment is a distinct request and gets its own workflow id, but a request arriving
  while a prior directive run for the same issue is still RUNNING is refused with a
  reply naming the live run, so the spend stays bounded. Tests assert both halves.
- Is `@MCTL` a real GitHub account? If it resolves to an unrelated user, every
  directive notifies a stranger. The mention token is a single constant
  (`DIRECTIVE_MENTION`); if the account is not ours, prefer a non-account token such
  as `/mctl`.
- Should an unauthorized directive get a reply? Replying turns any GitHub user into a
  way to make the bot comment. Default taken: log only, no reply, behind
  `DIRECTIVE_REPLY_TO_UNAUTHORIZED` (default off).
- Cooldown between two accepted directives on the same issue. Default taken: no timed
  cooldown; the "prior run still RUNNING" refusal is the only rate gate, plus the
  per-cycle cap.
- GitHub code search indexes comments with lag, so `gh search --match comments` may
  not see a directive for some minutes. Accepted; the reconcile backstop is what
  reports a directive the search never surfaced.
