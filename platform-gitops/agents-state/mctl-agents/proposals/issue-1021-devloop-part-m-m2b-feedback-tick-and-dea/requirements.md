# DevLoop Part M, slice M2b-1: terminal reconciliation of the merge watch

## Context

Issue mctlhq/mctl-agents#1021 is an execution slice of the approved #993 architecture. It is not a replacement
proposal. The approved umbrella digest `sha256:1e461962bc774bc5ed7f129c6a78378720a79beb97e601d2ca26985d3109742b`
is recorded here as provenance only. This proposal needs its own digest and its own human approval. It does not
recover or restart the failed #993 DevLoop, and it does not touch the umbrella's files or `.status.yaml`.

The directory slug keeps its historical `m2b-feedback-tick-and-dea` name because the slug binds this proposal to its
DevLoop. The slice's content is what this file says, not what the slug says.

**Amendment, owner decisions of 2026-11-06.** The earlier text of this proposal, with digest
`sha256:e0d913dddc0bfe706f011eed7580bf48c6e2849bca6dce70cdb489a5c9e1abe0`, was never approved. The owner decided:

1. The scope expands to terminal-state safety: deadline expiry, grace-polls exhaustion and unrecoverable PR read
   errors. The watch never finalizes from a stale OPEN without reconciliation. Unknown state produces a typed
   reconcile-required, never a false success.
2. M2b is split. This slice, M2b-1, is deadline-in-gap, terminal reconciliation, Temporal replay, continue-as-new,
   tests first and mutation evidence. Umbrella tasks 5-7 and the feedback-tick foundation move to M2b-2, with a
   separate issue, proposal, digest and approval. M2c and M3 stay separate. No investigator runs concurrently.
3. The workflow may end Completed with a typed reconcile-required and `pr=None`, provided the reconciliation is
   durably recorded before the claim is released and the request cannot be silently lost. Completed must not imply
   successful business processing.

**Second amendment, owner decisions of 2026-11-06.** The text with digest
`sha256:bd54c567ed51e42f15bfee2a1376f6b642bc1adc038bb0bfebcf3a7d0e278924` was not approved either. The owner decided:

4. Abandon stays an explicit operator-controlled exception, with no mandatory final read and no delay. The result
   documents that its last observed OPEN is not verified current state (R16).
5. Grace polls distinguish an authoritatively confirmed no-PR outcome from an unknown PR state. Normal no-PR completion
   stays only when absence is proven. Everything else is reconcile-required, fail-closed (R5a).
6. `RECONCILE_RECORD_WAIT` is 24 hours. Retries start every 5 minutes and rise to at most 30 minutes, with claim
   liveness preserved and fail-closed if the record cannot be confirmed (R9, R10).
7. Operational detection and human handling of both end states is a separate pre-release gate, #1022, with no silent
   reliance on logs alone (R17).

**Review corrections of 2026-11-06.** The text with digest
`sha256:f837e0b3ed17b5422d561cc2c06c59c5942919a625c22a87e77acd2b370da4e1` was not approved either. An independent review
against the code found that a final read could run while this loop's own merge attempt was still live, that cancellation
could release the claim with no record, and that several statements about claim liveness, deliveries and restarts were
false. R1a, R5a, R8-R11, R10a, R15 and R16 carry the corrections. The owner's decisions above are unchanged.

Authority checks stay fail-closed and the feedback tick stays OFF. The M2c accept path cannot be enabled without
verified live authority. This slice adds no tick and no switch, and it does not touch the validator.

**The defect.** `DevLoopWorkflow._watch_pr` (`orchestrator/temporal/workflows/dev_loop.py`) has three exits that end
on a last observed state, none of which establishes what the PR is now:

- **Deadline.** The loop runs `while workflow.now() < deadline and not self._abandoned`. If the worker is down while
  the PR merges and the absolute deadline passes before it returns, the pending `workflow.sleep` fires past the
  deadline, the condition is false, and the loop exits with no further read.
- **Grace polls.** After `pr_lookup_grace_polls` consecutive polls without a resolvable PR, the watch returns the last
  state, which may be None, an unresolved reference, or a stale OPEN. `found=False` covers both "no link yet" and "the
  file or PR is gone or unreachable", because GitHub answers unauthorized and missing lookups identically. So it does
  not prove absence, although today's result reads as if it did.
- **Unrecoverable read.** A non-transient `get_pr_state` failure returns the last state.

In each case the `finally` block releases the lifecycle claim and the workflow completes. A merged PR is then
reported as open, or not at all, and deploy observation and the security-landed record, both keyed on
`pr_state.merged` in `_finish_after_watch`, are silently lost.

## User stories

- AS a platform operator I WANT every non-terminal watch exit to establish the PR's current state before the watch
  ends SO THAT a merge is never reported as OPEN and its deploy observation is never skipped.
- AS a platform operator I WANT a watch that cannot establish the state to leave a durable, visible record before it
  lets go of the claim SO THAT unknown is never reported as open, closed or success, and the work is never silently
  lost.
- AS a reader of a DevLoop result I WANT Completed with a reconcile-required outcome to be distinguishable from
  success in every reader SO THAT Completed never implies the work landed.
- AS a DevLoop maintainer I WANT the new behaviour behind its own patch marker, decided once and carried across
  continue-as-new, SO THAT every history recorded before this change replays unchanged.
- AS a reviewer I WANT every behaviour proven by a test committed before its code, with mutation and replay evidence,
  SO THAT the commit order itself is the evidence (#1013 lacked this).

## Acceptance criteria (EARS)

Requirements R1-R15 apply only to an execution whose watch recorded `MERGE_WATCH_RECONCILE_PATCH`, except R12, which
pins the histories that did not.

### Establishing the state

- R1. WHEN `_watch_pr` reaches any of the following exits, THE SYSTEM SHALL run a final PR read before the watch ends:
  - `deadline`: the loop left because `workflow.now() >= deadline`, however far past the deadline it woke;
  - `grace-polls`: `polls_without_pr >= cadence.pr_lookup_grace_polls`;
  - `read-error`: a non-transient `get_pr_state` failure.
- R1a. THE SYSTEM SHALL settle the watch's shepherd tick and merge gate before it decides, because either can merge this
  PR, and cancelling one does not recall a merge already running:
  - on a `deadline` exit, before the final read;
  - on a `grace-polls` or `read-error` exit, as soon as the final read produces no found state, before any proof of
    absence and before any record. A found state on those exits needs no settle here.

  An attempt is *unobserved* if it was still in flight when it was settled, or if a merge-gate attempt reported `ran` for
  the head the read returned. WHILE an attempt is unobserved, a found OPEN or a read with no found state is not final:
  THE SYSTEM SHALL read again once `GATED_ACTIVITY_TIMEOUT` (10 minutes) has passed since the settle, and act on that
  read. IF a `deadline` exit still reads OPEN then, THE SYSTEM SHALL end reconcile-required (R6), because the outcome of
  this loop's own attempt was never observed.
- R2. THE final read SHALL make at most `FINAL_READ_ATTEMPTS` attempts, each one `get_pr_state` activity under
  `PR_STATE_RETRY_POLICY`, separated by `FINAL_READ_BACKOFF`. An attempt fails on an `ActivityError` of any kind or on
  `found=False`. A failed attempt SHALL never be read as OPEN, CLOSED or absent.
- R3. WHEN the final read returns a found MERGED PR, THE SYSTEM SHALL take the ordinary merged path, exactly as for a
  MERGED state observed inside the loop:
  - the lifecycle `terminal` write;
  - deploy observation, the security-landed record and the incident watch in `_finish_after_watch`;
  - `DevLoopResult.watch_end == "final-read"`.
- R4. WHEN the final read returns a found CLOSED PR, THE SYSTEM SHALL report CLOSED with the `terminal` write and
  `watch_end == "final-read"`.
- R5. WHEN the final read returns a found OPEN PR, THE SYSTEM SHALL act by exit:
  - `deadline`: report that freshly read OPEN state with the `release` write and `watch_end == "final-read"`;
  - `grace-polls` or `read-error`: resume the poll loop, with `polls_without_pr` reset to 0, because a resolvable OPEN
    PR before the deadline is not an end. The absolute deadline still bounds the watch.

- R5a. WHEN a `grace-polls` exit's final read returns `found=False` with no recorded PR reference, and no PR has
  resolved earlier in this watch (`saw_open_pr` is false and `last` carries no PR number), THE SYSTEM SHALL run the
  activity `confirm_no_pr`. Absence is proven only when one attempt of that activity observes all of:
  - the proposal's `.status.yaml` answering 200 with `encoding == "base64"` and non-empty content that decodes, a parsed
    `status:` line, and no line that sets a `pr` key in any form (indented, quoted, or with a blank value);
  - every page of `GET /repos/mctlhq/<service>/pulls?head=mctlhq:feat/agents-<slug>&state=all` answering 200 with a
    well-formed list, and no pull request in any of them;
  - `GET /repos/mctlhq/<service>/branches/feat/agents-<slug>` answering 404 after the listing above proved repository
    access. A pushed branch with no PR is undecided, not absent.

  Then THE SYSTEM SHALL end as a normal no-PR completion: `pr` None, `watch_end == "no-pr-confirmed"`, `ended` and
  `outcome` empty, no record, and no deploy observation. Each of the following is unknown, not absence, and SHALL end
  reconcile-required (R6):
  - the status file answering 404, or any non-200, malformed or undecodable answer, or content with no `status:` line;
  - a `pr` key of any shape, including a `pr:` line that names a PR outside the repo or one answering 404;
  - a non-empty listing, a failed or malformed page after earlier pages succeeded, or a missing token;
  - the branch existing, or the branch lookup answering anything other than 200 or 404;
  - a final read with no PR state because every attempt failed;
  - an activity failure, or any PR that resolved earlier in this watch.

  The proof covers the loop's deterministic branch and the recorded link. A PR opened by hand from another branch and
  never linked is outside it, and this limit is stated rather than implied.

### Reconcile-required

- R6. IF the final read produces no found PR state and R5a has not proven absence, THEN THE SYSTEM SHALL end the watch
  as reconcile-required. It
  SHALL durably record the reconciliation (R7) and then release the claim, with this result:
  - `DevLoopResult.watch_end == "reconcile-required"`;
  - `DevLoopResult.outcome == "merge_watch_reconcile_required"`;
  - `DevLoopResult.ended` non-empty, naming the exit, and taking precedence over any abandon that arrived after the
    decision;
  - `DevLoopResult.pr` None, and `DevLoopResult.last_observed_pr` carrying the last observed state, which may be None;
  - `DevLoopResult.reconcile_record` carrying the URL of the record;
  - no deploy observation, security-landed record or incident watch;
  - a `MERGE_WATCH_RECONCILE_REQUIRED` log line naming the repo, the slug, the exit and the record.
- R7. THE durable record SHALL be a comment on the loop's source issue, written by a new activity
  `record_merge_watch_reconcile` before any relinquishing write. It SHALL carry a hidden marker built from the
  workflow id and the watch's absolute deadline, the exit, the last observed PR, and the ids of the deliveries this run
  holds open at that moment. It carries no other data. A request the dispatcher has deferred is not held by this run and
  is not listed; it stays in its own store row and a later claim picks it up.
- R8. THE activity SHALL be idempotent. It lists the issue's comments in full and returns the existing record when the
  marker is present on a comment authored by the writer login `mctl-agents[bot]` or by an owner, member or collaborator.
  Any other comment carrying the marker text, including one from another bot, SHALL be ignored, so a third party cannot
  suppress the record. A failed or malformed page is a failed read, not a shorter list: the activity then raises and
  posts nothing. A 201 answer with no comment URL SHALL raise.
- R9. WHILE the record has not been confirmed THE SYSTEM SHALL keep the lifecycle claim and SHALL keep retrying for at
  most `RECONCILE_RECORD_WAIT` (24 hours). The interval starts at `RECONCILE_RECORD_RETRY_MIN` (5 minutes), doubles
  after each failed attempt, and never exceeds `RECONCILE_RECORD_RETRY_MAX` (30 minutes). An abandon signal that arrives
  after the decision point (R16) SHALL not shorten this wait.

  WHERE this run holds a claim, THE SYSTEM SHALL refresh its liveness with the idempotent `acquire` heartbeat when the
  wait starts and before any sleep once `RECONCILE_LIVENESS_INTERVAL` (90 minutes) has passed since the last refresh, so
  that refreshes land at most about 2 hours apart. A run with no claim, or with `track_ownership=False`, SHALL write no
  heartbeat. A verdict that this run lost the claim to another owner SHALL drop the claim and keep retrying the record.
  Any other unanswered or unknown verdict SHALL be logged and SHALL neither drop the claim nor stop the retries.
- R10. IF the record cannot be confirmed within `RECONCILE_RECORD_WAIT`, or the issue answers 410, or the issue URL
  cannot be parsed, THEN THE SYSTEM SHALL NOT release the claim and SHALL NOT end Completed. It SHALL log
  `MERGE_WATCH_RECONCILE_UNRECORDED` and fail the workflow with a non-retryable `MergeWatchReconcileUnrecorded`, so
  the unknown state is visible as a Failed run. A 404 on the issue is retried like any other failure, because GitHub
  answers unauthorized and missing lookups identically.
- R10a. IF workflow cancellation arrives while the watch is deciding, that is, from the settle or final read to a
  confirmed record, THEN THE SYSTEM SHALL NOT release the claim. It SHALL log `MERGE_WATCH_RECONCILE_UNRECORDED` and let
  the cancellation end the run as Cancelled. A cancelled activity attempt SHALL be re-raised at every new `except
  ActivityError` and at the loop's poll, and SHALL never count as a failed read. Cancellation during ordinary polling
  keeps today's release, and ends the run Cancelled rather than as a `read-error` exit.
- R11. THE SYSTEM SHALL set `_reconcile_required` at the decision point, before the record is attempted, on both end
  states of R6 and R10. FROM then on, a delivery that this run holds open and has not decided SHALL land `Failed` with
  the typed refusal `merge-watch-reconcile-required`, whether it was already waiting or binds during the record wait.
  Its request id SHALL appear in the record if it was held at the first attempt. These stay as they are, and none of
  them lands a new `Succeeded`:
  - a delivery already landed, and a delivery whose decided phase is already pending when the decision point is reached;
  - a delivery that never bound, which closes through the existing `request-not-fulfilled` path;
  - a delivery with `accepted_after_gates`, which keeps `feedback-not-ready` (T-16).

### Replay, continue-as-new and duplicates

- R12. WHERE a history was recorded before this change, THE SYSTEM SHALL replay it unchanged:
  - no new command;
  - `terminal_reconcile` defaults to False on a pre-change `MergeWatchResume`, and that watch keeps today's behaviour
    until it ends;
  - `_resume_merge_watch` and the resume arm of `_watch_pr` SHALL NOT call `workflow.patched` for this marker.
- R13. WHEN a continue-as-new hop occurs THE SYSTEM SHALL carry the absolute `deadline` and the `terminal_reconcile`
  decision. The deadline SHALL be neither extended nor recomputed, and the final read's own bound runs after it. A gap
  that straddles a hop, including a continued run that starts after the deadline has passed, SHALL behave exactly as
  the same gap without a hop.
- R14. WHEN an activity task is redelivered or the workflow is replayed, THE SYSTEM SHALL produce no duplicate effect:
  - at most one terminal or release write per watch end, and none before the final read has decided;
  - one deploy observation and one security-landed record;
  - one record comment.

### Readers

- R15. THE `orchestrator/temporal/cli.py` summary SHALL print reconcile-required with its record, before and instead
  of the existing `not watched` branch that a None `pr` would otherwise reach.

The other readers keep their code, and the implementer SHALL pin each of these statements with a test or cite the code
as evidence:

- `dispatcher._reconcile_closed_loops` only fails non-terminal executions of a closed loop and never writes
  `Succeeded`.
- mctl-api's `restartIfAbandoned` (`internal/api/handlers_dev_loop.go`) reports `already_exists` for a Completed run
  with any non-abandon `ended`, and for a Failed run.
- Intake starts with `ALLOW_DUPLICATE_FAILED_ONLY` (`orchestrator/temporal/start.py:33`). A Completed reconcile-required
  run is treated as handled, and a Failed or Cancelled run may be restarted by a later event.
- The dispatcher starts with `ALLOW_DUPLICATE` (`start.py:42`). A later claim may start a continuation after any closed
  run, reconcile-required included.
- A `_land_delivery` already decided before the watch ended is not changed.

A restart is therefore possible and is not silent loss. A new run re-reads the PR from live state through its own watch,
never inherits the old result, and the record stays on the issue. This slice does not add a dispatcher refusal for
unreconciled runs. See Open questions.

### Abandon and release gate

- R16. WHEN an operator's abandon reaches an exit, or arrives during a final read, before the decision point, THE
  SYSTEM SHALL do no further read, no `confirm_no_pr` and no record, and SHALL add no delay. A backoff or window wait
  SHALL wake on the signal. It keeps today's `release` and `ended="abandoned: ..."`, and the result SHALL state
  `watch_end == "abandoned-unverified"`. This holds at all three exits. The decision point is the moment the final read
  has ended with no found state and absence is not proven. A found MERGED or CLOSED read that arrives with an abandon is
  still reported, because it is a verified state. The `DevLoopResult.pr` docstring and the `cli.py` summary SHALL state
  that on `abandoned-unverified` this `pr` is the last observed state and is not verified current state.
- R17. A release carrying this slice SHALL NOT be cut until #1022 is closed by the owner. This slice implements no
  detector and SHALL NOT present its log lines as operational detection.

## Out of scope

- Umbrella tasks 5, 6 and 7, moved to M2b-2 and not started: `read_rollout_switches`, the feedback tick,
  `_feedback_authority_valid()`, `run_shepherd --feedback-intent`, and the `FlipAuthority` record.
- Task 8 (sibling mctl-gitops CWFT PR), task 4 and 4b (validator accept path; M2c), task 9 and #1005 (M3), tasks 10-11
  (M4), tasks 12-16 (M5), Part S and #992.
- `_validate_execution_request`: it still defers `feedback-not-ready`, and no production path creates a delivery with
  `accepted_after_gates=True`.
- An automated reconciler that acts on the record. This slice records; a human or a later slice acts.
- Operational detection and human handling of reconcile-required and failed-to-record runs. That is the separate
  pre-release gate #1022, whose live changes have their own approval.
- Any flag activation, release, deployment or production worker change. #1003 stays Draft, the release hold stays ON
  and B4 stays FAIL.
- Any PR merge. A PR, if later authorized, stays blocked for owner approval under the temporary code-owner rule
  (#1020) and is never merged with an admin bypass.

## Decisions recorded

- **The #516 terminal-status break is unchanged.** It ends only when no OPEN PR ever resolved and the proposal status
  stayed loop-terminal over `PROPOSAL_TERMINAL_CONFIRM_POLLS` polls, with a typed `ended`. It reports no PR state, so it
  is not a stale OPEN.
- **Record and read share GitHub as a failure domain.** A GitHub outage longer than 24 hours therefore ends in the
  fail-closed Failed run of R10, which #1022 must detect, along with a Cancelled run that holds its claim (R10a).
- **A read is a moment, not a guarantee.** A verified OPEN says what GitHub answered at that moment. A human can still
  merge afterwards. R1a covers only this loop's own in-flight attempts.

## Open questions

1. **Restart of an unreconciled run (owner).** This text keeps today's reuse policies and documents them (R15), pinned by
   T-23 and covered by #1022. The alternative is a dispatcher deferral with a typed reason while the last run is
   unreconciled, which needs cross-run state and widens this slice. Approving this digest accepts the documented
   behaviour.
