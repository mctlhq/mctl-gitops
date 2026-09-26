# End DevLoopWorkflow when its proposal reaches a terminal state

## Context

`DevLoopWorkflow` (`orchestrator/temporal/workflows/dev_loop.py`) ends its
post-implement merge watch on exactly four conditions today: the PR reads
`MERGED` or `CLOSED`, `get_pr_state` fails non-transiently, the PR link stays
unresolvable for `cadence.pr_lookup_grace_polls` consecutive polls, or
`MERGE_WATCH_DEADLINE` (14 days) expires. The proposal's own `status:` in
`.status.yaml` is never read by the workflow. So when the proposal reaches a
state that no machine will advance any further — `review-stuck` (written by
`run_shepherd` once `MAX_REVIEW_ATTEMPTS` is exhausted), or `needs-triage`
(written by `run_implementer._mark_needs_triage`, e.g. `code="no-commits"`) —
the loop keeps running against an open PR for the rest of the fortnight. It
keeps submitting in-loop shepherd ticks (up to `SHEPHERD_TICKS_MAX = 96` Argo
runs, one per 15-minute poll) at a proposal whose status is not even in
`run_shepherd.SHEPHERD_INPUT_STATUSES`, keeps polling GitHub ~1340 times, keeps
hopping through `continue_as_new` (up to `MERGE_WATCH_MAX_HOPS = 16`), and keeps
heartbeating its lifecycle-ownership claim every 8th poll so ADR-010 readers see
a *healthy* `devloop-workflow` owner for a PR nobody is driving — and only a
`dead` owner licenses a takeover.

It also makes the issue un-restartable in practice. `orchestrator/temporal/start.py`
pins `DEV_LOOP_ID_CONFLICT_POLICY = USE_EXISTING` on the id
`dev-loop-mctlhq-{repo}-{issue}`, so a later start attaches to the parked
execution instead of starting anything, and `_validate_execution_request`
refuses a dispatched `start` delivery to a live loop with `loop-active`. The
mctl-api#287 proposal ruled this out of scope precisely because mctl-api holds
no part of this state machine: the terminal-state vocabulary and the decision to
stop live in this repository, in `dev_loop.py`.

## User stories

- AS a platform operator I WANT a DevLoop whose proposal has parked in
  `needs-triage` or `review-stuck` to END, with a result that names why, SO
  THAT I can tell "still working" from "waiting for me" without opening
  Temporal.
- AS a platform operator I WANT no further shepherd ticks or PR polls spent on
  a proposal no machine will advance SO THAT a parked loop costs nothing in
  Argo runs, GitHub quota, worker slots and Temporal history.
- AS the lifecycle-ownership control plane (ADR-010) I WANT the loop to
  relinquish its claim when its proposal goes terminal SO THAT the entity is
  claimable again instead of showing a healthy owner that is achieving nothing.
- AS the execution-request dispatcher I WANT the issue's loop to be CLOSED once
  its proposal is terminal SO THAT a later request starts a continuation
  (`DISPATCH_ID_REUSE_POLICY = ALLOW_DUPLICATE`) instead of being refused
  `loop-active` by a parked execution.

## Acceptance criteria (EARS)

- WHEN the merge watch observes a proposal status in the loop-terminal set
  (`needs-triage`, `review-stuck`, `rejected`, `error`) THE SYSTEM SHALL end
  the merge watch at that poll boundary and complete the workflow normally.
- WHEN the workflow ends for that reason THE SYSTEM SHALL record it in
  `DevLoopResult.ended` as a string naming the observed status (the field
  mctl-agents#420 added for exactly this class of non-pipeline exit), and SHALL
  still carry the last observed `PRState` in `DevLoopResult.pr`.
- WHEN the proposal status is terminal and no PR link has resolved yet THE
  SYSTEM SHALL end at that poll rather than spending the remaining
  `cadence.pr_lookup_grace_polls`.
- WHILE the observed proposal status is terminal THE SYSTEM SHALL schedule no
  further in-loop shepherd tick, no further `get_pr_state` poll, and no further
  `continue_as_new` hop for that watch.
- WHEN the watch ends for this reason THE SYSTEM SHALL run the existing
  `_watch_pr` `finally` block — i.e. settle any in-flight tick and issue the
  relinquishing lifecycle-ownership write — and SHALL NOT take the `hopping`
  path that deliberately keeps the claim.
- WHEN the relinquishing write is issued for a terminal-proposal end THE SYSTEM
  SHALL name the observed proposal status in the write's `reason`, instead of
  the generic "merge watch ended without a terminal pull-request state".
- IF the observed proposal status is `merged` THEN THE SYSTEM SHALL keep
  watching, so that the PR-state arm still drives stages 6.2-6.4 (release and
  deploy observation, incident watch) as it does today.
- IF the proposal status cannot be read (absent, 404, undecodable
  `.status.yaml`) or is not in the loop-terminal set THEN THE SYSTEM SHALL keep
  watching — missing evidence is never terminal, the same rule
  `orchestrator/proposal_identity.py` states for an unreadable status.
- WHILE an execution's history predates the new `workflow.patched` marker THE
  SYSTEM SHALL keep its recorded behaviour (poll to the deadline), so no
  in-flight loop is wedged by a command-sequence change.
- WHEN a merge watch hops via `continue_as_new` THE SYSTEM SHALL carry the
  marker's decision in the resume record, so a continued run behaves exactly
  like the run it replaces.
- WHEN the proposal status is compared against the terminal set THE SYSTEM
  SHALL compare a stripped, case-folded string, as
  `ProposalCandidate.ignorable` already does.

## Out of scope

- Restarting an ended DevLoop. `DEV_LOOP_ID_REUSE_POLICY =
  ALLOW_DUPLICATE_FAILED_ONLY` means a *Completed* loop still refuses a
  re-added intake label with `WorkflowAlreadyStartedError`. Explicit restart is
  mctl-api#404; this proposal only stops the loop from occupying the id
  forever as a RUNNING execution.
- Any change in mctl-api: no change to `/dev-loop/start`'s reporting
  (mctl-api#287 / #408) or to `GET /dev-loop/{id}`. Once the execution
  completes, `shepherd_in_loop` is derived `False` from the status by that
  route, with no query change here.
- Changing what `run_implementer` or `run_shepherd` write. The terminal
  statuses are consumed, never produced, by this change.
- The operator gate out of `needs-triage` (a reviewed GitOps move back to
  `accepted`) stays a human action; nothing here automates it.
- Ending the loop on a terminal status observed *before* the merge watch. The
  implementer's own failure paths already fail the workflow through
  `_implement`'s typed `ApplicationError`s, and a run that reports Succeeded
  reaches the watch's first poll within one poll interval.
- Shortening `MERGE_WATCH_DEADLINE`, changing the shepherd cadence, or
  changing `SHEPHERD_TICKS_MAX`.

## Open questions

- **Is `error` a status anything still writes?** It appears in
  `run_shepherd.RECONCILE_INPUT_STATUSES` but no writer was found in this
  clone. Proceeding with it included in the loop-terminal set: if it is dead
  vocabulary the entry is inert, and if something does write it the loop should
  stop.
- **Complete or fail?** This proposal completes the workflow (a normal
  `DevLoopResult` with `ended` set), matching mctl-agents#420's treatment of
  abandon / closed-issue / expiry. Failing instead would make
  `ALLOW_DUPLICATE_FAILED_ONLY` permit an intake-label restart, but would make
  every `no-commits` run read as a red execution and would overload the signal
  `_implement` reserves for "a layer broke". Recorded, defaulting to complete.
- **`rejected` with a still-open PR.** A `CLOSED` PR already ends the watch, so
  including `rejected` only covers a status write that landed while the PR read
  lags or is unresolvable. Kept in the set (it is terminal in
  `pr_adoption.TERMINAL_STATUSES` and `run_issue_directive_poller`), accepting
  that a hand-edited `rejected` on an open PR now hands the PR back to the cron
  sweeper one watch earlier.
- **Should a terminal end emit a metric or an issue comment?** No
  notification surface is added here; the `ended` string plus the workflow's
  own completion are the signal. Worth revisiting alongside mctl-api#404.
