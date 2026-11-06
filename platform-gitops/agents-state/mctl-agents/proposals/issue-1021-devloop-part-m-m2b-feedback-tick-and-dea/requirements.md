# DevLoop Part M, slice M2b: final PR read at the merge-watch deadline, plus the feedback tick (switch OFF)

## Context

Issue mctlhq/mctl-agents#1021 is an execution slice of the approved #993 architecture. It is not a replacement
proposal. The approved umbrella digest `sha256:1e461962bc774bc5ed7f129c6a78378720a79beb97e601d2ca26985d3109742b`
is recorded here as provenance only. This proposal needs its own digest and its own human approval. It does not
recover or restart the failed #993 DevLoop, and it does not touch the umbrella's files or `.status.yaml`.

The slice has two parts.

**Deadline-in-gap.** This part is first and is a mandatory acceptance gate. It is a new owner requirement dated
2026-11-06, and the umbrella does not contain it. Today `DevLoopWorkflow._watch_pr`
(`orchestrator/temporal/workflows/dev_loop.py`) loops on `while workflow.now() < deadline and not self._abandoned`.
Suppose the worker is down while the PR merges, and the absolute deadline passes before the worker returns. The
pending `workflow.sleep(cadence.poll_interval)` timer then fires after the deadline. The loop condition is false,
the loop exits without another `get_pr_state` read, and the `finally` block releases the lifecycle claim. The
result carries the last observed OPEN, so a merged PR is reported open. Deploy observation and the
security-landed record, both keyed on `pr_state.merged` in `_finish_after_watch`, are silently lost.

**Feedback tick, from umbrella tasks 5, 6 and 7.** This part adds three things:
- the `read_rollout_switches` activity, reading `DEVLOOP_DEFERRED_FEEDBACK` only;
- the feedback tick in `_deliver` / `_watch_pr`, with `_feedback_authority_valid()`, dedupe through
  `_feedback_done`, and a typed landing;
- `run_shepherd --feedback-intent`, which emits `feedback_outcome`.

The switch stays OFF. The validator's `feedback-not-ready` deferral, owned by umbrella task 4 and slice M2c, is not
changed. This proposal therefore states exactly how the tick is reached in tests without the accept path. It also
records the portion of T6 that cannot be proven without that path as STOPPED.

## User stories

- AS a platform operator I WANT a merge watch whose deadline expired during a worker outage to read the PR once more
  before it ends SO THAT a merge that happened during the outage is never reported as OPEN, and its deploy
  observation is never skipped.
- AS a platform operator I WANT a watch whose final read fails to end in an explicit reconciliation-required state
  SO THAT unknown is never reported as open, closed or success.
- AS a DevLoop maintainer I WANT the new read behind its own patch marker, decided once and carried across
  continue-as-new, SO THAT every history recorded before this change replays unchanged.
- AS the owner of #993 I WANT the feedback tick built, tested and dark (switch OFF, validator unchanged) SO THAT M2c
  can later open the accept path onto code that is already proven.
- AS a reviewer I WANT every behaviour proven by a test committed before its code, with mutation and replay evidence,
  SO THAT the commit order itself is the evidence (#1013 lacked this).

## Acceptance criteria (EARS)

### Deadline-in-gap (D)

- D1. WHEN `_watch_pr` leaves its poll loop because `workflow.now() >= deadline` (not abandoned, not hopping, not
  the #516 terminal-status break) in an execution that recorded `MERGE_WATCH_FINAL_READ_PATCH`, THE SYSTEM SHALL
  read the PR with `get_pr_state` before the watch ends. This holds however far past the deadline the loop woke.
- D2. WHEN that final read returns a found MERGED PR, THE SYSTEM SHALL take the ordinary merged path:
  - the lifecycle `terminal` write;
  - `_WatchOutcome(last=<fresh state>)`;
  - deploy observation, the security-landed record and the incident watch in `_finish_after_watch`, exactly as
    for a MERGED state observed inside the loop.
- D3. WHEN the final read returns a found CLOSED PR, THE SYSTEM SHALL report CLOSED with the `terminal` write. WHEN
  it returns a found OPEN PR, THE SYSTEM SHALL report that freshly read OPEN state with the `release` write.
  `DevLoopResult.watch_end` SHALL be `final-read` in both cases.
- D4. IF the final read cannot produce a found PR state within `FINAL_READ_ATTEMPTS` attempts, THEN THE SYSTEM SHALL
  end the watch in the explicit state `reconcile-required`. Each attempt is one `get_pr_state` activity under
  `PR_STATE_RETRY_POLICY`, separated by `FINAL_READ_BACKOFF`. An attempt fails on an `ActivityError` of any kind or
  on `found=False`. In that state:
  - `DevLoopResult.watch_end == "reconcile-required"`;
  - `DevLoopResult.outcome == "merge_watch_reconcile_required"`;
  - `ended` is non-empty;
  - `pr` is None and `last_observed_pr` carries the last observed state;
  - deploy observation does not run;
  - a `MERGE_WATCH_RECONCILE_REQUIRED` log line is emitted.
- D5. WHILE the watch is ending on the deadline THE SYSTEM SHALL NOT end on the last observed OPEN without a final
  read. A failed read SHALL never be reported as OPEN, CLOSED or success.
- D6. WHILE the gap lasts THE SYSTEM SHALL keep the absolute deadline unchanged. The deadline is neither extended nor
  recomputed. The final read's own bound (D4) runs after the deadline and is not added to it.
- D7. WHEN a continue-as-new hop occurs THE SYSTEM SHALL carry the absolute `deadline` and the final-read decision
  (`MergeWatchResume.final_read`). A gap that straddles a hop, including a continued run that starts after the
  deadline has already passed, SHALL behave exactly as the same gap without a hop.
- D8. WHERE a history was recorded before this change, THE SYSTEM SHALL replay it unchanged:
  - no new command;
  - `final_read` defaults to False on a pre-change `MergeWatchResume`;
  - `_resume_merge_watch` and the resume arm of `_watch_pr` SHALL NOT call `workflow.patched` for this marker.
- D9. WHILE the final read is undecided THE SYSTEM SHALL keep the lifecycle-ownership claim. The relinquishing
  `terminal` or `release` write happens only after the final read has decided the outcome. In the
  `reconcile-required` case the write is `release`, with the reason
  `merge watch deadline: pull-request state unreadable, reconciliation required`.
- D10. WHEN a final-read activity task is redelivered, or the workflow is replayed, THE SYSTEM SHALL produce no
  duplicate effect:
  - at most one terminal or release write per watch end;
  - one deploy observation;
  - one security-landed record.

### Rollout switch (T5)

- T5-R1. THE SYSTEM SHALL provide a short activity `read_rollout_switches`, registered in the main worker's
  `short_activities`. It returns `RolloutSwitches(deferred_feedback: bool = False)`, which is true only for an
  explicit `DEVLOOP_DEFERRED_FEEDBACK` value in `{"1", "true", "yes", "on"}` (case-insensitive, trimmed).
- T5-R2. IF the variable is unset, empty, malformed or unknown, or the activity fails, THEN THE SYSTEM SHALL treat
  the switch as off. The activity never raises, and the workflow maps an `ActivityError` to off. The scheduled
  command sequence SHALL be identical in every case.

### Feedback tick (T6-T8)

- F1. WHEN a delivery with `accepted_after_gates=True` reaches `_deliver` in a loop that recorded
  `DEFERRED_FEEDBACK_PATCH` (carried as `MergeWatchResume.feedback_tick`), THE SYSTEM SHALL decide its feedback
  once. The order is:
  1. If the request id is already in `_pending_feedback`, wait. The decision has already been taken.
  2. If the request id is in `_feedback_done` with no pending phase, land `Failed feedback-unobservable`, with no
     second tick.
  3. Read the switch. If it is not on, land `Failed feedback-disabled`.
  4. If `_feedback_authority_valid()` is false, land `Failed reapproval-required`.
  5. Otherwise append the request id to `_pending_feedback`.
- F2. WHILE the PR is OPEN and `_pending_feedback` is non-empty, `_watch_pr` SHALL start exactly one feedback tick
  per request, under the single-tick rule (never while a cadence tick or another feedback tick is in flight). The
  tick runs outside the cadence budget, and the request id is added to `_feedback_done` BEFORE the tick is
  awaited.
- F3. WHEN the tick finishes THE SYSTEM SHALL land the delivery as follows:

  | Tick result | Landing |
  |---|---|
  | `processed` | `Succeeded` |
  | `scope-expansion` | `Failed scope-expansion` |
  | `failed`, or an `ActivityError` | `Failed feedback-failed` |
  | `unobservable`, a missing or unknown `feedback_outcome`, or a cancelled in-flight tick | `Failed feedback-unobservable` |

  Every Failed landing records a `ResumeRejection`. Nothing other than `processed` SHALL ever land `Succeeded`.
- F4. IF the watch ends (merged, closed, deadline, final read, terminal status, give-up) before a pending request's
  tick has started, THEN THE SYSTEM SHALL land `Failed merged-before-feedback` when the final state is MERGED, and
  `Failed feedback-not-run` otherwise.
- F5. WHEN a delivery is redelivered, the run hops, or the workflow is replayed, THE SYSTEM SHALL run no second tick
  for the same request id. The hop predicate SHALL refuse while a feedback tick is in flight.
- F6. `_feedback_authority_valid()` SHALL be true only when all of the following hold:
  - the flip's `aar_`, approved content digest and approver are present on the loop (recorded at the flip and
    carried across hops);
  - `check_grant_freshness` confirms the recorded digest still matches the live proposal.

  A missing record, a stale digest or an unreadable read SHALL be `reapproval-required`.
- F7. WHILE this slice is in effect THE SYSTEM SHALL keep `_validate_execution_request` deferring
  `feedback-not-ready` for every new post-gates contract resume. No production path SHALL create a delivery with
  `accepted_after_gates=True`.

### Shepherd feedback mode (task 7)

- S1. WHEN `run_shepherd` is invoked with `--feedback-intent <intent_id>` (requires `--service`, `--slug`,
  `--execution-request-id` and `--feedback-actor`, and a work item id), THE SYSTEM SHALL do the following:
  1. Fetch that intent through `WorkItemClient.list_intents`.
  2. Classify it against the approved `requirements.md` / `design.md` as `in-scope` or `scope-expansion`.
  3. Run the existing `--review-feedback` path only for `in-scope`, under the existing lifecycle claim,
     `--match-head-commit` fencing, and review and CI gates.
  4. Emit exactly one `feedback_outcome` in `{processed, scope-expansion, failed, unobservable}`, as a stdout line
     `FEEDBACK_OUTCOME=<value>` and in the file `$FEEDBACK_OUTCOME_PATH` (default `/tmp/feedback_outcome`).
- S2. IF any of the following happens, THEN THE SYSTEM SHALL emit the outcome shown:

  | Condition | `feedback_outcome` |
  |---|---|
  | The intent is missing, redacted (`text_redacted`) or unreadable | `unobservable` |
  | The classifier output is anything other than an exact `in-scope` | `scope-expansion` |
  | The review-feedback run or a fencing check fails | `failed` |
  | An unexpected exception | `failed` |

  It SHALL never emit `processed` unless the review-feedback commit was pushed under fencing.
- S3. WHERE the shepherd CWFT does not yet declare the `feedback_outcome` output (task 8, out of scope),
  `WorkflowResult.feedback_outcome` SHALL be None, and the workflow SHALL land `feedback-unobservable`.

## Out of scope

- Task 8, the sibling mctl-gitops CWFT PR (`intent_id`, `feedback_actor`, the `feedback_outcome` output). Merging it
  is a live change and needs its own approval.
- Task 4 (validator accept path; M2c) and 4b, task 9 and #1005 (M3), tasks 10-11 (M4), tasks 12-16 (M5), Part S
  and #992.
- Any flag activation, release, deployment or production worker change. `DEVLOOP_DEFERRED_FEEDBACK` stays unset on
  `services/admins/mctl-agents-worker`. #1003 stays Draft and the release hold stays ON.
- Changing the in-loop non-transient `get_pr_state` failure path, or the grace-polls give-up path. Both still end
  with the last observed state (see Open questions).
- Any PR merge. A PR, if later authorized, stays blocked for owner approval under the temporary code-owner rule
  (#1020) and is never merged with an admin bypass.

## Open questions

- **T6 delivery leg, STOPPED.** Umbrella T6 includes "a resume with an intent delivered while the loop is in its
  merge watch". With the validator still deferring `feedback-not-ready`, no `accept_execution_request` Update can
  open a post-gates delivery. This slice therefore proves T6-T8 from a real `DevLoopWorkflow` continued run that
  carries `OpenDelivery(accepted_after_gates=True)` in `MergeWatchResume.open_deliveries`. The dispatcher -> Update
  -> fulfil leg of T6 is recorded as STOPPED and left to M2c. Redelivery is still proven through a real Update,
  because the validator returns early for an id already in `_accepted_request_ids`.
- Should `reconcile-required` end the Temporal workflow as Completed with a typed outcome (proposed, which keeps
  `DevLoopResult`), or as Failed?
- Should `pr` be None in `reconcile-required` (proposed; the pointer moves to `last_observed_pr`)? Downstream
  readers that treat `pr is None` as "no PR watched" must also read `watch_end` / `outcome`.
- Should the claim be released (proposed) or left held for the store to derive as dead in `reconcile-required`?
- `_feedback_authority_valid()` re-checks the digest with the existing `check_grant_freshness`. There is no existing
  activity that re-reads the approver's live authority. Is presence of the recorded approver plus a fresh digest
  sufficient for this slice, or must a new authority read be added (fail closed until it exists)?
- The non-transient read-failure path (`_is_transient` false) and the grace-polls give-up path also end on a last
  observed state without a final read. Should a follow-up apply the same `reconcile-required` rule there?
- The exact Argo behaviour when the tick passes parameters the current CWFT does not declare is unverified. It is
  unreachable while the switch is OFF and the validator defers, and task 8 must settle it.
