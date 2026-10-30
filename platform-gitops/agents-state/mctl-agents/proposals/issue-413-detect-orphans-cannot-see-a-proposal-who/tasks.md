# Tasks: issue-413-detect-orphans-cannot-see-a-proposal-who

- [ ] 1. Extract `approval.approved_at` in `orchestrator/temporal/activities/gitops_state.py`: extend `_ParsedStatus` / `_parse_status_yaml` (normalize with `str(...)` like `updated_at`), update the unpack in `list_proposal_refs.one`, add `approved_at: str | None = None` to `ProposalStateRef` — DoD: existing gitops_state tests pass; a new test shows quoted and unquoted `approved_at` both round-trip as strings.
- [ ] 2. Move `stranded._parse_iso` to `gitops_state.parse_iso`, leaving `stranded._parse_iso` as an alias — DoD: `tests/test_stranded_activity.py` passes unchanged.
- [ ] 3. Add `NEVER_STARTED_THRESHOLD_MINUTES_ENV`, `DEFAULT_NEVER_STARTED_THRESHOLD_MINUTES = 45` and `never_started_threshold_minutes()` to `orchestrator/temporal/constants.py`, with a comment tying 45 to the implement-sweep grace (20 minutes) plus its interval (15 minutes) — DoD: the env override and the default are both covered by a test.
- [ ] 4. (depends on 1, 2, 3) In `orchestrator/temporal/activities/orphans.py`:
  - add `NEVER_STARTED_STATUSES`, `NEVER_STARTED_REASON`, `NeverStartedSignal`, and the defaulted fields `OrphanDetectionResult.never_started` and `never_started_unauthorized`;
  - add the pure `_classify_never_started(refs, active_ids, threshold_minutes, now)` with the ordered rules from design.md section 3.

  DoD: the function is pure (no I/O, `now` injected), and the existing PR-orphan loops are byte-for-byte unchanged in behaviour.
- [ ] 5. (depends on 4) Call the classifier from `_detect_from_github` on the already-listed actionable refs. In `_sync_detect_orphans`, build `ProposalStateRef`s from `_discover_refs` plus `run_shepherd._load_status`, using `proposal_state.execution_authorization` and `unrunnable_reason`, and call the same classifier. Run it only when `detect_orphans` received `active_workflow_ids is not None`. DoD: both paths return identical `never_started` for equivalent fixtures; a `None` active set yields `never_started == []`.
- [ ] 6. (depends on 5) In `detect_orphans`, log one `NEVER_STARTED ...` WARNING per signal and one INFO summary with the counts, including `never_started_unauthorized`. Update the module and activity docstrings to describe both signals — DoD: a log assertion test passes.
- [ ] 7. Document the never-started signal in `docs/adr/005-temporal-reconcile.md` under "Orphan definition": the predicate, its threshold, that it is report-only, and its relation to `ImplementSweepWorkflow` — DoD: the ADR text matches the implemented predicate.
- [ ] 8. (depends on 5) Confirm `orchestrator/temporal/workflows/reconcile.py` needs no change: the visibility-failure arm's `OrphanDetectionResult(...)` gets the new fields by default, and no new `workflow.patched` is introduced — DoD: replay tests over `tests/fixtures/histories/reconcile_apply.*.json` pass unchanged.

## Tests

- [ ] T1. `_classify_never_started`: an `accepted`, authorized, PR-less proposal approved 60 minutes ago with no live loop yields one signal with `NEVER_STARTED_REASON` and `age_minutes == 60`.
- [ ] T2. The same proposal approved 10 minutes ago (below the threshold) yields no signal.
- [ ] T3. Exclusions each yield no signal: `pr_url` set; unexpired `attempt_expires_at`; `unrunnable`; `blocked`; derived `dev-loop-mctlhq-<svc>-<N>` in the active set; status `implemented` or `review-fixing`.
- [ ] T4. Unauthorized (`execution_authorization is None`) yields no signal and increments `never_started_unauthorized`, for both legacy and anonymous-approver reasons.
- [ ] T5. Age falls back to `updated_at` when `approved_at` is missing. With both missing or unparseable, it reports with `age_minutes is None`.
- [ ] T6. An `in-progress` status is classified like `accepted`.
- [ ] T7. `detect_orphans` via `env.run` on the GitHub path (extending `test_orphans_are_detected_from_github_too`'s fixtures): one PR orphan and one never-started proposal come back in separate fields with distinct reasons. The existing orphan assertions still hold.
- [ ] T8. `detect_orphans(state_dir, None)` returns `never_started == []`; `detect_orphans(state_dir, [])` reports eligible proposals.
- [ ] T9. Local-checkout path (`tmp_path` with real `.status.yaml` files) and GitHub path agree for the same fixture set.
- [ ] T10. An `OrphanDetectionResult` payload without the new fields deserializes through the Temporal data converter, with defaults.
- [ ] T11. `tests/test_reconcile_workflow.py`: when the visibility query fails, the result has `orphans.never_started == []` and `skipped_reason` set; on a normal tick, `ReconcileWorkflowResult.orphans.never_started` carries the activity's signals.

## Rollback

The change is report-only and adds no workflow commands, so rolling it back is a plain revert of the PR and a worker redeploy. Defaulted fields mean any results recorded in the meantime still deserialize after the revert. Unknown fields are dropped by the dataclass converter, which should be verified as part of T10. To silence the signal without a deploy, set `NEVER_STARTED_THRESHOLD_MINUTES` to a very large value (e.g. `525600`) in `services/admins/mctl-agents-worker/values.yaml`'s `env:` block. No durable state is written, so there is nothing to clean up.
