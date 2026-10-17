# Tasks: issue-428-architecture-implementer-define-bounded

## Delivery split

The work ships as three mctl-agents PRs. Each PR can be reviewed on its own, and they merge
in this order:

- **PR 1 (contract and emission):** tasks 1, 2, 3, 4, 7. Tests T1-T4, T7.
  - Covers the schema module, `completion_from_result`, emission and `.status.yaml`
    projection, the primary / fallback authority rule, the `RefusalMarker.remaining`
    extension, and ADR 021.
  - It changes no consumer behaviour.
- **PR 2 (shepherd shadow):** task 5. Test T5.
  - Covers shepherd consumption in shadow mode behind `SHEPHERD_TRUST_COMPLETION`
    (default off).
  - Depends on PR 1 being merged.
- **PR 3 (Temporal observe-only):** task 6. Test T6.
  - Covers the `read_proposal_completion` activity, the `ExecutionRecord` fields, and the
    `implement-completion` patch.
  - Depends on PR 1 being merged. Independent of PR 2.

Companion, in a separate repo: task 8 (mctl-gitops, additive). It may merge before or
after PR 1.

## PR 1: contract, emission, projection, fallback authority, ADR

- [ ] 1. Add `orchestrator/implementation_completion.py` with:
  - frozen dataclasses `ImplementationCompletion`, `CompletionSubject`, `AttemptBinding`
    (with `run_id` and `step: primary|fallback`), `SourceBinding`, `ProposalBinding`,
    `VerificationRecord`, `RemainingWorkItem`, `StopReason`;
  - the `CompletionSummary` projection type and the pure
    `select_authoritative(primary_summary | None, fallback) -> projection` function;
  - closed sets `OUTCOMES`, `STOP_REASON_CODES` (with `gates_passed` for `complete`),
    `VERIFICATION_RESULTS`, `VERIFICATION_CLASSIFICATIONS`, and
    `REQUIRED_CHECKS_V1ALPHA1 = {commits_present, chart_major_guard, push_succeeded,
    claim_valid_at_push}`;
  - bounds of 32 per list, plus leaf caps;
  - `seal()`, `to_dict()`, `from_dict()`, `ImplementationCompletionError`.

  Reuse `canonical_json` / `hash_bytes` from `context_snapshot.py` and the validator
  patterns from `execution_evidence.py`. Redact via `orchestrator/redaction.py`.

  The module docstring states verbatim that in v1alpha1 `complete` means "the attempt
  pushed a head that passed the orchestrator gates", not "the approved scope is
  implemented", and names follow-up F1 (task-coverage verification).

  DoD:
  - the module imports nothing from `run_implementer` / `run_shepherd`;
  - the invariants are enforced at construction;
  - forbidden keys are rejected;
  - `run_id` and `step` are part of the hash.
- [ ] 2. (depends on 1) In `orchestrator/run_implementer.py`, add
  `completion_from_result()` and `_AttemptObservations`:
  - `proposal_digest` at attempt start;
  - `review_bundle_digest` in `_review_feedback_one`;
  - `base_sha` / `head_sha`;
  - the four required gate records;
  - non-required `CommandBudgetLedger` entries;
  - `run_id` from `WORKFLOW_NAME`, and `step` from `IS_FALLBACK`.

  DoD: every exit code 0, 1, 42-54 and every `ImplementResult` arm maps to exactly one
  (outcome, stop_reason) pair. There is one mapping function.
- [ ] 3. (depends on 2) Emit once per step:
  - one `try/finally` emission point after claim acquisition in `_implement_one` and
    `_review_feedback_one`;
  - `completion=` passed through `update_status_yaml` on the existing `implemented`,
    `_mark_needs_triage`, `_mark_rate_limited` and hand-back writes, using the
    `completion: {run_id, authoritative, other?, primary_observed}` projection;
  - a `--completion-out PATH` flag with a bounded writer;
  - `_completion_write_allowed(existing, new)` keyed on `(run_id, step, attempt_id)`,
    combined with `_status_is_still_ours`;
  - no projection when the claim check fails;
  - when `step == fallback`, `_load_prior_handoff(Path("/tmp/prior-state"), ref, run_id)`
    reads the primary's `completion.authoritative` (bounded, validated; a `run_id`
    mismatch counts as absent) and applies `select_authoritative`.

  DoD:
  - existing exit codes, `--refusal-out` payloads and status values are byte-identical in
    the existing tests;
  - a missing `/tmp/prior-state` yields `primary_observed: false`.
- [ ] 4. (depends on 1) Extend `RefusalMarker` / `_read_refusal_marker` with an optional
  bounded `remaining: [{item_id, summary}]`. When it is present on an otherwise successful
  push, the outcome is `incomplete`.

  DoD: a marker without `remaining` behaves exactly as it does today.
- [ ] 7. (depends on 1-4) Add `docs/adr/021-implementation-completion-contract.md`
  covering:
  - the scope statement;
  - the outcome / stop-reason table;
  - the v1alpha1 meaning of `complete` (orchestrator gates only; no check against
    `tasks.md`) and follow-up F1;
  - the primary / fallback authority rule, including that `status` and
    `completion.authoritative` may differ after a failed fallback;
  - the replay key;
  - the carrier boundary;
  - the non-authorities list.

  DoD: the ADR says explicitly "implementer-phase completion contract — not an independent
  review verdict, not approval, not another DevLoop".

## PR 2: shepherd consumption in shadow mode

- [ ] 5. (depends on PR 1) In `run_shepherd.py`:
  - pass `--completion-out` next to `--refusal-out`;
  - add `_read_completion(path, expected_run_id)` and `_followup_kind_from_completion()`;
  - always log `completion-disagreement` against `_followup_exit_codes()`;
  - change charging only when `SHEPHERD_TRUST_COMPLETION` is on (default off);
  - record `completion_id` in the status notes;
  - append a "Shepherd consumption" section to ADR 021.

  DoD:
  - with the flag off, charging is unchanged;
  - with it on, a stale, mismatched or absent completion falls back to the exit code;
  - the merge decision does not read `outcome`.

## PR 3: Temporal observe-only

- [ ] 6. (depends on PR 1) Temporal:
  - add `read_proposal_completion(service, slug)` in
    `orchestrator/temporal/activities/proposals.py` and register it in `worker.py`;
  - add the optional `completion_id`, `completion_outcome`, `completion_stop_reason` and
    `completion_step` to `ExecutionRecord`, sent through `record_execution`'s `optional`
    dict;
  - in `dev_loop._implement` and `implement_sweep`, read `completion.authoritative`
    behind `workflow.patched("implement-completion")`, accepting it only when
    `completion.run_id == result.workflow_name`;
  - expose `ImplementExecutionState.completion_outcome`;
  - make no control-flow change;
  - add a pointer in `docs/temporal-flow.md` and a section in ADR 021.

  DoD:
  - a mismatched `run_id` counts as absent;
  - a `step: fallback, primary_observed: false` record is recorded with its step, never
    relabelled as the primary;
  - the existing replay fixtures still replay.

## Companion (mctl-gitops, separate PR)

- [ ] 8. In `argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`, add an
  optional input artifact to `run-implementer`:
  - S3 key `{{workflow.name}}/agents-state.tgz`, the existing literal key;
  - `optional: true`;
  - unpacked to `/tmp/prior-state`.

  No other change: no step-order change, no `outputs.parameters`.

  DoD:
  - the primary step (key absent) runs unchanged;
  - the fallback pod sees the primary's handoff.

## Tests

- [ ] T1. (PR 1) `tests/test_implementation_completion.py`:
  - round-trip for every outcome;
  - hash stable across key order and `created_at`;
  - the hash differs between `step: primary` and `step: fallback` with the same
    `attempt_id`;
  - unknown and forbidden keys (`approved`, `review_verdict`, `merge`, `release`,
    `owner`, `extend_budget`) are rejected;
  - list bounds are enforced;
  - `complete` invariants: a failed required check, remaining work, or a null head is
    rejected;
  - `incomplete` with empty `remaining_work` is rejected;
  - redaction;
  - the required-check set equals the four gates;
  - the docstring contains the v1alpha1 `complete` statement.
- [ ] T2. (PR 1) `tests/test_run_implementer_completion.py`: a parametrized table over
  every exit code and `ImplementResult` arm. The test fails if a new `EXIT_*` constant is
  added without a mapping.
- [ ] T3. (PR 1) Primary / fallback authority. Both scenarios are driven through
  `_implement_one` twice, with `WORKFLOW_NAME` fixed, `IS_FALLBACK` false then true, and
  the primary's staged `.status.yaml` copied into a tmp `prior-state` dir. Each scenario
  is run with `WORKFLOW_UID` set (same `attempt_id`) and unset (different `HOSTNAME`):
  - T3a. **The primary fails, then the fallback fails.** The primary ends
    `deterministic_failure` / `no_commits`. The fallback ends `harness_failure` or
    `budget_exhausted` / `rate_limited`. Assert:
    - `completion.authoritative` is the primary's record;
    - `completion.other.relation == fallback`, with the fallback's outcome;
    - `primary_observed: true`.
  - T3b. **The primary fails, then the fallback succeeds.** The primary ends
    `harness_failure`; the fallback ends `complete` / `gates_passed`. Assert:
    - `authoritative` is the fallback's record;
    - `other.relation == superseded`, with the primary's outcome.
  - T3c. The fallback runs with no `prior-state`. Assert `primary_observed: false` and
    that the fallback's own record is authoritative.
  - T3d. `prior-state` from a different `run_id` is treated as absent.
- [ ] T4. (PR 1) Replay and staleness:
  - re-sealing the same step yields the same `completion_id`;
  - re-projecting it is a no-op;
  - a different completion under the same `(run_id, step, attempt_id)` is refused
    (including `budget_exhausted` → `complete` and `harness_failure` → `complete`);
  - an older attempt is refused when status holds a newer one;
  - `_check_claim_or_raise` raising at emission produces no projection, and a
    `--completion-out` record of `harness_failure` / `fenced`.
- [ ] T5. (PR 2) Shepherd:
  - `_read_completion` rejects oversize, invalid and mismatched files;
  - the kind table is followed;
  - a disagreement is logged and the exit code is used;
  - with the flag off, there is no behaviour change.
- [ ] T6. (PR 3) Temporal:
  - `record_execution` sends the new optional keys and retries without them on a 4xx;
  - `success` + non-`complete` is observed and does not fail;
  - a `run_id` mismatch counts as absent;
  - the existing `tests/fixtures/histories/dev_loop_*.json` and `implement_sweep.json`
    replay under the new patch.
- [ ] T7. (PR 1, rerun in PR 2 and PR 3) Backward compatibility:
  - the existing `tests/test_run_implementer_*.py` and shepherd tests pass unchanged;
  - a `.status.yaml` without `completion:` parses everywhere.

## Rollback

Each PR is additive and can be reverted independently, in reverse merge order:
- **PR 2:** turn `SHEPHERD_TRUST_COMPLETION` off (the default) to return to exit-code
  classification at once. Revert the PR to remove the shadow logging.
- **PR 3:** ship a build that keeps the `implement-completion` patch branch as a no-op
  until in-flight DevLoops drain, then delete it (the existing patch-retirement practice).
  mctl-api drops the unknown optional keys, and the 4xx fallback protects the row.
- **PR 1:** revert it to remove `--completion-out`, the projection and the fallback
  authority logic. A stray `completion:` key left in `.status.yaml` is ignored by every
  reader, so no data cleanup is needed.
- **Task 8 (mctl-gitops):** revert the optional input artifact. The fallback then
  projects `primary_observed: false`, or nothing at all if PR 1 is also reverted.
