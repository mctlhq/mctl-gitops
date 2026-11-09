# DevLoop Part M, slice M2b-1d-2b: wire the merge watch's deadline decision and guard the two Failed-end paths

## Context

Slice 1d-2a (#1052, PR #1053, merge `0536caf`) built the merge watch's deadline decision inert. It added
`_decide_watch_end`, `_settle_watch_work`, `_final_pr_read`, `_wait_unless_abandoned`, `_settled`, `_FinalRead`,
`_WatchDecision`, `FINAL_READ_ATTEMPTS`, `FINAL_READ_BACKOFF`, `MERGE_WATCH_RECONCILE_UNRECORDED`,
`DevLoopWorkflow._watch_unrecorded` and `DevLoopWorkflow._gate_ran_head`
(`orchestrator/temporal/workflows/dev_loop.py`). Nothing in production calls them. Today the deadline exit of
`_watch_pr` (the `while workflow.now() < deadline and not self._abandoned:` loop, line 6854) falls straight into
`finally` and writes `release` on the last state it observed, without reading the PR again. #1029 pins that defect.

Issue #1055 asks for the activation slice declared in section 8 of the 1d-2a design (digest
`sha256:c4fc4f17d5ab389f9c7d209b0cafc2e80cc97d1eb9b67b993f9f365f31a0803c`). The slice has five parts:

- call the decision from a `while ... else:` arm gated on `watch.terminal_reconcile`;
- guard the relinquishing write in `finally` and the delivery decision in `_deliver` with `_watch_unrecorded`, so an
  undecided watch neither releases its claim nor lands a delivery `Succeeded`;
- carry `_gate_ran_head` across continue-as-new;
- reuse the existing marker;
- prove all of it with tests, fixtures and mutations.

This is the step that makes the deadline exit fail closed instead of reporting stale state.

## User stories

- AS the DevLoop owner I WANT the merge watch to read the PR once more at its deadline before it lets go of the claim
  SO THAT a PR that merged during a worker gap is reported MERGED and written `terminal`, not released as open work.
- AS the DevLoop owner I WANT a deadline end whose PR state cannot be established to fail closed (Failed, claim
  retained) SO THAT no release and no delivery `Succeeded` is ever based on a state the loop did not observe.
- AS an operator I WANT an ordinary `abandon` to behave exactly as today SO THAT the restart contract
  (`ABANDONED_ENDED_PREFIX`) and the existing abandon tests are untouched.
- AS a reviewer I WANT every new guard to have a mutation that turns a named test red SO THAT no guard is unfalsifiable.

## Acceptance criteria (EARS)

Wiring (R1-R7)

- R1. WHEN the `_watch_pr` loop condition goes false, AND `watch.terminal_reconcile` is True, AND `self._abandoned` is
  False, THE SYSTEM SHALL call `self._decide_watch_end("deadline", watch, service, slug)` exactly once, from a `while
  ... else:` arm inside the existing `try`.
- R2. IF the decision returns kind `final` THEN THE SYSTEM SHALL return `_WatchOutcome(last=decision.last,
  watch_end=WATCH_END_FINAL_READ)`. `finally` still runs and writes nothing a second time when `_terminal_claim` already
  landed.
- R3. IF the decision returns kind `open` THEN THE SYSTEM SHALL set `watch_end = WATCH_END_FINAL_READ` and fall into
  `finally`, which writes `release` with the fresh head as today.
- R4. IF the decision returns kind `abandoned` THEN THE SYSTEM SHALL set `watch_end = WATCH_END_ABANDONED_UNVERIFIED`
  and fall into `finally`, which writes `release` as today's abandon does.
- R5. IF the decision returns kind `unrecorded` THEN THE SYSTEM SHALL run `finally` without any relinquishing write and
  then raise `ApplicationError("merge watch deadline: pull-request state not established; claim retained",
  type=MERGE_WATCH_RECONCILE_UNRECORDED, non_retryable=True)`. `run`'s existing `except` ends the canonical execution
  and the deliveries and re-raises, so the run ends Failed.
- R6. WHEN the loop condition goes false because of an ordinary operator abandon (`self._abandoned` already True when
  the `else:` arm starts) THE SYSTEM SHALL NOT call the decision. It SHALL schedule no command beyond today's, and it
  SHALL leave `watch_end` at `""` (decision Q-A: keep the guard and map to `""`).
- R7. WHILE `watch.terminal_reconcile` is False THE SYSTEM SHALL make the `else:` arm issue no command, so unpatched
  histories and resume records replay byte-identically.
- R8. THE SYSTEM SHALL return `watch_end` on the final `_WatchOutcome(last=watch.last, ended=watch_ended,
  watch_end=watch_end)`. Every exit other than the deadline (MERGED/CLOSED in-loop, the #516 terminal-status break,
  grace polls, read error, hop) SHALL be unchanged.

`finally` guards (R9-R10)

- R9. IF `self._watch_unrecorded` is True when `finally` reaches the relinquishing block THEN THE SYSTEM SHALL skip the
  `release`/`terminal` write. When `watch.track_ownership` is also set, it SHALL log one warning starting
  `MERGE_WATCH_RECONCILE_UNRECORDED` (repo, workflow id, `exit=deadline`, last state). The guard SHALL become `if not
  hopping and not self._watch_unrecorded and watch.track_ownership and self._owned_entity_id:`.
- R10. THE SYSTEM SHALL keep the `_report_claim_abandonment` guard (`if not hopping and watch.track_ownership:`)
  unchanged, so that a claim whose last relinquishing write already failed is still counted once. The flag does not
  change what that metric counts: an unrecorded end makes no relinquishing attempt.

Delivery guard (R11-R12)

- R11. WHILE `self._watch_unrecorded` is True THE SYSTEM SHALL NOT let `_deliver`'s wait predicate wake on
  `_is_approved()` or `_gates_passed`. The predicate becomes `self._abandoned or self._exiting or self._hopping or
  ((self._is_approved() or self._gates_passed) and not self._watch_unrecorded)`, so that `_settle_deliveries` (which
  sets `_exiting`) still wakes it.
- R12. THE SYSTEM SHALL compute `decided = (self._is_approved() or self._gates_passed) and not self._abandoned and not
  self._watch_unrecorded`. A delivery woken on an unrecorded end then lands `Failed` (closes S1).

Hop carry (R13)

- R13. THE SYSTEM SHALL add `MergeWatchResume.gate_ran_head: str = ""`, fill it from `self._gate_ran_head` in the hop
  record next to `merge_gate_settled_head`, and restore it in `_rehydrate_work_context` next to `self._gate_settled_head
  = resume.merge_gate_settled_head`. A record from before this field SHALL decode as `""` (E2).

Marker (R14-R15)

- R14. THE SYSTEM SHALL add no `workflow.patched` call. The AST count stays at 37, and the decision reuses
  `MERGE_WATCH_RECONCILE_PATCH = "merge-watch-terminal-reconcile"` (owner ruling 2026-11-08).
- R15. WHEN any committed history fixture is replayed THE SYSTEM SHALL replay it unchanged, because no committed fixture
  carries the marker. The two new `tests/fixtures/histories/merge_watch/` fixtures SHALL replay clean.

Scope and STOP conditions (R16-R18)

- R16. THE SYSTEM SHALL NOT schedule `record_merge_watch_reconcile` or `confirm_no_pr`. It SHALL NOT set
  `_reconcile_required = True`, use `is_cancelled_exception`, add `_retain_claim`, `tick_blocked_until`, backoff beyond
  the existing `FINAL_READ_BACKOFF`, a heartbeat, or a cancellation re-raise.
- R17. IF any existing test or replay fixture other than E1, E2, E3, the gap-harness pin and D17a needs editing THEN the
  implementer SHALL stop and report on #1055 with no workaround.
- R18. IF the converted gap-harness assertion cannot be shown red on base `0536caf`, or any listed mutation can be
  neither shown red nor reported equivalent with reasoning and output, THEN the implementer SHALL stop and report.

## Out of scope

- 1d-3: `record_merge_watch_reconcile`, `WATCH_END_RECONCILE_REQUIRED` production use, liveness, heartbeat,
  cancellation re-raise (mutation (y) turns D13d red on purpose there), and #1022 (it blocks any release carrying this
  line).
- 1d-4: the grace-polls and read-error exits, `confirm_no_pr`, `tick_blocked_until`, mutations (am) and (ao).
- Any `DevLoopResult` field change, any mctl-api change, any release, tag or deploy. B4 (#1007) stays FAIL and the
  release hold stays ON.
- Restarting #1021 or editing its files. #1051 stays as evidence. Closing #1029 is the owner's call after verifying D1.

## Open questions

- Q-A (decided here, for the reviewer to confirm): an ordinary operator abandon keeps the guard and maps to `""` (R6).
  The alternative, mapping it to `abandoned-unverified` without a command (the #1051 draft), is in design Alternatives.
  D8 asserts `watch_end == ""` either way, so mutation (v) is killable.
- Q-B: the issue and the 1d-2a design name mutations N1 and N2, but no record I could read (the #1021, #1051 and #1052
  proposals, and the comments on #1052, #1053 and #1021) defines them. This proposal defines them in tasks.md:
  - N1 = return normally instead of raising on `unrecorded`;
  - N2 = clear `_watch_unrecorded` when the decision raises.

  N2 turns D13 red, as the 1d-2a design says it must. The reviewer should confirm these readings.
- Q-C: R10 keeps `_report_claim_abandonment` unchanged. Its mutation (add `not self._watch_unrecorded`) is killable
  only when a claim reaches an unrecorded end with `_claim_abandoned` already True (via a resume record carrying
  `claim_abandoned=True` and `owned_entity_id`). If the implementer cannot build that state through a real resume
  record, it reports the mutation equivalent with reasoning and output, as R18 allows.
- Q-D: existing tests that ride a fresh (patched) run to the deadline now take the final read. Two were checked by
  reading:
  - `test_merge_detection_deadline_returns_last_open_state` (line 4083) should stay green (OPEN, `final-read`) if nothing
    is in flight at the deadline;
  - `test_deadline_is_carried_not_recomputed_across_hops` (line ~7880) gets one more read, within its bound `<= 5`.

  If a shepherd tick or gate is in flight at the deadline in either test, it ends Failed instead. That is a STOP (R17),
  not a test edit. Task 1 checks this before any other work.
