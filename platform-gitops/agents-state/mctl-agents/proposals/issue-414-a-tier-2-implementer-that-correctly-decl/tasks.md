# Tasks: issue-414-a-tier-2-implementer-that-correctly-decl

- [ ] 1. Extend the marker contract in `orchestrator/run_implementer.py`: add `REFUSAL_KINDS`, `MAX_REFUSAL_RECOMMENDATION_CHARS = 4000`, and `RefusalMarker.kind` (default `"no-op"`) and `.recommendation` (default `""`). Parse both in `_read_refusal_marker`; an unknown or non-string `kind` rejects the marker, and a non-string `recommendation` is dropped. Update the docstrings. — DoD: existing markers parse to `kind="no-op"`; the new fields are validated and capped.
- [ ] 2. Review-fix path (depends on 1): in the no-commit branch around `refusal = _read_refusal_marker(target)` (~3137), treat `kind != "no-op"` as no marker and log it. — DoD: a `scope`/`cross-repo`/`blocked` marker on a review follow-up exits 42 (charged); `no-op` markers behave exactly as before.
- [ ] 3. Initial implement path (depends on 1): in `implement_one`'s `if not obs.commits_present:` block, after the `budget_ledger.exhausted` arm and before the `no-commits` `_mark_needs_triage`, read the marker and record `refused-<kind>` with a `refusal:` block via `extra_fields`. Add `IMPLEMENT_REFUSED_ERROR_PREFIX` and `ImplementResult.implement_refusal`. — DoD: the #242 scenario records `failure.code: refused-scope` with reason and recommendation; no marker still records `no-commits`; an exhausted ledger still wins.
- [ ] 4. Add `_comment_refusal_on_source_issue` (depends on 3): source lookup via `read_source_issue`, an idempotency marker in the body, a post through the policy checkpoint and `gh issue comment` (same pattern as `run_issue_investigator.py`), with every failure caught and logged. Add a policy-checkpoint allowance for this comment in `orchestrator/policy_checkpoint.py` if one is required. — DoD: a comment is posted once per recorded non-`no-op` refusal on an open linked issue; a failure leaves the outcome unchanged.
- [ ] 5. Completion and batch accounting (depends on 3): add `"implement_refused"` to `orchestrator/implementation_completion.py` `STOP_REASON_OUTCOMES` as `OUTCOME_BOUNDED_REFUSAL`. Map `implement_refusal` in `_classify_result` (no-op to `deliberate_no_op`). Exclude these results from `failed` in `_batch_outcome`, keep them counting toward the limit, and add a summary section in `main()`. Add a row to the ADR 021 table in `docs/adr/021-implementation-completion-contract.md`. — DoD: the completion record for a scope refusal is `bounded_refusal / implement_refused`; a tick whose only non-success is a refusal is not red.
- [ ] 6. Prompt (depends on 1): rewrite `_build_prompt` initial rule 5 and the cross-repo ground-rule bullet to document the typed marker, including the `recommendation` and "never beside a commit". — DoD: the prompt text names the file, all four kinds, and the recommendation field.
- [ ] 7. Agent definitions (depends on 6): update the "Declining to act is a valid outcome" bullet in all 8 `agents/*/.claude/agents/implementer.md` to split the review-follow-up rule (unchanged) from the initial-implement rule (write a typed marker). — DoD: all copies are consistent; the review rule still forbids a marker when blocked.
- [ ] 8. CHANGELOG / docs note (depends on 3-5): record the new failure codes and the `refusal:` block, and add a note that the mctl-gitops `assert-attempt` hint needs a companion change. — DoD: an operator can find the code meanings in-repo.

## Tests

- [ ] T1. `tests/test_run_implementer_refusal.py`: a marker without `kind` gives `kind="no-op"`; each valid kind round-trips; an unknown kind, `kind: 1` or `kind: null` gives `None`; a recommendation over the cap is truncated; a non-string recommendation is dropped and the marker is still valid.
- [ ] T2. Review path: a `kind: scope` marker with no commits gives the charged no-follow-up exit (42); `kind: no-op` still gives 47; `insufficient_evidence` with `no-op` still gives 50.
- [ ] T3. Initial path (extend `tests/test_run_implementer_budget_handback.py` or add `tests/test_run_implementer_implement_refusal.py`): no commits plus a `scope` marker writes `needs-triage` with `failure.code: refused-scope` and a `refusal` block holding reason and recommendation, and `ImplementResult.implement_refusal == "scope"`.
- [ ] T4. Initial path: no commits and no marker still writes `no-commits` (regression).
- [ ] T5. Initial path: ledger exhausted plus a `scope` marker takes the budget hand-back / `verification-budget-exhausted` arm, not `refused-scope`.
- [ ] T6. Initial path: a commit plus a marker pushes normally; the marker does not change the outcome.
- [ ] T7. Initial path: a tracked marker is ignored and the result is `no-commits`.
- [ ] T8. Attempt CAS lost (`_status_is_still_ours` false): no status write and no issue comment.
- [ ] T9. Issue comment: posted once with the idempotency marker; `gh` failure, a policy-checkpoint refusal, or an unreadable or closed source issue logs a warning and leaves the result unchanged; not posted for `refused-no-op`.
- [ ] T10. `tests/test_run_implementer_completion.py`: `implement_refused` is mapped to `bounded_refusal`; the exhaustiveness check passes; `_batch_outcome` does not count an implement refusal as failed.
- [ ] T11. Prompt test: the initial `_build_prompt` output contains `.implementer-refusal.json` and every kind; the review prompt is unchanged apart from the documented text.

## Rollback

Revert the PR. Markers without `kind` were never affected, so reverting returns the
initial path to the unconditional `no-commits` record. Proposals already recorded
as `refused-*` stay in `needs-triage`, which is terminal and human-gated either
way. Their `refusal:` block becomes inert extra data that the shepherd and
reconcile do not read. No data migration is needed.
