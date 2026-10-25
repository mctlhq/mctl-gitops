# '@MCTL investigate' starts a DevLoop on an issue that has no proposal

## Context

The directive-comment scan (`orchestrator/run_issue_directive_poller.py`,
`orchestrator/directives.py`, mctl-agents#417) only understands
`@MCTL reinvestigate`, and it only reads comments on issues that already own a
proposal: discovery walks `gitops_state.list_proposal_refs()`. A comment on a
fresh issue is never read, so `@MCTL investigate` on #791 and #796
(2026-10-25) got no reply, and an operator had to start both investigations
through `POST /api/v1/agents/dev-loop/start`. Spikes now routinely produce
follow-up issues, and a comment on the follow-up is the natural way to start
it. Today that comment is ignored, which breaks the module's own rule that
every non-dispatch outcome gets a reply.

This proposal adds a second verb, `investigate`, and a second discovery
source: the repo-wide issue-comments endpoint for every repository in
`config.settings.SERVICES`. An authorized `@MCTL investigate` on an issue with
no proposal and no DevLoop starts the issue's `DevLoopWorkflow` through the
same start helper the label path uses (`orchestrator.temporal.start.
start_dev_loop_workflow`), with the commenter recorded as requester. Every
other outcome gets a reply.

## User stories

- AS a maintainer of an mctlhq repository I WANT to comment `@MCTL investigate`
  on a new issue SO THAT the investigator writes a proposal without an operator
  calling the API.
- AS an operator I WANT investigations started from comments to stay serial,
  one at a time across the platform, SO THAT parallel investigates cannot
  overwrite each other's gitops writes.
- AS a commenter I WANT every `@MCTL` comment to get a reply SO THAT I know
  whether anything started and what to do next.

## Acceptance criteria (EARS)

Recognition
- THE SYSTEM SHALL accept `investigate` as a member of `directives.VERBS`, at
  the start of a line, after any of the existing `MENTION_TOKENS`, using the
  same parsing rules as `reinvestigate`.
- WHEN a directive's verb is not in `VERBS` THE SYSTEM SHALL reply listing both
  supported verbs (`investigate`, `reinvestigate`).

Discovery
- WHEN a scan tick runs THE SYSTEM SHALL list, for every repository in
  `config.settings.SERVICES`, issue comments updated within the lookback window
  using `GET /repos/mctlhq/{repo}/issues/comments?since=<ts>&sort=updated&direction=asc`,
  following every page.
- THE SYSTEM SHALL NOT use the GitHub search API for directive discovery.
- IF any page of a repository's comment listing fails (non-zero `gh` exit,
  unparseable payload) THEN THE SYSTEM SHALL count that repository as a failed
  scan for this tick, act on no directive found only through that repository's
  listing, post no ack, and retry on the next tick.
- WHEN a listed comment belongs to a pull request rather than an issue THE
  SYSTEM SHALL ignore it.
- WHEN an issue found through the repo-wide listing is also reached through the
  existing proposal-driven discovery THE SYSTEM SHALL read and handle its
  comments once per tick.
- WHEN an issue found through the repo-wide listing has a candidate directive
  THE SYSTEM SHALL read the issue's full comment list
  (`read_issue_comments`) before deciding, so that ack and fail markers are
  evaluated against all of the issue's comments.

Authorization
- IF the directive author's `author_association` is not OWNER, MEMBER or
  COLLABORATOR THEN THE SYSTEM SHALL reply unauthorized, with the ack trailer,
  and start nothing.

Dispatch
- WHEN an authorized `investigate` directive is on an issue with no proposal
  directory (no ref in `list_proposal_refs()` for that service and issue number,
  terminal or not) AND the issue's `dev-loop-mctlhq-<repo>-<n>` workflow is
  absent or its latest run is not RUNNING and may be restarted, AND no
  investigation is in flight platform-wide, THE SYSTEM SHALL start the
  DevLoopWorkflow with `start_dev_loop_workflow` (same workflow id, reuse
  policy and conflict policy as the `agents:intake` path), recording the
  commenter's login as `requested_by`, and then reply with the workflow id and
  the ack trailer.
- IF the issue's repository is not in `config.settings.SERVICES` THEN THE
  SYSTEM SHALL start nothing. Such an issue is never discovered.

Concurrency (chosen behaviour: refuse with a retry hint)
- WHILE any running DevLoopWorkflow reports an investigation in flight THE
  SYSTEM SHALL NOT start a DevLoopWorkflow from an `investigate` directive, and
  SHALL reply that another investigation is running and the commenter should
  comment `@MCTL investigate` again once it finishes. This reply carries the
  ack trailer.
- THE SYSTEM SHALL start at most one DevLoopWorkflow from `investigate`
  directives per scan tick.
- IF the in-flight check cannot be completed (visibility listing or a query
  fails) THEN THE SYSTEM SHALL treat the outcome as unknown: start nothing,
  post no ack, and record a failed attempt under the existing
  `MAX_DISPATCH_ATTEMPTS` fail-trailer budget.

Existing proposal or workflow
- WHEN an authorized `investigate` directive is on an issue that already has a
  proposal directory THE SYSTEM SHALL reply naming the proposal
  (`<service>/<slug>`) and its status, point to `@MCTL reinvestigate`, start
  nothing, and ack.
- WHEN an authorized `investigate` directive is on an issue whose DevLoop is
  RUNNING THE SYSTEM SHALL reply naming the workflow id and its state, point to
  `@MCTL reinvestigate`, start nothing, and ack.
- WHEN an authorized `investigate` directive is on an issue whose latest DevLoop
  run COMPLETED (`WorkflowAlreadyStartedError` from the start) THE SYSTEM SHALL
  reply that the issue was already handled, start nothing, and ack.
- IF describing the issue's DevLoop fails for any reason other than not-found
  THEN THE SYSTEM SHALL start nothing, post no ack, and count a failed attempt.

Dedup and failure
- THE SYSTEM SHALL post the ack trailer for a dispatched `investigate` only
  after `start_dev_loop_workflow` returned successfully.
- WHEN a comment id already has a bot-authored ack trailer THE SYSTEM SHALL NOT
  act on it again.
- IF the workflow start fails THEN THE SYSTEM SHALL reuse the existing
  fail-trailer and give-up accounting (`_record_dispatch_failure`,
  `MAX_DISPATCH_ATTEMPTS`).

Unchanged
- THE SYSTEM SHALL keep the `agents:intake` label path
  (`run_issue_poller.poll`) and the `reinvestigate` behaviour unchanged, except
  that `reinvestigate` on a fresh issue now also gets the "no proposal" reply,
  which points to `@MCTL investigate` as well as the label.
- WHILE `MCTL_DIRECTIVE_SCAN_ENABLED=false` THE SYSTEM SHALL perform neither
  discovery pass.

Docs
- THE SYSTEM SHALL document both verbs, the concurrency refusal and the lookback
  window in the README "Directive comments" section.

## Out of scope

- Queuing investigate requests across ticks. The chosen behaviour is refusal
  with a retry hint.
- Gating the `agents:intake` label path or `mctl_trigger_issue` on the new
  platform-wide in-flight check.
- New verbs beyond `investigate` (`approve`, `implement` and the rest stay
  refused as unrecognised).
- Wiring `requested_by` through the `mctl-agents-investigate` CWFT into
  `.status.yaml`. That needs an mctl-gitops change, as the
  `submit_investigate` docstring already notes.
- A durable `since` cursor. A fixed lookback window is used instead.

## Open questions

- The issue calls "at most one investigate at a time, platform-wide" an
  existing rule, but nothing in this repo enforces it today. The only related
  control is the `mctl-gitops-main-writes` mutex on the CWFT's write step. This
  proposal adds a new `investigate_in_flight` query on `DevLoopWorkflow` and
  applies the check only to directive-started investigations. Whether the
  label path should share the gate is left open.
- Lookback window length. The proposal uses 72h by default
  (`MCTL_DIRECTIVE_LOOKBACK_HOURS`). A directive older than the window, for
  example after a scan outage longer than 72h, is not seen.
- Does mctl-api's `POST /api/v1/agents/dev-loop/start` record the requester in
  a specific place (memo, WorkItem, audit row)? The worker cannot read
  mctl-api's code from this clone. The proposal records `requested_by` on
  `IssueRef` and in the Temporal start memo. A reviewer should confirm this
  matches mctl-api.
- A completed-then-abandoned loop: `dev-loop/start` restarts it via
  `restart_if_restartable`. This proposal does not, for the same reason the
  intake poller does not (an abandon should not be undone by a stray comment).
  It replies instead.
