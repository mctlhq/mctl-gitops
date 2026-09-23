# Tasks: issue-198-feat-governance-human-approval-checkpoin

- [ ] 1. Surface the pending receipt's metadata through the decision —
  add `expires_at` and `intent_hash` passthrough fields to
  `policy_checkpoint.ApprovalOutcome` and `policy_checkpoint.Decision`,
  and populate them in `action_approvals.MctlApiApprovals.redeem()` on the
  `APPROVAL_PENDING` path (the `ApprovalRecord` is already in hand at
  `action_approvals.py:398`). — DoD: a `Decision` with
  `awaiting_approval` true carries a non-empty `expires_at` and
  `intent_hash`; `policy_checkpoint` still imports nothing from
  `action_approvals` (the existing stdlib-only test passes unchanged).

- [ ] 2. Add `orchestrator/approval_wait.py` (depends on 1) — the
  transport-neutral contract: frozen `ApprovalTicket` dataclass,
  `ticket_from(decision, request)`, `to_json()` / `from_json()`, and the
  `WaitOutcome` constants (`APPROVED`, `DENIED`, `EXPIRED`, `MISMATCH`,
  `UNDECIDED`). — DoD: stdlib-only (pinned by a test mirroring
  `tests/test_action_approvals.py::test_module_import_is_stdlib_only`);
  round-trips through JSON; carries no raw action arguments.

- [ ] 3. Add the read-only approval activity (depends on 2) —
  `orchestrator/temporal/activities/action_approvals.py` with
  `@activity.defn async def get_action_approval(approval_ref) -> dict[str, str]`
  wrapping `ActionApprovalClient.get`, plus registration in
  `orchestrator/temporal/worker.py`'s control `WorkerPlan`. — DoD: returns
  state, `intent_hash`, `expires_at`, `decided_by`; never calls `create`
  or `consume`; an unreachable store yields `UNKNOWN` rather than raising.

- [ ] 4. Add the Temporal approval gate (depends on 3) —
  `orchestrator/temporal/approval_gate.py`: the
  `action_approval_decided` signal (defensive parse, ref-matching only,
  payload ignored), the `action_approval_state` query projecting
  `WAITING_FOR_APPROVAL` with `approval_ref` and `expires_at`, and the
  bounded poll loop modelled on `dev_loop.py:2248-2270` with a new
  `ACTION_APPROVAL_POLL_INTERVAL` (15m) and a deadline parsed from
  `ticket.expires_at`. Guard with `workflow.patched("action-approval-gate")`.
  — DoD: the query reports the parked state (the first time
  `WAITING_FOR_APPROVAL` is projected anywhere); the signal never raises
  on a malformed payload; the loop terminates at the deadline with
  `EXPIRED`; no activity is held while parked.

- [ ] 5. Re-entry on wake (depends on 4) — on any wake, re-run the
  governed step with `approval_ref` set so the action's own
  `checkpoint(..., approval_ref=...)` recomputes the intent and redeems.
  — DoD: the gate itself never inspects `state == "approved"` to authorize;
  the only authorization is a returned decision with `code == CODE_APPROVED`.

- [ ] 6. Persist the ticket for the cron driver (depends on 2) — add an
  `approval` block (serialized `ApprovalTicket` plus a `denials` counter)
  to `orchestrator/proposal_state.py`, written from inside the CWFT under
  the `mctl-gitops-main-writes` mutex like every other `.status.yaml`
  write. — DoD: readers tolerate the block's absence; no schema version
  bump; no backfill; a round-trip preserves the ticket.

- [ ] 7. Park the shepherd's merge (depends on 5, 6) — in
  `run_shepherd.merge_pr` (`orchestrator/run_shepherd.py:2565`, checkpoint
  at :2594), branch on `decision.awaiting_approval`: build and persist the
  ticket, log `APPROVAL_PARKED`, return the existing `(False, None)`.
  On a later tick with a stored ticket, call
  `checkpoint(GITHUB_PR_MERGE, ..., approval_ref=...)`. — DoD:
  `merge_pr`'s signature and its `(False, None)` refusal contract are
  unchanged; every existing shepherd test passes untouched; `gh pr merge`
  never runs on a non-permitted decision.

- [ ] 8. Outcome handling (depends on 7) — implement the per-outcome table
  from design.md §5: `denied` increments `denials` and goes terminal
  `needs-triage` with `failure.code: approval-denied` at the cap (mirroring
  `IMPLEMENT_MAX_POLICY_HANDBACKS`); `expired` and `intent_mismatch` clear
  the ticket; `consumed` reconciles against canonical GitHub PR state via
  `orchestrator/pr_adoption.py` instead of re-merging;
  `approval_lookup_error` keeps its existing undecided classification. —
  DoD: no outcome causes a second `gh pr merge`; no outcome re-asks
  unboundedly.

- [ ] 9. Audit and trace (depends on 5) — add `approval_ref`, `approver`
  (`ApprovalRecord.decided_by`) and `decided_at` to
  `policy_checkpoint.decision_record()` and to
  `tracing.record_policy_decision()`, and add the new attribute keys to
  `tracing_sdk`'s `_ALLOWED_KEY` allow-list. Emit `APPROVAL_PARKED` /
  `APPROVAL_RESUMED` on the `lifecycle/claim.py::_emit` convention. — DoD:
  a granted consume shows the approver in both the stdout record and the
  span event; the new span attributes survive `GuardedExporter`; no raw
  arguments appear in either.

- [ ] 10. ADR 015 (depends on 8, 9) —
  `docs/adr/015-human-approval-checkpoints.md`: supersede ADR 014 §7's
  "design only" status, record the one-contract/two-drivers decision,
  correct §4's stale "#195's trace does not exist yet" sentence, and state
  plainly why the action-level approval and the proposal-level `approve`
  signal are different things at different layers with different identity
  guarantees. — DoD: ADR 014 §7 and its open decision 1 link forward to
  015; `tests/test_diagram_facts.py` still passes.

- [ ] 11. Enablement runbook (depends on 10) — document the two-step
  rollout (`MCTL_POLICY_APPROVALS=mctl-api`, then flipping the
  `github-pr-merge` rule to `REQUIRE_APPROVAL` for one service) and the
  `ACTION_APPROVAL_POLL_INTERVAL` / `MCTL_POLICY_APPROVAL_TTL_S` knobs. —
  DoD: an operator can enable and disable the first governed path from the
  runbook alone, without reading the code.

## Tests

- [ ] T1. Contract round-trip: `ApprovalTicket` JSON round-trips; the
  module imports stdlib only.
- [ ] T2. Binding: a receipt bound to head SHA A, revalidated after the PR
  advances to head SHA B, yields `approval_intent_mismatch`, and
  `consume` is never called. This is the issue's "approval cannot be
  reused for a materially different action/target".
- [ ] T3. Single use: a second redemption of a spent receipt yields
  `approval_consumed` and the side effect does not run.
- [ ] T4. Replay safety: drive a workflow through park → approve → resume
  under `WorkflowEnvironment.start_time_skipping()`, then replay the
  recorded history through `temporalio.worker.Replayer`; the external
  mutation is performed exactly once.
- [ ] T5. Patch guard: a pre-`action-approval-gate` history recorded under
  `tests/replay_scenarios.py` replays clean against the new definitions
  (no new command at the gate's position).
- [ ] T6. Signal hygiene: `action_approval_decided` with a malformed
  payload, with a decision payload claiming approval, and with a
  non-matching ref each leave the park intact and authorize nothing.
- [ ] T7. Lost signal: with no signal delivered, the poll path resolves the
  approval within one `ACTION_APPROVAL_POLL_INTERVAL`.
- [ ] T8. Deterministic timeout: no decision by `expires_at` ends the wait
  with `EXPIRED`, deterministically, under time skipping.
- [ ] T9. Store outage: `get_action_approval` failing repeatedly keeps the
  action parked and undecided; it is never recorded as the item's failure.
- [ ] T10. Default-off: with `MCTL_POLICY_APPROVALS` unset, no ticket is
  built, no HTTP call is made, and `merge_pr` behaves byte-identically to
  today. Extend `tests/test_github_mutations_policy.py`.
- [ ] T11. Denial bound: repeated denials reach the terminal
  `needs-triage` at the cap and stop re-asking.
- [ ] T12. Trace: a granted consume emits the approver and timestamp, and
  the new attribute keys survive `tracing_sdk.GuardedExporter` redaction.
- [ ] T13. No leakage: no ticket, record, log line or span attribute
  contains raw action arguments.

## Rollback

Three independent levers, coarsest first.

1. **Disable the governed path (seconds, no deploy).** Revert the
   `github-pr-merge` rule to `ALLOW`. Nothing parks; the gate becomes
   unreachable. Any already-parked merge resolves on its next tick as an
   ordinary allowed merge.
2. **Disable the store (seconds, no deploy).** Unset
   `MCTL_POLICY_APPROVALS`. `REQUIRE_APPROVAL` reverts to blocking with no
   HTTP call — the pre-#198 behaviour exactly.
3. **Revert the code.** The change is additive: a new module, a new
   activity, a new gate, an additive `.status.yaml` block, and new
   optional dataclass fields. Reverting needs no migration and no
   backfill, because nothing existing was rewritten.

Two carve-outs. Temporal histories that already recorded the gate must
keep `workflow.patched("action-approval-gate")` in the tree even after a
functional revert, or in-flight loops wedge on replay — so revert the
*behaviour* while leaving the patch marker, exactly as the repo's other
patch markers are retained. And a stranded `approval` block in
`.status.yaml` is inert to every reader that tolerates its absence (task
6), so it can be left in place and cleaned up lazily rather than migrated
out under time pressure.

An approval consumed but never acted on is not rolled back by any of
these; it is resolved by reconciling against canonical GitHub PR state
(task 8), which is the same mechanism the shepherd already uses for a
merge whose outcome it did not observe.
