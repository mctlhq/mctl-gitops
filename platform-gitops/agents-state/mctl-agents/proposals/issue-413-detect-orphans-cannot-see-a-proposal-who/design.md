# Design: issue-413-detect-orphans-cannot-see-a-proposal-who

## Current state

- `orchestrator/temporal/activities/orphans.py`
  - `ACTIONABLE_STATUSES = {"accepted", "in-progress", "implemented", "review-fixing"}`.
  - `_sync_detect_orphans` is the local-checkout path. It iterates `_discover_refs(state_dir, reconcile=True)` and calls `run_shepherd.find_pr_for_proposal`, which reads `pr:` and falls back to branch discovery. It executes `continue` when `pr is None or pr.closed_unmerged or pr.merged`.
  - `_detect_from_github` is the worker's default path. It runs `list_proposal_refs()` and then `fetch_pr_snapshots(refs)`, and applies the same `continue` on a missing snapshot. `fetch_pr_snapshots` only fetches refs whose `pr:` parses via `pr_ref_of`.
  - Both paths emit `OrphanSignal(reason="No active DevLoopWorkflow found for open PR proposal")`.
  - `detect_orphans(state_dir_path="", active_workflow_ids=None)` converts `None` and `[]` both to an empty set (`active_workflow_ids or set()`), so the two cannot be told apart.
  - `expected_dev_loop_id(slug, repo, service)` derives `dev-loop-{owner}-{service}-{N}` from an `issue-N-` slug. For other slugs it returns `None`.
- `orchestrator/temporal/workflows/reconcile.py`, `ReconcileWorkflow.run`:
  - It calls `list_active_dev_loop_ids` under the `orphan-active-ids` patch.
  - If that query fails, it returns `OrphanDetectionResult(total_actionable=0, orphans=[], skipped_reason=...)`.
  - Otherwise it calls `detect_orphans(state_dir_path, active_ids)`.
  - The unpatched replay branch calls `detect_orphans(state_dir_path)` without an active set.
  - `ReconcileWorkflowResult.orphans` is the `OrphanDetectionResult`.
- `orchestrator/temporal/activities/stranded.py` (#412):
  - `_scan` already implements most of a "never started" predicate for `accepted` only: no `pr_url`, no unexpired attempt lease, not `unrunnable`/`blocked`, `execution_authorization` present, outside the `updated_at` grace period, derived DevLoop id not active.
  - It feeds `ImplementSweepWorkflow` (`workflows/implement_sweep.py`, scheduled every 15 minutes at offset 12 in `worker.py`, grace `DEFAULT_IMPLEMENT_SWEEP_GRACE_MINUTES = 20` in `constants.py`), which re-submits the implementer.
  - Its result is not on the reconcile result, and the sweep's own documented rollback is to pause its schedule. That rollback recreates exactly the silent state.
  - `stranded.py` imports `expected_dev_loop_id` from `orphans.py`, so `orphans.py` must not import from `stranded.py` (it would create an import cycle).
- `orchestrator/temporal/activities/gitops_state.py`:
  - `_parse_status_yaml` returns an 8-tuple `_ParsedStatus`: status, pr_url, updated_at, attempt_expires_at, unrunnable, blocked, execution_authorization, unauthorized_reason. The tuple is cached per blob sha in `_blob_cache`.
  - `ProposalStateRef` carries the same fields, all defaulted.
  - `approval.approved_at` is not extracted anywhere in `orchestrator/`. The only approval-related read is `approved_by`, in `proposal_state.execution_authorization`.
- `orchestrator/proposal_state.py`, `execution_authorization(data)` returns `(authorization, unauthorized_reason)` and is fail-closed.
- `docs/adr/005-temporal-reconcile.md`, the "Orphan definition" section, defines the orphan as requiring an open PR.
- Tests: `tests/test_temporal_activities.py` (`test_detect_orphans_*`, `test_orphans_are_detected_from_github_too`), `tests/test_reconcile_workflow.py`, `tests/test_stranded_activity.py`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml` (`env:` block): the worker runs in tenant `admins` (`LIFECYCLE_ROLLOUT_MODE: observe`, `TEMPORAL_NAMESPACE: mctl-agents`). No `IMPLEMENT_SWEEP_*` or never-started env var is set, so code defaults apply. Sibling services in the same directory: `mctl-agents-worker-exec`, `mctl-agents-worker-implement`.
- `$MCTL_GITOPS_ROOT/agents-state/*/proposals/*/.status.yaml`: 120 proposals are `status: accepted`. All 120 have no `approval.approved_by`, no `pr:` and no `attempt:`. They are the legacy, unauthorized shape. 0 proposals are `in-progress`.
  - Consequence: a predicate without the authorization filter would emit 120 signals on its first tick. That is why unauthorized records are only counted.
  - Approved records do carry `approval.approved_at`, e.g. `mctl-academy/.../issue-212-.../.status.yaml: approved_at: '2026-08-29T14:07:18Z'`.
- The three evidence proposals (`mctl-api/proposals/issue-335-*`, `mctl-gitops/proposals/issue-1278-*`, `.github/proposals/issue-99-*`) are now `merged`. Each has `approval.approved_at: '2026-09-19T15:37:12Z'` and `attempt.started_at` between 17:47 and 18:05Z, which confirms the 2h+ gap between approval and claim.
- `mctl_list_services(team="admin")` returned `count: 0`. That is the wrong tenant name, not evidence of absence; the gitops path above is the authoritative source. Live worker logs were not queried.

## Proposed solution

Add a second predicate inside the same activity and return its output in the same result object. The two signals stay separate.

1. **Extract `approved_at` in `gitops_state.py`.**
   - `_parse_status_yaml` also returns `approval.approved_at`, normalized with `str(...)` exactly like `updated_at`. This makes `_ParsedStatus` a 9-tuple.
   - Update the single unpack site in `list_proposal_refs.one`.
   - Add `approved_at: str | None = None` to `ProposalStateRef`.
   - `_blob_cache` is process-local and holds tuples from the same code version, so no migration is needed.

2. **Share the timestamp parser.** Move `stranded._parse_iso` into `gitops_state.py` as `parse_iso` and keep `stranded._parse_iso = parse_iso` as an alias. `orphans.py` can then use it without importing `stranded.py`, which would be circular.

3. **Add the new types and predicate in `orphans.py`.**
   ```python
   NEVER_STARTED_STATUSES = {"accepted", "in-progress"}
   NEVER_STARTED_REASON = "approved, no PR, no live DevLoopWorkflow: execution never started"

   @dataclass(frozen=True)
   class NeverStartedSignal:
       service: str; slug: str; status: str
       approved_at: str | None; age_minutes: int | None; reason: str
   ```
   `OrphanDetectionResult` gains two defaulted fields:
   - `never_started: list[NeverStartedSignal] = field(default_factory=list)`;
   - `never_started_unauthorized: int = 0`.

   A pure function `_classify_never_started(refs, active_ids, threshold_minutes, now)` does the classification. It takes a list of `ProposalStateRef` and returns `(signals, unauthorized_count)`. It applies these rules in order:
   - status not in `NEVER_STARTED_STATUSES`: skip;
   - `pr_url` set: skip (that is the existing orphan predicate's case);
   - `attempt_expires_at > now`: skip;
   - `unrunnable` or `blocked`: skip;
   - `execution_authorization is None`: increment the unauthorized count and skip;
   - `expected_dev_loop_id(slug, None, service)` in `active_ids`: skip;
   - `age = now - parse_iso(approved_at or updated_at)`, falling back to `updated_at` when `approved_at` does not parse. If `age < threshold`: skip. If neither timestamp parses: report with `age_minutes=None` (fail toward visibility).
   - Otherwise: emit a signal.

   `_detect_from_github` calls it on the actionable refs it has already listed, so there are no extra GitHub reads. `_sync_detect_orphans` builds equivalent `ProposalStateRef`s from `_discover_refs` plus `run_shepherd._load_status` (reusing `proposal_state.execution_authorization`/`unrunnable_reason`) and calls the same function. Both paths therefore share one classifier.

   The PR-based loop is untouched. A `pr is None` ref continues there exactly as before.

4. **Keep "active set unknown" distinct from "no active loops".**
   - `detect_orphans` keeps `active_workflow_ids: list[str] | None = None`.
   - It runs the never-started classifier only when `active_workflow_ids is not None`.
   - The unpatched replay branch in `reconcile.py` passes one argument, so it gets an empty `never_started`.
   - The visibility-failure arm already builds an `OrphanDetectionResult` with `skipped_reason`. The new fields default to empty there, and `skipped_reason` covers both signals.
   - No workflow code changes, so there is no new `workflow.patched` marker and no replay risk. The new data travels inside the existing activity result.

5. **Threshold and logging.**
   - In `constants.py`, add `NEVER_STARTED_THRESHOLD_MINUTES_ENV = "NEVER_STARTED_THRESHOLD_MINUTES"`, `DEFAULT_NEVER_STARTED_THRESHOLD_MINUTES = 45` and `never_started_threshold_minutes()` via `_int_env`. The comment should tie the 45 to the sweep's 20-minute grace plus its 15-minute interval.
   - The activity reads the threshold itself (activities may read env). The workflow input does not change.
   - Log `activity.logger.warning("NEVER_STARTED service=%s slug=%s status=%s approved_at=%s age_minutes=%s reason=%s", ...)` per signal.
   - Log one INFO summary line that includes `never_started_unauthorized`.

6. **Docs.** Extend ADR-005's "Orphan definition" with a "Never-started signal" subsection stating the predicate and that it is report-only. Update the `orphans.py` module docstring, which currently defines only the PR orphan.

## Alternatives

- **Loosen the existing predicate** so `pr is None` also yields an `OrphanSignal`. Rejected: the issue asks for the two conditions to stay distinguishable. It would also put 120 legacy records into `orphans` immediately, with no age threshold.
- **Surface `find_stranded_accepted`'s result on the reconcile result** (call it from `ReconcileWorkflow`). Rejected:
  - it adds a new activity command, and therefore a patch marker, to the workflow;
  - its grace period is tuned for submitting, not alerting (20 minutes from `updated_at`, not `approved_at`);
  - it covers `accepted` only;
  - if the sweep code is the regression, a monitor that shares its code path regresses with it. Sharing only the low-level field extraction keeps the detector independent.
- **A new top-level `ReconcileWorkflowResult.never_started` field.** Rejected for now: it requires workflow-code changes behind a new `workflow.patched("never-started")`. Nesting the signal in `OrphanDetectionResult` meets the "alongside the existing orphans" requirement with zero replay surface.

## Platform impact

- **Migrations:** none.
  - All new dataclass fields are defaulted, so older recorded `OrphanDetectionResult` and `ProposalStateRef` payloads still deserialize.
  - The blob cache is in-memory.
- **Backward compatibility:**
  - `OrphanSignal` and its reason string are unchanged.
  - The `detect_orphans` signature is unchanged.
  - Workflow command sequence is unchanged, so existing replay fixtures (`tests/fixtures/histories/reconcile_apply.*.json`) still replay.
- **Resources:** no additional GitHub API calls. One extra dict lookup per status blob, and an O(n) pass over refs that are already listed.
- **Risks and mitigations:**
  - *False positives during the normal approval-to-claim window:* the 45-minute threshold from `approved_at` exceeds the sweep's worst-case claim latency (about 35 minutes).
  - *Legacy noise:* unauthorized records are counted, not listed. All 120 current `accepted` records are unauthorized, so the first tick in production is expected to emit zero signals and `never_started_unauthorized=120`. That count is a useful baseline in itself.
  - *Unknown active set:* never-started is suppressed whenever `active_workflow_ids is None` or the visibility query failed.
  - *Slug without an `issue-N-` prefix* (e.g. an authorized `incident-*`): `expected_dev_loop_id` returns `None`, so no active check applies. That matches `stranded._scan`, which also treats such records as unowned.
