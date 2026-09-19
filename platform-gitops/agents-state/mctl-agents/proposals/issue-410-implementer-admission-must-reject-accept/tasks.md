# Tasks: issue-410-implementer-admission-must-reject-accept

- [ ] 1. Add `orchestrator/source_issue.py` with `SourceIssueVerdict` (fields
      `known`, `failure`, `linked`, `issue_ref`, `closed_at`, `state_reason`)
      and `read_source_issue(status_data, *, stage)`, moving the body of
      `run_shepherd._source_issue_state` (run_shepherd.py:1272) verbatim in
      behaviour. Depend only on `json`, `subprocess` and
      `orchestrator.proc.run_capturing` — never on `run_shepherd` or
      `run_implementer` (`pr_adoption` already imports `run_shepherd`, so either
      import would create a cycle). — DoD: module imports standalone
      (`python -c "import orchestrator.source_issue"` with no gh/network), keeps
      `source-resolved` / `source-not-planned` code selection identical, and
      sets `linked=False` for an absent/partial/non-`github_issue` source block
      while keeping `linked=True, known=False` for an unreadable GitHub.
- [ ] 2. Reduce `run_shepherd._source_issue_state` to
      `read_source_issue(status_data, stage="reconcile")` (depends on 1),
      leaving `_SOURCE_UNKNOWN` / `_SOURCE_ISSUE_OPEN` semantics and the
      `reconcile_one` call site at run_shepherd.py:3055 untouched. — DoD:
      `uv run pytest tests/test_run_shepherd.py` passes with no test edits.
- [ ] 3. Add `_stale_source_message(ref, verdict)` to
      `orchestrator/run_implementer.py`: issue reference, close reason, close
      timestamp, and the reopen / re-publish-as-`proposed` recovery sentence
      (depends on 1). — DoD: message is deterministic for a fixed verdict and
      stays under the 2000-char clamp `_mark_needs_triage` applies.
- [ ] 4. Add best-effort supersession lookup used by task 3 (depends on 3):
      only on the closed-as-completed arm, `gh api
      repos/<repo>/issues/<N>/timeline`, keeping `cross-referenced` events whose
      `source.issue.pull_request.merged_at` is set plus `closed` events with a
      `commit_id`; at most three URLs, newest first. Any exception or empty
      result drops the sentence. — DoD: a raised exception inside the lookup
      never propagates and never changes the verdict.
- [ ] 5. Insert the admission gate in `implement_one` (run_implementer.py:2534)
      immediately after the `existing.action == "needs-triage"` branch and
      before `ensure_auth_for_sdk()` — i.e. only on the `existing.action ==
      "none"` path (depends on 3). Unreadable-but-linked -> return
      `skipped_reason`, `counts_toward_limit=False`, no write. Closed ->
      `_mark_needs_triage(code=verdict.failure["code"], stage="admission",
      message=…)` with no `attempt` and no `claim_context`, returning
      `error=_triage_error(message, recorded)` and
      `counts_toward_limit=False`. — DoD: no clone, no `_acquire_claim`, no
      `in-progress` write and no SDK call happen on either arm; an existing
      open/merged/closed/branch-ready preflight result still short-circuits
      first.
- [ ] 6. Print a `=== Stale source ===` section in `main()` beside the existing
      `=== Blocked ===` block, one line per refusal (`service/slug: <code>
      <issue-ref>`) (depends on 5). — DoD: section is absent when no refusal
      occurred; totals line is unchanged in shape.
- [ ] 7. Add `orchestrator/temporal/activities/issue_state.py` with
      `get_issue_state(repo, issue_number) -> IssueState(state, state_reason,
      closed_at)`, following `activities/proposals.py`'s `_resolve_token()` +
      `httpx` + retryable-exception pattern (never an unauthenticated request),
      and register it in `orchestrator/temporal/worker.py` next to
      `find_proposal_slug` / `get_pr_state`. — DoD: worker starts with the
      activity registered; a missing token raises the retryable error rather
      than issuing an anonymous call.
- [ ] 8. Call `get_issue_state` in `DevLoopWorkflow.run` (dev_loop.py, right
      after `await workflow.wait_condition(lambda: self._approved)`) behind
      `workflow.patched("stale-issue-admission")` (depends on 7); a closed issue
      returns `DevLoopResult(investigate=…, implement=None)` with the skip
      reason recorded, before `find_proposal_slug` and before the
      `mctl-agents-approve` CWFT. Activity failure after retries proceeds
      (fail-open on the workflow side). — DoD: no approve or implement Argo
      submission occurs for a closed issue; the unpatched branch is byte-for-byte
      today's command sequence.
- [ ] 9. Document the gate: a "Stale source issue" subsection in
      `docs/adr/005-temporal-reconcile.md` under the existing `failure.code`
      table noting that the implementer now emits the same two codes at
      `stage: admission`, and one line in the `run_implementer.py` module
      docstring's Idempotency section (depends on 5). — DoD: the ADR table and
      the code agree on both code names and on who may write them.

## Tests

- [ ] T1. `tests/test_source_issue.py` — unit table over
      `read_source_issue`: open issue -> `known=True, failure=None`; closed with
      `state_reason=completed` -> `source-resolved`; `not_planned` ->
      `source-not-planned`; closed with `state_reason` null -> `source-resolved`;
      no `source` block / partial block / `type != github_issue` ->
      `linked=False`; `gh` raising and an unparseable payload ->
      `linked=True, known=False`.
- [ ] T2. `tests/test_run_implementer_admission.py::test_closed_source_issue_is_refused_before_the_model`
      — an accepted, approved proposal with a closed source issue, preflight
      stubbed to `ExistingResult(action="none")`: asserts `.status.yaml` becomes
      `needs-triage` with `failure.code == "source-resolved"` and
      `failure.stage == "admission"`, and that `ensure_auth_for_sdk`,
      `_acquire_claim`, `_clone_target` and the SDK entry point were never
      called (mock assertions, not just a status check — the whole point is the
      spend that did not happen).
- [ ] T3. `...::test_not_planned_issue_uses_its_own_code` — same shape,
      `state_reason=not_planned` -> `source-not-planned`.
- [ ] T4. `...::test_unreadable_github_leaves_the_proposal_accepted` — the issue
      read raises: `.status.yaml` is byte-identical afterwards, result carries
      `skipped_reason` and `counts_toward_limit is False`, no model call.
- [ ] T5. `...::test_proposal_without_a_source_block_still_runs` — an
      incident-responder-shaped proposal (no `source`) reaches the claim/clone
      path unchanged, proving the gate cannot strand that whole class.
- [ ] T6. `...::test_existing_merged_pr_wins_over_a_closed_issue` — preflight
      returns `action="merged"` while the source issue is closed: status becomes
      `merged`, the gate never runs, no issue read is performed. This is the
      regression the ordering exists to prevent.
- [ ] T7. `...::test_refusal_does_not_consume_the_batch_budget` — two accepted
      proposals, the first stale, `--max-proposals 1`: `_implement_refs` still
      attempts the second.
- [ ] T8. `...::test_supersession_urls_are_listed_and_failures_are_silent` —
      timeline stub returning one merged cross-reference puts its URL in
      `failure.message`; a timeline stub that raises still produces the same
      `failure.code` with no URL sentence.
- [ ] T9. `tests/test_run_implementer_admission.py::test_dry_run_writes_nothing`
      — `--dry-run` over a stale proposal leaves `.status.yaml` untouched.
- [ ] T10. `tests/test_dev_loop_workflow.py::test_closed_issue_skips_approve_and_implement`
      — workflow-test harness: approve signal delivered, `get_issue_state`
      stubbed closed; assert no `mctl-agents-approve` and no implement activity
      were scheduled and the result carries the skip reason. Plus a fail-open
      case where the activity errors and the loop proceeds.
- [ ] T11. `tests/test_workflow_replay.py` / `tests/replay_scenarios.py` — replay
      a recorded pre-patch history through the new workflow code and assert no
      nondeterminism error (the `stale-issue-admission` patch guard).
- [ ] T12. `uv run ruff check .` and `uv run mypy .` clean, per LLMS.md.

## Rollback

The change is additive and confined to four files plus two new modules, so
rollback is a revert of the implementer PR — no data migration, and no
`.status.yaml` schema change to undo.

Staged de-escalation, cheapest first, if the gate misbehaves in production:

1. **Proposal-level:** any proposal wrongly refused is recoverable by reopening
   its source issue and moving `status` back to `accepted` in gitops (dropping
   the `failure` block). The refusal wrote no branch, no PR and no claim, so
   there is nothing else to clean up.
2. **Workflow-level:** revert task 8's patched block alone. Because it is
   guarded by `workflow.patched("stale-issue-admission")`, removing it is only
   safe while no history has recorded the marker; once any has, neutralise it by
   making the closed-issue branch a log-and-continue instead of deleting the
   command, which preserves replay determinism.
3. **Full revert:** `git revert` the merge commit. `run_shepherd`'s behaviour is
   unchanged by design (task 2 is a pure delegation), so a revert restores
   exactly today's admission path: approval gate, result preflight, model.
