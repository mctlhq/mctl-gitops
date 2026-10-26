# Tasks: issue-813-fix-security-harden-landed-binding-corre

- [ ] 1. Add `SUPPORTED_OWNER`, `mctlhq_repo_name()` and `issue_number_for()` to
  `orchestrator/security_findings/landed.py` — DoD: pure functions, no regex over owner/repo, unit-tested.
- [ ] 2. (depends on 1) In `orchestrator/run_security_verifier.py`, change `MergedLookup` to
  `(client, workflow_id, repo)`, rewrite `default_merged_lookup` to use the passed repo and
  `issue_number_for`, remove `_DEV_LOOP_ID_RE` and `import re` — DoD: no workflow-id-to-repo parsing remains.
- [ ] 3. (depends on 2) In `_bind_missed`, derive `repo` from `occ.repository or summary.repository`; emit
  `skipped="repository_unsupported"` and continue when empty — DoD: lookup always receives the occurrence's repo.
- [ ] 4. In `bind_landed`, drop `LandedOutcome(summary.id, UNKNOWN)` for unread candidates; log a warning and
  continue; update the module docstring — DoD: no outcome carries an id that was not proven to match `workflow_id`.
- [ ] 5. (depends on 2) Update existing sweep tests' `merged_lookup` lambdas to the 3-arg form — DoD: suite green.

## Tests
- [ ] T1. `issue_number_for("dev-loop-mctlhq-svc-7", "svc") == "7"`; `issue_number_for("dev-loop-mctlhq-my-repo-42", "my-repo") == "42"`;
  `issue_number_for("dev-loop-my-org-my-repo-42", "org-my-repo") == ""`; `issue_number_for("dev-loop-mctlhq-svc-7x", "svc") == ""`.
- [ ] T2. `mctlhq_repo_name`: `github.com/mctlhq/svc`, `mctlhq/svc.git/` -> `svc`; `github.com/my-org/my-repo`,
  `gitlab.com/mctlhq/svc`, `svc`, `""` -> `""`.
- [ ] T3. Sweep fallback with occurrence repo `github.com/mctlhq/my-repo` and attempt workflow id
  `dev-loop-mctlhq-my-repo-42`: `default_merged_lookup` (with monkeypatched `find_proposal_slug`/`get_pr_state`
  and a finished dev loop) is called with repo `my-repo`, number `42`, and the occurrence binds.
- [ ] T4. Workflow id `dev-loop-my-org-my-repo-42` (repo `github.com/my-org/my-repo`): no proposal/PR call,
  `skipped="repository_unsupported"` emitted, occurrence stays `fixing`; and a recorder lookup never receives `org-my-repo`.
- [ ] T5. Two `fixing` occurrences in `github.com/mctlhq/svc`, one for `WID`, one for another DevLoop; make
  `GET` of the unrelated one fail (503 for that id): `bind_landed` returns only `[(matching_id, "bound")]`.
- [ ] T6. Single unread candidate: `bind_landed` returns `[]` (not `LandedOutcome(<id>, "unknown")`).
- [ ] T7. Existing `test_store_503_is_unknown_everywhere_and_writes_nothing`, `test_landed_binding_matches_exactly_and_is_replayed`,
  `test_sweep_fallback_binds_a_missed_merge`, `test_two_cycle_proof` remain green.

## Rollback
Revert the PR. No data, schema or Temporal history depends on it; the verifier sweep is not yet scheduled, so
reverting only restores the pre-fix (known-defective) matching. Keep the sweep unscheduled if reverted.
