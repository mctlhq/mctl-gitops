# DevLoop Part M, M2b-1d-2a: the deadline decision, built inert (first half of the 1d-2 split)

## Context

Issue #1052 carried slice M2b-1d-2 of the sequential plan recorded on #1021 and split in #1046: the merge watch's deadline
exit gets a settle, a final PR read and a decision. The first version of this proposal (digest
`sha256:512664c4d06c709be257ef053f2a94456b943389f157aac8fa73e9aee14c9d24`) was reviewed by two independent read-only
passes on 2026-11-08 and **superseded by this amendment**; its grant `aar_2191c03d35aa4db58a91833004490dac` is not to be
used. The owner ruled "docs-only amend + pre-split":

- **1d-2a (this proposal)** is inert preparation: the decision model and its helpers, covered by focused tests through a
  test-only harness. Nothing in production calls it, so no deadline behaviour changes.
- **1d-2b (a later issue, its own proposal, digest, review, approval and PR)** is the activation: the `while ... else:`
  wiring, both `finally` guards, the `_deliver` guard (the V1/V2 closures, D13 and D18), the gap-harness conversion,
  the replay fixtures, E1-E3 and the wiring mutations. 1d-2a and 1d-2b are never merged with an active unsafe runtime path
  in between: the unsafe path (S1/S2 below) only becomes reachable in 1d-2b, together with its guards.

The specification is the approved #1021 proposal (digest `sha256:e833d2af0ce3ce1e30699e6a77d221ba34af8948175c1ad75f2f0acd566fb144`),
cited as provenance only: #1021 is not restarted and its files are not edited. This proposal is written against main
`55b4633` (the merge of PR #1049, M2b-1d-1).

### The defect the line fixes, and why the pieces must not ship apart

Today `DevLoopWorkflow._watch_pr` (`orchestrator/temporal/workflows/dev_loop.py`) ends at the 14-day deadline with no PR
read. After a worker gap that crosses the deadline the watch ends on a stale `OPEN` although the PR merged
(scenario A of `tests/test_merge_watch_worker_gap.py`, #1029). The fix is a decision at the deadline: settle, read,
decide. Verified on main:

- **S1 (deliveries).** `_deliver` lands a still-waiting resume delivery `Succeeded` on any run end where
  `_reconcile_required` is unset, so an interim Failed end would report success to a request.
- **S2 (claim).** `finally` writes `release` for every exit other than a hop, so a cancel arriving during the decision
  would release the claim while the PR state is unknown.
- **S3 (cancel inside a final-read activity).** On `temporalio==1.34.0` a workflow cancel during a running activity
  surfaces as `ActivityError` with a cancelled cause, which a `except ActivityError` counts as a failed attempt (an
  accepted interim limit, pinned in 1d-2b).

Activating the decision without the guards that close S1/S2 would create an unsafe path. 1d-2a therefore adds the
decision but no caller; 1d-2b adds the caller and the guards in the same change.

## User stories

- AS the reviewer of the #1021 line I WANT the deadline decision's reads, ordering, kinds and flag lifecycle pinned in
  isolation, with no production caller, SO THAT the activation slice (1d-2b) is a small wiring change on top of code
  whose behaviour is already pinned. Cancellation surfaces and the settle's `workflow.wait` against a real gate are
  not covered here; they are 1d-2b (D13 family).
- AS an operator I WANT this slice to change no runtime behaviour, SO THAT it can be merged without a replay,
  rollback or release consideration.
- AS a release owner I WANT every pre-change history to replay unchanged and no marker, payload or result field touched,
  SO THAT B4 (#1007) and the release hold are not touched.

## Acceptance criteria (EARS)

### Scope gate

- R0a. IF making the change green needs an edit to **any** existing test or replay fixture THEN the implementer SHALL
  stop and report on #1052 with no workaround. 1d-2a edits no existing test: E1, E2 and E3 (defined in design.md
  section 8) and the gap-harness conversion belong to 1d-2b, because they are caused by activation or by the `MergeWatchResume.gate_ran_head` payload
  field, neither of which is in this slice.
- R0b. IF the work needs any of the following THEN the implementer SHALL stop and report:
  - a call site of the decision helpers in production code (R2);
  - an edit to `_watch_pr`, `_deliver` or the `finally` block of `_watch_pr`;
  - a new field on `MergeWatchResume`, `DevLoopResult`, `_MergeWatchRun` or any serialized payload;
  - a `workflow.patched` marker, or use of the existing one;
  - a record, a caller of `record_merge_watch_reconcile` or `confirm_no_pr`, a record backoff, a heartbeat, a cancellation
    re-raise, `tick_blocked_until`, `_retain_claim`, or `_reconcile_required` being set.
- R0c. IF the slice does not fit one bounded implementer pass THEN the implementer SHALL stop and report. It SHALL NOT
  trim tests to fit.

### Inertness

- R1. THE SYSTEM SHALL contain no production call site of `_decide_watch_end`, `_settle_watch_work`, `_final_pr_read`
  or `_wait_unless_abandoned`, other than the calls those helpers make to each other. A test (D17a) SHALL pin this with
  an AST scan of `dev_loop.py`, and SHALL name 1d-2b as the slice that replaces the pin with an activation pin.
- R2. THE SYSTEM SHALL leave `_watch_pr`, `_deliver` and every other existing method unchanged, with exactly one
  exception: `_record_gate_result` additionally records `self._gate_ran_head` (R9). The new code only adds new
  methods, constants, dataclasses and two instance fields.
- R3. Every existing test, replay suite and fixture SHALL pass unedited. No history changes shape, because the new code
  issues no command from any existing path.

### The decision (reachable only from the test harness in this slice)

The decision is `_decide_watch_end("deadline", watch, service, slug)`, returning `_WatchDecision(kind, last)` with
`kind` one of `final`, `open`, `abandoned`, `unrecorded`.

- R4. WHEN the decision starts THE SYSTEM SHALL first set `self._watch_unrecorded = True` (the interim retention flag,
  an instance field; neither `_reconcile_required` nor `_retain_claim`). It SHALL then settle the in-flight shepherd tick
  and merge gate through `_settle_watch_work`:
  - cancel both;
  - `await workflow.wait(...)` on them, only if at least one was in flight;
  - drain both through `_settle_tick` / `_settle_gate` with the real `watch.poll_index`;
  - set both task references to None.

  Only after that SHALL it issue the first final read.
- R5. WHEN the final read runs THE SYSTEM SHALL call `get_pr_state` at most `FINAL_READ_ATTEMPTS = 3` times, with
  `PR_STATE_TIMEOUT` and `PR_STATE_RETRY_POLICY`, waiting `FINAL_READ_BACKOFF = 2 min` between attempts (the wait ends
  early on abandon). It SHALL apply `_apply_found_state` to the first found state and return it. Any `ActivityError` and
  any `found=False` counts as one failed attempt.
- R6. IF the final read returns MERGED or CLOSED THEN THE SYSTEM SHALL write the lifecycle `terminal` op through
  `_terminal_claim` and return kind `final` with that state.
- R7. IF the final read returns OPEN and no own attempt is unobserved THEN THE SYSTEM SHALL return kind `open` with the
  fresh state. The decision itself writes no `release`; that stays with the caller's `finally` in 1d-2b.
- R8. WHILE an own attempt is unobserved THE SYSTEM SHALL NOT treat a found OPEN as final. An attempt is unobserved if the
  settle found a tick or gate in flight, or if the fresh OPEN head equals a non-empty `_gate_ran_head`. In that case THE
  SYSTEM SHALL wait until `settled_at + GATED_ACTIVITY_TIMEOUT` (the wait ends early on abandon), then run one more
  final-read set.
- R9. WHEN `_record_gate_result` records a result with `ran` True THE SYSTEM SHALL set `self._gate_ran_head` to that
  attempt's head. The field is instance state: it issues no command, and carrying it across a hop is 1d-2b.
- R10. IF the final-read set yields no found state, or yields OPEN while an attempt is still unobserved, THEN THE
  SYSTEM SHALL return kind `unrecorded` and leave `self._watch_unrecorded` True. The decision schedules no write and
  raises nothing: turning `unrecorded` into the interim `Failed` end is 1d-2b.
- R11. WHEN the decision returns `final`, `open` or `abandoned` THE SYSTEM SHALL clear `self._watch_unrecorded` in the same
  step, with no suspension point between the last await and the clear. An exception or a cancel raised anywhere inside
  the decision SHALL leave it True.
- R12. IF `self._abandoned` is observed after the settle, after a final-read attempt that found no MERGED/CLOSED, during
  a backoff, or during the R8 window THEN THE SYSTEM SHALL wake at once, make no further read, and return kind
  `abandoned` with the last observed or fresh state. A final read that returns MERGED/CLOSED under abandon SHALL still
  return `final`. (Whether the future `else:` arm skips the decision when `_abandoned` is already set before it, or maps the
  resulting kind to today's empty `watch_end`, is a wiring question for 1d-2b: the two are equal in commands but not in
  the typed result. See design.md section 3 and section 8.)
- R13. WHILE deciding THE SYSTEM SHALL NOT set `self._reconcile_required`, SHALL NOT schedule
  `record_merge_watch_reconcile` or `confirm_no_pr`, and SHALL NOT use `is_cancelled_exception`. It SHALL add no
  heartbeat, no record backoff and no `_retain_claim`. A cancel arriving during the decision propagates as the SDK
  delivers it; pinning those surfaces is 1d-2b (D13, D13b-d).

### Evidence

- R14. THE SYSTEM SHALL be accompanied by the 1d-2a share of mutation proof (tasks.md task 6): each mutation applied
  locally, shown red with the expected test named, reverted and kept out of the diff. No mutation is claimed red without
  its output.

## Out of scope

- **1d-2b (next, its own issue, proposal and digest):**
  - the `while ... else:` wiring under `watch.terminal_reconcile`, the `watch_end` and `decision_kind` locals, the raise
    of `ApplicationError(type="MergeWatchReconcileUnrecorded", non_retryable=True)` after `finally`;
  - **both** guards in `finally` (the relinquishing write at line 6974 and `_report_claim_abandonment` at line 7045),
    and the `_deliver` guard (V1/V2 closures);
  - `MergeWatchResume.gate_ran_head` and its hop carry;
  - the gap-harness conversion (scenario A, #1029), E1, E2, E3, the two `merge_watch/` replay fixtures with their
    recorder, D13/D13b/D13c/D13d, D18 and the wiring mutations, the activation pin replacing D17a;
  - the V3 pin (accepted undeployed interim: S3).
- **1d-3:** the record, `_reconcile_heartbeat`, record backoff, `_retain_claim`, all cancellation re-raises including
  #1021 mutation (y), setting `_reconcile_required`, the `dev_loop_reconcile_required` fixture.
- **1d-4:** grace-polls and read-error exits, `_no_pr_proven`, `confirm_no_pr`, `tick_blocked_until` with mutations (am)
  and (ao), the `dev_loop_no_pr_confirmed` fixture, T-23.
- Any change to `DevLoopResult`, `orchestrator/temporal/cli.py`, `start.py`, `activities/pr_state.py` or
  `activities/issue_state.py`.
- Any release, deployment, Vault or GitOps rollout, any B4 decision (#1007), #1022, lifting the release hold, undrafting
  #1003, gitops#2394 or mctl-api#934, and starting 1d-3 or 1d-4.

## Open questions

- Q1. **Marker reuse (accepted by the owner for 1d-2b).** 1d-2a uses no marker at all, existing or new. 1d-2b reuses
  `merge-watch-terminal-reconcile`, with replay proof of old histories (owner ruling 2026-11-08). The reasoning is kept in
  design.md section 8 so that 1d-2b's proposal can cite it.
- Q2. **V2 closure pulls one piece of 1d-3 forward (owner confirmed 2026-11-08).** The minimal retention flag
  `_watch_unrecorded` comes forward from 1d-3. 1d-2a introduces the field and pins its lifecycle (set at start, cleared
  by `_settled`, kept on `unrecorded` and on an exception); 1d-2b adds its two readers (`finally`, `_deliver`). The flag is
  not `_reconcile_required` and not `_retain_claim`; 1d-3 replaces it.
- Q3. A delivery refused on the interim end lands `Failed` with an empty refusal, as an abandoned one does (1d-2b). No new
  `delivery-<refusal>` reason is added. Accepted by the owner as interim, until 1d-3; the diagnostic remains an obligation
  of 1d-3 and #1022.
- Q4. **Budget.** The implementer cap (#1025, $20 per the #1051 investigation) was not re-observed. Sizing in design.md
  section 9 is judged against 1d-1 (77 production + 428 test lines in about 29 minutes). 1d-2a is estimated at about
  2 times that in production lines and about 1.3-1.6 times in test lines, and R0c is a hard stop.
- Q5. mctl-api's reader of `DevLoopResult` (`restartIfAbandoned`) reads `Ended` and `Implemented` on Completed runs only
  (`handlers_dev_loop.go:181-203`, read by the independent review). 1d-2a changes no result field.
- Q6. SDK 1.34.0 facts (read from source, not executed): a workflow cancel during a running activity surfaces as
  `ActivityError` with a cancelled cause, except that a `CancelledError` can be re-raised if the activity result is
  already ready in the same activation (`_workflow_instance.py`, `run_activity`). The repo `.venv` has 1.31.0 while
  `uv.lock` pins 1.34.0. 1d-2a pins none of this; 1d-2b does (D13d).
