# Tasks: issue-239-fix-dev-loop-keep-shepherd-ownership-for

- [ ] 1. Extract `_shepherd_tick`/`_drain_tick`/`_settle_tick` out of
      `orchestrator/temporal/workflows/dev_loop.py` into a shared
      `orchestrator/temporal/shepherd_tick.py` (parameterized by a caller
      label for log lines), keeping behavior byte-for-byte identical. Update
      `DevLoopWorkflow` to import from the new module. — DoD: `pytest
      tests/test_dev_loop_workflow.py` passes unchanged; no behavior diff
      (verify with `git diff` limited to import/move, not logic).

- [ ] 2. Add `head_sha`, `decision`, `review_attempts` fields to
      `OrphanSignal` (`orchestrator/temporal/activities/orphans.py`), all
      optional with defaults so existing constructions keep working. Extend
      `_sync_detect_orphans` to call `run_shepherd.read_codex_review(pr)` and
      `run_shepherd.decide(pr, codex)` on every non-skipped candidate and
      populate the new fields before appending the signal. — DoD: existing
      `detect_orphans` tests pass; a new test asserts a candidate whose PR is
      `CHANGES_REQUESTED` with a P1 finding gets `decision="address-review"`
      and the finding's data doesn't leak into `OrphanSignal` itself (only
      the decision name + head_sha + attempts).

- [ ] 3. Add a `shepherd_in_loop`-aware ownership check: extend
      `VisibilityActivities` (`orchestrator/temporal/activities/visibility.py`)
      with a method that, given the `Running` `DevLoopWorkflow` ids from
      `list_active_dev_loop_ids`, queries each one's `shepherd_in_loop` via
      the Temporal client and returns only the subset answering `True`. Wire
      `detect_orphans`'s `active_workflow_ids` comparison to use that
      narrowed set instead of the raw `Running` list. Fail-open on any query
      error (treat as not-confirmed-owned) per the existing pattern in
      `run_shepherd._dev_loop_owns`. — DoD: a new test simulates a `Running`
      DevLoop whose `shepherd_in_loop` query answers `False`/errors and
      asserts its proposal is still reported as an orphan.

- [ ] 4. Add a small metadata read/write pair to `orchestrator/proposal_state.py`
      for the `last_orphan_tick` block (`{at, head_sha, decision}`) that
      writes via `update_status_file(path, current_status, last_orphan_tick=...)`
      without changing `status`. — DoD: unit test round-trips
      write-then-read and asserts `status`/other fields are untouched by the
      write.

- [ ] 5. (depends on 1, 2, 4) In `ReconcileWorkflow.run`
      (`orchestrator/temporal/workflows/reconcile.py`), after
      `detect_orphans`: drop signals with `decision in (None, "wait")`;
      for the rest, skip if `last_orphan_tick.head_sha == signal.head_sha and
      last_orphan_tick.decision == signal.decision` and the cool-down
      (`ORPHAN_TICK_COOLDOWN`, new named constant) hasn't elapsed since
      `last_orphan_tick.at`; otherwise submit via the shared tick helper from
      task 1, bounded by a small concurrency cap (e.g. 4 concurrent tasks),
      settling/draining them before the workflow returns exactly like
      `_watch_pr`/`_settle_tick` do today. On successful submission, write
      `last_orphan_tick`. — DoD: new `ReconcileWorkflow` test asserts (a) a
      `"wait"` orphan gets no tick, (b) an `"address-review"` orphan not
      previously ticked gets one, (c) the same orphan on the next simulated
      cycle with an unchanged head/decision inside the cool-down window gets
      none, (d) a head-SHA change re-ticks immediately regardless of
      cool-down.

- [ ] 6. Extend log lines: `detect_orphans`'s existing `ORPHAN ...` line
      gains `head_sha=... decision=... attempts=...`; add a
      `RECONCILE_TICK service=... slug=... decision=... head_sha=...
      attempt=... submitted=<bool>` line in `ReconcileWorkflow`/the shared
      tick helper. — DoD: grep for both prefixes in a captured test/log run;
      no change to log format of unrelated lines.

- [ ] 7. Update `docs/adr/006-dev-loop-merge-deploy-monitor.md` (or add a
      short addendum) and `docs/agent-inventory.yaml`'s `shepherd-reconcile`
      entry to state the fallback is implemented (not just planned) and
      describe where the ownership-skip logic now lives for the Temporal
      path. — DoD: docs reference the actual module/function names used
      above, no dangling "becomes:" future-tense language for this specific
      piece.

## Tests

- [ ] T1. Unit: `decide()`/`read_codex_review()` called from
      `_sync_detect_orphans` for a `CHANGES_REQUESTED`-with-P1-finding PR
      returns `decision="address-review"` on the `OrphanSignal` (task 2).
- [ ] T2. Unit: a mergeable, clean, green, settled PR with no active owner
      returns `decision="merge"` on the `OrphanSignal` (task 2).
- [ ] T3. Unit: ownership — `Running` DevLoop with `shepherd_in_loop=False`
      does not suppress an orphan signal; `Running` with `True` does (task 3).
- [ ] T4. Unit: `last_orphan_tick` read/write preserves unrelated
      `.status.yaml` fields and does not change `status` (task 4).
- [ ] T5. Workflow: `ReconcileWorkflow` end-to-end with fake activities —
      first cycle ticks an `address-review` orphan; second cycle, same head
      SHA and decision, inside cool-down, does not re-tick; third cycle,
      head SHA changed (simulating the fix push), ticks again (task 5).
- [ ] T6. Workflow: `ReconcileWorkflow` never ticks a proposal whose
      `review_attempts >= MAX_REVIEW_ATTEMPTS` (already `review-stuck` by the
      time `decide()` would run, or flips to it on the tick's own next read)
      — asserts no infinite fallback loop past the cap.
- [ ] T7. End-to-end scenario (mirrors PR #234): direct-implementer-created
      PR (no DevLoop) -> `CHANGES_REQUESTED` -> fallback tick fixes it ->
      fresh `CHANGES_REQUESTED` on the new head -> a second fallback tick is
      scheduled and fixes it (or exhausts `MAX_REVIEW_ATTEMPTS` and lands in
      `review-stuck`) -> merge once clean. Exercise via
      `tests/test_reconcile_workflow.py` plus existing `tests/test_run_shepherd.py`
      fixtures for the `process_one`/`decide()` half.
- [ ] T8. Regression: existing `tests/test_dev_loop_workflow.py` shepherd-tick
      tests pass unchanged after the extraction in task 1.

## Rollback

- Every change is additive to existing modules and confined to
  `orchestrator/temporal/{workflows/reconcile.py,activities/orphans.py,
  activities/visibility.py,shepherd_tick.py}` plus
  `orchestrator/proposal_state.py`'s new helper — no changes to `decide()`,
  `MAX_REVIEW_ATTEMPTS`, `process_one`, or any status value's meaning.
- If fallback ticks misbehave in production (e.g. mis-triggering merges or
  spinning), the safest immediate rollback is reverting the
  `ReconcileWorkflow` change from task 5 only (step 5 in design.md) — this
  drops `ReconcileWorkflow` back to detection-only (today's deployed
  behavior), leaving `DevLoopWorkflow`'s in-loop ticking completely
  unaffected, since that code path never calls the new shared helper's
  fallback caller.
- Tasks 1, 3, 4 are safe to leave in place even if task 5 is rolled back
  (pure refactor / additive read-write helpers / a stricter-but-unused
  ownership check) — no need to revert the whole stack to undo the
  behavioral change.
- `.status.yaml`'s `last_orphan_tick` field is inert to every other
  consumer (`run_shepherd.py`, `run_implementer.py`, the implementer's own
  status writes) since none of them read or clear it; no data migration is
  needed to remove it if the feature is reverted.

## Corrected implementation tasks (authoritative)

- [ ] C1. Implement deterministic-ID `FallbackReviewWorkflow` with durable cooldown, one in-flight shepherd tick and bounded activity retries.
- [ ] C2. Reconcile starts/adopts C1 idempotently; WorkflowAlreadyStarted is success; Schedule overlap policy is explicit `SKIP`.
- [ ] C3. Keep all filesystem/GitHub/status/CWFT work in activities. Remove tasks 4-5's direct workflow-side `last_orphan_tick` read/write.
- [ ] C4. DevLoop cancels/awaits fallback before `shepherd_in_loop=True`; fallback checks live DevLoop ownership before every tick.
- [ ] C5. Return typed submit outcome; transient submit failure advances no cooldown and consumes no review attempt.
- [ ] C6. Test duplicate reconcile starts, replay/retry, takeover races, failed submit, current-head revalidation, second review-fix cycle and `MAX_REVIEW_ATTEMPTS` terminal behavior.

## P1 follow-up tasks (authoritative)

- [ ] P1. Persist a deterministic per-cycle tick ID and propagate it through mctl-api to the Argo workflow name/idempotency key; treat `AlreadyExists` as adoption.
- [ ] P2. Classify submission errors and add a separately bounded deterministic `submission_failures` budget ending in `review-stuck`; keep transient retries bounded by Temporal retry/backoff and outside `review_attempts`.
- [ ] P3. Implement takeover as a drain barrier for any submitted external Argo tick; DevLoop publishes ownership only after terminal cancellation/completion is observed.
- [ ] P4. Test response loss after successful create, `AlreadyExists` adoption, deterministic failure-budget exhaustion, and takeover while an external tick is running. Assert one Argo workflow and no overlapping status writers.

## Cancellation-race task correction

- [ ] P5. Make takeover await the submission activity's terminal outcome before checking the deterministic Argo ID; then adopt/drain any discovered run before acknowledging handoff.
- [ ] P6. Add race tests for cancellation before send, while the create request is in flight, after create with lost response, and after activity completion. Assert DevLoop never starts while a late-created fallback run can mutate state.

## Arbiter and terminal-writer tasks

- [ ] P7. Implement a durable proposal-scoped ownership arbiter with monotonic epochs; DevLoop claims `takeover_pending` before fallback lookup, and Reconcile/fallback require a current grant before start and immediately before remote create.
- [ ] P8. Add an idempotent mutex-protected GitOps status activity for submission-budget exhaustion so `review-stuck` persists even when no CWFT was created.
- [ ] P9. Test reconcile-start between DevLoop lookup and ownership publication, stale-epoch submission, duplicate terminal writes, and process restart after the terminal GitOps commit.

## Claim recovery and CAS tasks

- [ ] P10. Bind takeover claims to exact DevLoop workflow/run IDs; release in cleanup and reclaim only after an activity confirms that owner run is terminal. Fail closed on visibility/query errors.
- [ ] P11. Fence the terminal status activity with expected status, exact head SHA, ownership epoch, and open/unmerged state under the repository mutex; mismatches are auditable no-ops.
- [ ] P12. Test failed/cancelled/terminated DevLoop recovery, visibility outage, manual merge during retries, head change, status change, stale epoch, and duplicate CAS submission.

## Repair and transient-recovery tasks

- [ ] P13. Make terminal projection provisional, revalidate GitHub after commit, and issue an idempotent compensating GitOps commit on head/open/merged mismatch; Reconcile always projects newer external state over stale failure evidence.
- [ ] P14. After transient activity-retry exhaustion, retain the logical tick and counters, wait on durable exponential backoff, and retry. Cap `transient_outage_windows`; terminal exhaustion uses the fenced status path without incrementing `review_attempts`.
- [ ] P15. Test push/merge before commit, between commit and revalidation, and after revalidation; test worker restart and continue-as-new during transient backoff, eventual recovery, and outage-budget exhaustion.
