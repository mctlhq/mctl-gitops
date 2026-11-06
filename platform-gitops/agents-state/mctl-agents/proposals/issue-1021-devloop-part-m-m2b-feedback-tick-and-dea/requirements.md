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

Authority checks stay fail-closed and the feedback tick stays OFF. The M2c accept path cannot be enabled without
verified live authority. This slice adds no tick and no switch, and it does not touch the validator.

**The defect.** `DevLoopWorkflow._watch_pr` (`orchestrator/temporal/workflows/dev_loop.py`) has three exits that end
on a last observed state, none of which establishes what the PR is now:

- **Deadline.** The loop runs `while workflow.now() < deadline and not self._abandoned`. If the worker is down while
  the PR merges and the absolute deadline passes before it returns, the pending `workflow.sleep` fires past the
  deadline, the condition is false, and the loop exits with no further read.
- **Grace polls.** After `pr_lookup_grace_polls` consecutive polls without a resolvable PR, the watch returns the last
  state, which may be None, an unresolved reference, or a stale OPEN.
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

### Reconcile-required

- R6. IF the final read produces no found PR state, THEN THE SYSTEM SHALL end the watch as reconcile-required. It
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
  workflow id and the watch's absolute deadline, the exit, the last observed PR, and the ids of the requests open at
  that moment. It carries no other data.
- R8. THE activity SHALL be idempotent. It lists the issue's comments in full and returns the existing record when the
  marker is present on a comment authored by a bot or by an owner, member or collaborator. Any other comment carrying
  the marker text SHALL be ignored, so a third party cannot suppress the record. A failed or malformed page is a failed
  read, not a shorter list: the activity then raises and posts nothing.
- R9. WHILE the record has not been confirmed THE SYSTEM SHALL keep the lifecycle claim and SHALL keep retrying, every
  `RECONCILE_RECORD_RETRY` for at most `RECONCILE_RECORD_WAIT`, refreshing the claim's liveness on its existing
  cadence so that the claim is not reaped during the wait. An abandon signal SHALL not shorten this wait.
- R10. IF the record cannot be confirmed within `RECONCILE_RECORD_WAIT`, or the issue answers 404 or 410, or the
  issue URL cannot be parsed, THEN THE SYSTEM SHALL NOT release the claim and SHALL NOT end Completed. It SHALL log
  `MERGE_WATCH_RECONCILE_UNRECORDED` and fail the workflow with a non-retryable `MergeWatchReconcileUnrecorded`, so
  the unknown state is visible as a Failed run.
- R11. WHEN a watch ends reconcile-required, every delivery still open SHALL land `Failed` with the typed refusal
  `merge-watch-reconcile-required`, or close through the existing `request-not-fulfilled` path if it never bound. None
  SHALL land `Succeeded`. Its request id SHALL appear in the record.

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

The other readers need no change, and the implementer SHALL pin that with tests or cite the code as evidence:

- `dispatcher._reconcile_closed_loops` only fails non-terminal executions of a closed loop and never writes
  `Succeeded`.
- mctl-api's `restartIfAbandoned` (`internal/api/handlers_dev_loop.go`) reports `already_exists` for a Completed run
  with any non-abandon `ended`, and for a Failed run. A reconcile-required run is therefore never silently restarted.
- A `_land_delivery` already decided before the watch ended is not changed.

## Out of scope

- Umbrella tasks 5, 6 and 7, moved to M2b-2 and not started: `read_rollout_switches`, the feedback tick,
  `_feedback_authority_valid()`, `run_shepherd --feedback-intent`, and the `FlipAuthority` record.
- Task 8 (sibling mctl-gitops CWFT PR), task 4 and 4b (validator accept path; M2c), task 9 and #1005 (M3), tasks 10-11
  (M4), tasks 12-16 (M5), Part S and #992.
- `_validate_execution_request`: it still defers `feedback-not-ready`, and no production path creates a delivery with
  `accepted_after_gates=True`.
- An automated reconciler that acts on the record. This slice records; a human or a later slice acts.
- A Promtail metric or alert on `MERGE_WATCH_RECONCILE_REQUIRED`. It would be a live mctl-gitops change with its own
  approval.
- Any flag activation, release, deployment or production worker change. #1003 stays Draft, the release hold stays ON
  and B4 stays FAIL.
- Any PR merge. A PR, if later authorized, stays blocked for owner approval under the temporary code-owner rule
  (#1020) and is never merged with an admin bypass.

## Open questions

- **Abandon, proposed unchanged.** An operator abandon during the watch still ends on the last observed state with
  `ended="abandoned: ..."` and a `release`, with no final read. It is an explicit operator decision and is typed as
  such, but `pr` can be a stale OPEN. Is that carve-out acceptable, or should abandon also take the final read and
  delay the abandon by up to the final read's bound?
- **The #516 terminal-status break, proposed unchanged.** It ends only when no OPEN PR ever resolved and the proposal
  status stayed loop-terminal over `PROPOSAL_TERMINAL_CONFIRM_POLLS` polls, with a typed `ended`. It reports no PR
  state, so it is not a stale OPEN.
- **Grace-polls behaviour change.** A loop whose implementer legitimately produced no PR today ends with `pr=None`
  and nothing else. After this slice it ends reconcile-required with a comment on the source issue. This follows the
  owner's scope decision and is stated so that it is approved knowingly.
- **Bounds.** `RECONCILE_RECORD_WAIT` is proposed at 7 days and `RECONCILE_RECORD_RETRY` at 30 minutes. They cover a
  GitHub outage that also caused the failed read, because record and read share a failure domain.
