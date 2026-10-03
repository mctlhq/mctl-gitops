# Tasks: issue-413-detect-orphans-cannot-see-a-proposal-who

- [ ] 1. Widen the gitops status parse in `orchestrator/temporal/activities/gitops_state.py`:
      add a frozen `ParsedStatus` dataclass (`status`, `pr_url`, `approved_at`,
      `updated_at`, `attempt_started_at`, `attempt_finished_at`,
      `attempt_expires_at`), make `_parse_status_yaml` (lines 137-148) return it,
      and change `_blob_cache` (lines 56-57, 123-134) and `_read_blob`
      (lines 180-202) to cache and return it. Keep the "one unparseable file must
      not blind the sweep" behaviour: a missing or non-mapping `approval:` /
      `attempt:` yields `None` fields, never an exception.
      — DoD: `uv run mypy` clean; no new GitHub call is introduced; the
      `_BLOB_CACHE_MAX` bound and the SHA key are unchanged.

- [ ] 2. Carry the timestamps on the ref (depends on 1): add the five optional
      timestamp fields to `ProposalStateRef` (gitops_state.py:66-76), all
      defaulted to `None`, and populate them in `list_proposal_refs`' inner
      `one()` (lines 258-272).
      — DoD: every existing `ProposalStateRef(...)` construction in the repo and
      in `tests/` still type-checks and runs unmodified.

- [ ] 3. Add the never-started signal type and its knobs to
      `orchestrator/temporal/activities/orphans.py`: `NEVER_STARTED_STATUSES =
      {"accepted", "in-progress"}`, `STALLED_NEVER_STARTED_MINUTES =
      int(os.getenv("STALLED_NEVER_STARTED_MINUTES", "60"))` (the env-override
      shape of `run_incident_responder.MIN_AGE_MINUTES`), the two stable reason
      slugs, the frozen `StalledSignal` dataclass, and a `stalled:
      list[StalledSignal] = field(default_factory=list)` field on
      `OrphanDetectionResult` — defaulted for the same reason `skipped_reason`
      at lines 41-44 is.
      — DoD: an `OrphanDetectionResult` JSON payload recorded without `stalled`
      deserializes with an empty list.

- [ ] 4. Implement the pure helpers in `orphans.py` (depends on 3):
      `_progress_timestamp(...)` returning `(iso_value, field_name)` for the
      first parseable of `attempt.finished_at`, `attempt.started_at`,
      `approval.approved_at`, `updated_at`; `_age_minutes(iso, now)` using the
      `.replace("Z", "+00:00")` idiom, normalising naive values to UTC and
      clamping future timestamps to 0, following
      `run_shepherd._within_settle_window` (run_shepherd.py:1493-1515); and
      `_attempt_is_live(started_at, finished_at, expires_at, now)` mirroring
      `run_shepherd._attempt_is_fresh` (run_shepherd.py:2795-2877) WITHOUT
      importing `run_implementer`.
      — DoD: all three are module-level pure functions taking an explicit `now`,
      directly unit-testable, and `orphans.py` gains no import that
      `tests/test_worker_isolation.py` forbids.

- [ ] 5. Wire the predicate into `_detect_from_github` (orphans.py:102-126),
      the production path (depends on 2, 4): when the existing skip at line 109
      fires because `pr is None` (not because the PR is merged or
      closed-unmerged), evaluate the five never-started guards from design.md
      and append a `StalledSignal`. Emit nothing when the caller passed no
      active set.
      — DoD: a proposal with an open PR is never in `stalled`; a merged or
      closed-unmerged PR is never in `stalled`; `total_actionable` is unchanged.

- [ ] 6. Wire the same predicate into `_sync_detect_orphans` (orphans.py:47-79),
      the local `state_dir` path (depends on 4): re-read `ref.status_path` with
      `run_shepherd._load_status` for refs that reach the never-started branch,
      and preserve `active_workflow_ids is None` as "unknown", distinct from the
      empty set — replacing the collapse at line 55 for the new branch only,
      leaving the existing orphan behaviour byte-identical.
      — DoD: both paths produce the same `StalledSignal` for the same proposal
      state; a diff of the orphan branch shows no behaviour change.

- [ ] 7. Log the signal (depends on 5, 6): a second loop next to
      orphans.py:154-162 emitting
      `STALLED service=%s slug=%s status=%s since=%s since_field=%s age_minutes=%s reason=%s`
      at INFO. Set `skipped_reason` when stalled detection was skipped for an
      unknown active set and nothing else already set it.
      — DoD: an `ORPHAN` line and a `STALLED` line for the same tick are
      independently greppable and carry distinct stable reason slugs.

- [ ] 8. Confirm the workflow needs no change (depends on 7): `ReconcileWorkflow`
      gains no new `workflow.execute_activity` call, no new `workflow.patched`
      marker, and no new field on `ReconcileWorkflowResult`; the signal is
      reached as `result.orphans.stalled`. Verify the visibility-failure early
      return (reconcile.py:110-122) still compiles with the keyword-only
      construction and picks up the empty default.
      — DoD: `git diff orchestrator/temporal/workflows/reconcile.py` is empty,
      and no file under `tests/fixtures/histories/` is modified.

- [ ] 9. Update the docs (depends on 7): the orphan definition in
      `docs/adr/005-temporal-reconcile.md:127-136` gains the second predicate;
      `docs/adr/010-lifecycle-ownership-contract.md:48` gains a row for the
      never-started signal, still "logged only"; `docs/temporal-flow.md:157` and
      `docs/diagrams/temporal-flow-schedules.mmd:4` describe both outputs of the
      `detect_orphans` node.
      — DoD: `.github/workflows/diagrams.yml` passes; no doc still states that
      an orphan requires a PR without qualifying it as the first of two
      predicates.

- [ ] 10. Ship it (depends on 1-9): one branch `fix/...`, Conventional Commit
      `fix(orphans): report proposals whose execution never started (#413)`
      so release-please produces a version bump — `.github/workflows/pr-validation.yml`
      fails the PR without a releasable commit type. Do not hand-edit
      `CHANGELOG.md`.
      — DoD: `uv run pytest tests/`, `uv run ruff check orchestrator config tests`
      and `uv run mypy` all green in CI, plus the automated PR review.

## Tests

- [ ] T1. `tests/test_temporal_activities.py::TestDetectStalled` — accepted
      proposal, no `pr:`, no active DevLoop, `approval.approved_at` 3 hours ago
      (the #412 shape): exactly one `StalledSignal`, reason
      `execution-never-started`, `age_minutes` ~180, and `orphans == []`.
- [ ] T2. Freshly approved: `approved_at` 5 minutes ago with the default
      60-minute threshold produces no stalled signal. Covers the issue's explicit
      "a proposal approved seconds ago is not reported as stuck".
- [ ] T3. Live claim: status `in-progress`, `attempt.expires_at` in the future,
      no `finished_at` — no stalled signal even though the age is past the
      threshold. Then advance past `expires_at` and assert it does report.
- [ ] T4. No parseable timestamp at all (`approval`, `attempt` and `updated_at`
      absent) — reported with reason `execution-never-started-unknown-age` and
      `age_minutes is None`, never dropped.
- [ ] T5. Unknown active set: `await env.run(detect_orphans, state_dir, None)`
      yields `stalled == []` and a non-empty `skipped_reason`, so the unpatched
      replay branch cannot manufacture false positives.
- [ ] T6. Disjointness: a proposal with an open PR and no active DevLoop appears
      in `orphans` and not in `stalled`; a merged PR and a closed-unmerged PR
      appear in neither. Asserts the existing predicate is untouched.
- [ ] T7. Status filter: `implemented` and `review-fixing` with no PR produce no
      stalled signal; `accepted` and `in-progress` do.
- [ ] T8. GitHub path parity: extend the existing HTTP-fixture class that owns
      `test_orphans_are_detected_from_github_too`
      (tests/test_temporal_activities.py:1536-1562), using its
      `self._clear_cache()` / `self._handler(monkeypatch, tree=..., blobs=..., pulls=...)`
      helpers with blobs carrying `approval.approved_at`, and assert the same
      signal the local path produces in T1.
- [ ] T9. Blob-cache shape: two `list_proposal_refs()` calls over the same SHA
      return refs with identical timestamp fields and issue only one blob read —
      the cache still hits after the value type widened.
- [ ] T10. Threshold override: `monkeypatch.setenv("STALLED_NEVER_STARTED_MINUTES", ...)`
      plus a module reload changes the boundary, documenting the operator knob.
- [ ] T11. `tests/test_reconcile_workflow.py` — extend `_fake_activities`' fake
      `detect_orphans` to return a result carrying `stalled`, and assert
      `result.orphans.stalled` survives the workflow round trip; assert the
      visibility-failure tick (lines 151-177) reports `stalled == []` alongside
      its existing empty orphans and non-None `skipped_reason`.
- [ ] T12. Backward deserialization: an `OrphanDetectionResult` payload without
      the `stalled` key loads with an empty list, mirroring the `skipped_reason`
      and `PRSnapshot.head_sha` precedents.
- [ ] T13. `tests/test_workflow_replay.py` passes unmodified against the
      untouched `reconcile_apply.prepatch.json` and
      `reconcile_apply.patched.json` — the regression guard that this change
      added no workflow command.
- [ ] T14. `tests/test_worker_isolation.py` passes: the widened `orphans.py` and
      `gitops_state.py` still import neither `claude_agent_sdk` nor
      `orchestrator.run_implementer` at module scope.

## Rollback

Single-commit revert. The change is read-only end to end: no `.status.yaml` key
is written, no gitops commit is made, no Temporal workflow command is added, no
`workflow.patched` marker is introduced, and no history fixture is re-recorded —
so reverting leaves no half-applied state anywhere, in-flight `ReconcileWorkflow`
executions replay against the reverted definitions unchanged, and the next tick
simply stops emitting `STALLED` lines.

If the volume of `STALLED` lines is the only problem, no revert is needed: raise
`STALLED_NEVER_STARTED_MINUTES` on the Temporal worker deployment in mctl-gitops
and restart it. Setting it very high effectively disables the new signal while
leaving the existing orphan detection completely untouched.

The one thing a revert must also undo is the `_blob_cache` value type in
`gitops_state.py`; because the cache is in-process and keyed by blob SHA with no
persistence, a reverted worker starts with an empty cache and cannot read a
widened entry, so there is nothing to clean up.
