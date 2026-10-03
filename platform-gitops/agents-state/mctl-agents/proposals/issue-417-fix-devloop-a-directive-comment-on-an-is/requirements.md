# Make a directive comment on an issue a real, answered trigger

## Context

A human who comments `@MCTL Please reinvestigate and rewrite the durable proposal
for this issue` on a GitHub issue gets nothing: no run is scheduled, no durable
state changes, and no reply says so. The issue reads as "waiting on the
investigator" indefinitely. On mctl-agents#395 this burned four hours across two
requests, whose durable proposal
`issue-395-feat-devloop-admit-implementation-work-i/.status.yaml` never moved past
`updated_at: 2026-09-19T15:18:29Z`.

The comment was never a broken trigger — it is an absent one. `orchestrator/run_issue_poller.py`
discovers work only through `search_labeled_issues()`, which runs
`gh search issues --owner mctlhq --label agents:intake --state open` and never reads
comments. The only `issue_comment` handler in `.github/workflows/` is
`claude-review.yml`, the PR reviewer. Grepping this repo for `reinvestigate`,
`@MCTL` or `directive` returns nothing outside an unrelated prompt-hardening
sentence in `run_issue_investigator.py`.

Worse, the documented workaround does not work either. `remove_label()` drops
`agents:intake` after dispatch, so "ask again" means re-labelling — but
`start_dev_loop_workflow()` starts `dev-loop-{owner}-{repo}-{issue}` with
`WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY` and
`WorkflowIDConflictPolicy.USE_EXISTING`. A re-label against a RUNNING loop is a
true no-op; against a SUCCEEDED loop it raises `WorkflowAlreadyStartedError`,
which the poller logs as `OK (already handled)` and then drops the label again.
Both paths end in silence. Asking twice is not a repeatable gesture anywhere in
the current system.

The failure is silent in both directions: nothing runs, and nothing says nothing
ran. This proposal makes the gesture real for one documented verb, and makes every
other shape of the gesture loudly refused instead of ignored.

## User stories

- AS an operator triaging an agent proposal I WANT to comment
  `@MCTL reinvestigate` on the issue SO THAT the investigator rewrites that exact
  proposal without me having to find and run an out-of-band `mctl_trigger_issue`
  dispatch.
- AS an operator I WANT a reply naming the run my comment started SO THAT I have a
  durable handle to follow instead of inferring progress from silence.
- AS an operator who typed the wrong thing I WANT an explicit "not a recognised
  instruction" reply SO THAT I learn the request failed in minutes rather than
  concluding hours later that the investigator is merely slow.
- AS a platform maintainer I WANT a directive that was never picked up to surface
  in the reconcile tick SO THAT a missed request is a reported condition rather
  than an invisible one.
- AS a platform maintainer I WANT one run per request and no unbounded SDK spend
  SO THAT a comment-driven trigger cannot become a quota incident.

## Acceptance criteria (EARS)

Recognition and parsing

- WHEN a comment body contains a line beginning with the mention token `@MCTL`
  THE SYSTEM SHALL parse the remainder of that line against a closed verb
  vocabulary and classify the comment as `recognised`, `unrecognised`, or
  `not-a-directive`.
- WHEN the parsed verb is `reinvestigate` THE SYSTEM SHALL classify the comment as
  a recognised re-investigation directive.
- IF a comment contains the mention token but no supported verb THEN THE SYSTEM
  SHALL classify it as `unrecognised` rather than ignoring it.
- WHILE parsing a directive THE SYSTEM SHALL read only the verb from the closed
  vocabulary and SHALL NOT forward any part of the comment body into an agent
  prompt or a shell argument.
- WHEN the comment author is the platform bot identity THE SYSTEM SHALL classify
  it as `not-a-directive`, so an acknowledgement can never be re-read as a
  request.

Dispatch

- WHEN a recognised `reinvestigate` directive is found on an open issue that
  already owns exactly one `issue-<N>-*` proposal directory whose status is
  overwritable (`proposed`, per `run_issue_investigator._OVERWRITABLE_STATUSES`)
  THE SYSTEM SHALL submit exactly one `mctl-agents-investigate` run bound to that
  proposal's `service` and `slug`.
- WHEN that run is submitted THE SYSTEM SHALL reply on the issue naming the
  returned Argo workflow name, the `service`/`slug` it is bound to, and the
  commenter it answers.
- WHEN the re-investigation writes the proposal THE SYSTEM SHALL record the
  requesting GitHub login and the requesting comment URL in that proposal's
  `.status.yaml`.
- IF the issue owns no `issue-<N>-*` proposal directory THEN THE SYSTEM SHALL
  reply that there is no proposal to rewrite and name the `agents:intake` label as
  the way to create one, and SHALL NOT dispatch.
- IF the issue's proposal is at a status outside `_OVERWRITABLE_STATUSES` THEN THE
  SYSTEM SHALL reply naming that status and SHALL NOT dispatch, so a
  re-investigation never races an implementer that owns the proposal.
- IF `existing_slugs()` resolves more than one proposal directory for the issue
  THEN THE SYSTEM SHALL reply naming the ambiguous directories and SHALL NOT
  dispatch.
- IF the commenter's `authorAssociation` is not one of OWNER, MEMBER or
  COLLABORATOR THEN THE SYSTEM SHALL reply that the directive was not accepted
  from an unprivileged author and SHALL NOT dispatch.

Exactly-once, and the loud absence

- WHILE an acknowledgement for a given comment id already exists on the issue THE
  SYSTEM SHALL treat that directive as handled and SHALL NOT dispatch again,
  however many poll ticks observe it.
- WHEN the same directive text is posted twice as two distinct comments THE SYSTEM
  SHALL produce exactly one run and one reply per comment id.
- WHILE handling a directive THE SYSTEM SHALL NOT add or remove the
  `agents:intake` label, so the comment path has no label side effects and cannot
  perturb the label path.
- WHEN a poll tick would exceed the configured per-tick directive cap THE SYSTEM
  SHALL leave the remaining directives unacknowledged for a later tick and SHALL
  log the number deferred.
- IF a directive is recognised but dispatch fails THEN THE SYSTEM SHALL reply that
  the dispatch failed, SHALL NOT write a handled-acknowledgement for that comment
  id, and SHALL count the directive as a per-issue failure without failing the
  whole tick.
- WHEN the reconcile tick observes a proposal whose issue carries a
  directive-shaped comment newer than the proposal's `.status.yaml` `updated_at`
  and for which no acknowledgement exists THE SYSTEM SHALL report that proposal as
  a stale directive in the tick's result.
- WHILE reporting stale directives THE SYSTEM SHALL NOT dispatch or write anything
  — reconcile stays read-only with respect to this condition.

Operability

- WHEN the directive scan runs in dry-run mode THE SYSTEM SHALL print every
  directive it would act on and SHALL neither submit a run nor post a reply.
- IF the directive scan cannot read an issue's comments THEN THE SYSTEM SHALL log
  the failure for that issue and continue with the rest, exiting the tick
  non-zero only on a global failure.

## Out of scope

- Any verb other than `reinvestigate`. `approve`, `implement`, `cancel`, `retry`
  and friends are deliberately not in the vocabulary; each has its own
  authorization story (`mctl_approve_dev_loop`, `mctl_trigger_implementer`) and
  the unrecognised-verb reply is what keeps them explicitly refused rather than
  half-supported.
- Adding a `reinvestigate` signal to `DevLoopWorkflow`, or otherwise changing the
  approve `wait_condition` in `orchestrator/temporal/workflows/dev_loop.py`. See
  design.md Alternatives — this proposal deliberately leaves a parked loop parked.
- A GitHub Actions `issue_comment` workflow. The pipeline serves fourteen services
  listed in `config/settings.py SERVICES`; a workflow file in this repo covers
  only this repo.
- Changing the label path: `search_labeled_issues()`, `remove_label()` and the
  `agents:intake` semantics are untouched.
- Reconcile acting on a stale directive. It reports; the directive scan dispatches.
- PR comments. This is about issue comments on issues that own proposals.

## Open questions

- `gh issue view --json comments` is already used by `gh_issue_view()` in
  `orchestrator/run_issue_investigator.py` and by
  `context_assembly.collect_issue_comments`, which read `id`, `author.login`,
  `createdAt` and `body`. The authorization criterion above additionally needs
  `authorAssociation` on each comment. If that field is unavailable on the
  comments sub-object in the pinned `gh` version, fall back to a one-call
  membership check per distinct commenter per tick (`gh api
  /orgs/mctlhq/members/{login}`) and cache it for the tick; either way the
  authorization criterion holds and no directive is silently dropped.
- The mention token is written as `@MCTL` here because that is the spelling in
  the issue's evidence. If `@mctl-agents[bot]` is the mention GitHub actually
  renders, accept both — matching is case-insensitive over a fixed set of
  tokens, so adding a spelling is a one-line vocabulary change and not a
  redesign.
- Whether `mctl-agents-investigate` accepts a `slug` parameter today, or whether
  the slug must be re-derived inside the CWFT from `issue_url`. `resolve_slug()`
  already reuses an existing `issue-<N>-*` directory, so re-derivation from
  `issue_url` alone is correct; passing the slug explicitly is a scoping
  belt-and-braces mirroring what `DevLoopWorkflow` does for the implement step
  via `find_proposal_slug`. Proceed with `issue_url` as the required parameter and
  `slug` as an optional one, adding it to the operation only if it is not already
  accepted.
- Per-tick directive cap default. Proceed with 3, matching the spirit of
  `DEFAULT_MAX_ISSUES = 5` — a comment-triggered SDK run is the expensive thing
  being bounded.
