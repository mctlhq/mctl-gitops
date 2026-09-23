# Tasks: issue-198-feat-governance-human-approval-checkpoin

Revision 2 (2026-09-23). The Temporal wait driver is mctl-agents#479
(`ActionApprovalWaitWorkflow`, `run_gated_action`, `read_action_approval`,
`next_attempt`); do not re-implement, extend or duplicate it. This slice is
the cron-driven first adopter (the shepherd merge), the approver record on
the trace, and the ADR. Build on `main` after #479 has merged; if #479 is
still open, base the branch on `main` and import nothing from #479's
modules beyond the `action_approvals` constants.

- [ ] 1. Add `orchestrator/approval_ticket.py` — frozen `ApprovalTicket`
  dataclass, `ticket_from(decision, request, record)` where `record` is
  the `ApprovalRecord` from one read-only
  `ActionApprovalClient.get(decision.approval_ref)`, `to_json()` /
  `from_json()`. — DoD: stdlib-only (pinned by a test mirroring
  `tests/test_action_approvals.py::test_module_import_is_stdlib_only`);
  round-trips through JSON; carries no raw action arguments;
  `policy_checkpoint.py` is not modified.

- [ ] 2. Persist the ticket for the cron driver (depends on 1) — add an
  `approval` block (serialized `ApprovalTicket` plus a `denials` counter)
  to `orchestrator/proposal_state.py`, written from inside the CWFT under
  the `mctl-gitops-main-writes` mutex like every other `.status.yaml`
  write. — DoD: readers tolerate the block's absence; no schema version
  bump; no backfill; a round-trip preserves the ticket.

- [ ] 3. Park the shepherd's merge (depends on 2) — in
  `run_shepherd.merge_pr` (`orchestrator/run_shepherd.py`, the
  `GITHUB_PR_MERGE` checkpoint), branch on `decision.awaiting_approval`:
  build and persist the ticket, log `APPROVAL_PARKED`, return the existing
  `(False, None)`. On a later tick with a stored ticket for this PR, call
  `checkpoint(GITHUB_PR_MERGE, ..., approval_ref=ticket.approval_ref)` and
  log `APPROVAL_RESUMED`. — DoD: `merge_pr`'s signature and its
  `(False, None)` refusal contract are unchanged; every existing shepherd
  test passes untouched; `gh pr merge` never runs on a non-permitted
  decision; the merge still binds the PR head SHA so a moved head is
  `approval_intent_mismatch`.

- [ ] 4. Outcome handling (depends on 3) — implement the shepherd column
  of design.md §3 using the `action_approvals` constants: `DENIED`
  increments `denials` and goes terminal `needs-triage` with
  `failure.code: approval-denied` at the cap (mirroring
  `IMPLEMENT_MAX_POLICY_HANDBACKS`); `EXPIRED` and `MISMATCH` clear the
  ticket so the next tick may open a fresh request for the current head;
  `CONSUMED` reconciles against canonical GitHub PR state via
  `orchestrator/pr_adoption.py` instead of re-merging;
  `approval_lookup_error` keeps its existing undecided classification. —
  DoD: no outcome causes a second `gh pr merge`; no outcome re-asks
  unboundedly; a lost ticket is recovered by the deterministic
  `idempotency_key(intent)` find-or-create on the next tick (design.md
  alternative 3), never by a second request.

- [ ] 5. Audit and trace (depends on 3) — add `approval_ref`, `approver`
  (`ApprovalRecord.decided_by`) and `decided_at` to
  `policy_checkpoint.decision_record()` and to
  `tracing.record_policy_decision()`, emitted as
  `mctl.policy.approval_ref`, `mctl.approval.approver`,
  `mctl.approval.decided_at`, and add the new keys to `tracing_sdk`'s
  `_ALLOWED_KEY` allow-list. Emit `APPROVAL_PARKED` / `APPROVAL_RESUMED`
  on the `lifecycle/claim.py::_emit` convention. — DoD: a granted consume
  shows the approver in both the stdout record and the span event; the new
  span attributes survive `GuardedExporter`; no raw arguments appear in
  either; the same fields are populated when #479's Temporal driver
  redeems, since both go through `checkpoint(..., approval_ref=...)`.

- [ ] 6. ADR 016 (depends on 4, 5) —
  `docs/adr/016-human-approval-checkpoints.md`: record the
  one-contract/two-drivers decision (Temporal child workflow from #479;
  cron ticket from this slice), the outcome table, the approver record,
  the companion mctl-api#381 signal and the surfaces follow-up, and state
  plainly why the action-level approval and the proposal-level `approve`
  signal are different things at different layers with different identity
  guarantees. Link forward from ADR 014 §7 and its open decision 1 without
  rewriting #479's §7 text. — DoD: `tests/test_diagram_facts.py` still
  passes; ADR 014 §7's "not built" list shrinks to the surfaces and the
  mctl-api signal.

- [ ] 7. Enablement runbook (depends on 6) — document the two-step rollout
  (`MCTL_POLICY_APPROVALS=mctl-api`, then flipping the `github-pr-merge`
  rule to `REQUIRE_APPROVAL` for one service) and the
  `MCTL_POLICY_APPROVAL_TTL_S` knob, plus how to find a parked merge
  (`.status.yaml` `approval` block, `APPROVAL_PARKED` line,
  `GET /action-approvals?status=pending`) and how to decide it
  (`POST /action-approvals/{id}/decision`). — DoD: an operator can enable,
  decide and disable the first governed path from the runbook alone.

- [ ] 8. Open the follow-up issues (depends on 6) — one in mctl-api for
  the human approval surfaces (an MCP tool pair to list pending approvals
  and submit a decision, reading `ApprovalTicket` fields), cross-linked to
  mctl-api#381 and #198; confirm mctl-api#381 is still the signal tracker.
  — DoD: both issues are referenced from ADR 016 and from the #198 issue.

## Tests

- [ ] T1. Contract round-trip: `ApprovalTicket` JSON round-trips; the
  module imports stdlib only; `ticket_from` performs exactly one `get`.
- [ ] T2. Binding: a receipt bound to head SHA A, revalidated after the PR
  advances to head SHA B, yields `approval_intent_mismatch`, and
  `consume` is never called. This is the issue's "approval cannot be
  reused for a materially different action/target".
- [ ] T3. Single use: a second redemption of a spent receipt yields
  `approval_consumed`, the side effect does not run, and the shepherd
  reconciles PR state instead of merging.
- [ ] T4. Park and resume across ticks: tick 1 parks (ticket persisted,
  `APPROVAL_PARKED`, no merge); tick 2 with the receipt approved redeems
  through `checkpoint(..., approval_ref=...)` and merges exactly once
  (`APPROVAL_RESUMED`).
- [ ] T5. Lost ticket: with the `approval` block removed between ticks,
  the next tick re-derives the same request by idempotency key and opens
  no second request.
- [ ] T6. Store outage: `get` failing repeatedly keeps the merge parked and
  undecided; it is never recorded as the item's failure.
- [ ] T7. Default-off: with `MCTL_POLICY_APPROVALS` unset, no ticket is
  built, no HTTP call is made, and `merge_pr` behaves byte-identically to
  today. Extend `tests/test_github_mutations_policy.py`.
- [ ] T8. Denial bound: repeated denials reach the terminal
  `needs-triage` at the cap and stop re-asking.
- [ ] T9. Expiry and mismatch clear the ticket; the following tick opens a
  new request for the current head.
- [ ] T10. Trace: a granted consume emits the approver and timestamp, and
  the new attribute keys survive `tracing_sdk.GuardedExporter` redaction.
- [ ] T11. No leakage: no ticket, record, log line or span attribute
  contains raw action arguments.
- [ ] T12. #479's suites (`tests/test_action_approval_wait.py`,
  `tests/test_workflow_replay.py`) and the shepherd suites stay green with
  no edits.

## Rollback

Three independent levers, coarsest first.

1. **Disable the governed path (seconds, no deploy).** Revert the
   `github-pr-merge` rule to `ALLOW`. Nothing parks. Any already-parked
   merge resolves on its next tick as an ordinary allowed merge.
2. **Disable the store (seconds, no deploy).** Unset
   `MCTL_POLICY_APPROVALS`. `REQUIRE_APPROVAL` reverts to blocking with no
   HTTP call — the pre-#198 behaviour exactly, for both drivers.
3. **Revert the code.** The change is additive: a new module, an additive
   `.status.yaml` block, a branch in `merge_pr`, and new optional record
   fields. No Temporal workflow definition changes, so no patch marker to
   retain and no replay exposure; #479 is untouched by the revert.

A stranded `approval` block in `.status.yaml` is inert to every reader
that tolerates its absence (task 2), so it can be left in place and
cleaned up lazily. An approval consumed but never acted on is resolved by
reconciling against canonical GitHub PR state (task 4), the same mechanism
the shepherd already uses for a merge whose outcome it did not observe.
