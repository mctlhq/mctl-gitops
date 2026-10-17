# Tasks: issue-428-architecture-implementer-define-bounded

**This DevLoop implements PR 1 only. PR 2 and PR 3 are separate follow-up work items and
must not be implemented in this attempt.**

In scope for this attempt: tasks 1, 2, 3, 4 and 7; tests T1, T2, T3, T4 and T7. One branch,
one PR.

Out of scope for this attempt (kept below as reference only):
- PR 2, shepherd shadow consumption (task 5, T5): mctlhq/mctl-agents#679 — own DevLoop
  after PR 1 merges.
- PR 3, Temporal observe-only (task 6, T6): mctlhq/mctl-agents#680 — own DevLoop after
  PR 1 merges.
- Task 8, mctl-gitops optional prior-state input: mctlhq/mctl-gitops#1947 — done outside
  this DevLoop.

Do not modify `orchestrator/run_shepherd.py`, `orchestrator/temporal/**`, or any
mctl-gitops file in this attempt.

## PR 1 (this attempt): contract, emission, projection, fallback authority, ADR

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
  patterns from `execution_evidence.py`. Redact via `orchestrator/redaction.py`. The
  module docstring states verbatim that in v1alpha1 `complete` means "the attempt pushed a
  head that passed the orchestrator gates", not "the approved scope is implemented", and
  names follow-up F1 (task-coverage verification).

  DoD: the module imports nothing from `run_implementer` / `run_shepherd`; invariants are
  enforced at construction; forbidden keys are rejected; `run_id` and `step` are part of
  the hash.
- [ ] 2. (depends on 1) In `orchestrator/run_implementer.py`, add
  `completion_from_result()` and `_AttemptObservations`:
  - `proposal_digest` at attempt start via `proposal_state.proposal_content_digest`;
  - `review_bundle_digest` in `_review_feedback_one`;
  - `base_sha` / `head_sha`;
  - the four required gate records;
  - non-required `CommandBudgetLedger` entries (classification only);
  - `run_id` from `WORKFLOW_NAME`, `step` from `IS_FALLBACK`.

  DoD: every exit code 0, 1, 42-54 and every `ImplementResult` arm maps to exactly one
  (outcome, stop_reason) pair through one mapping function.
- [ ] 3. (depends on 2) Emit once per step:
  - one `try/finally` emission point after claim acquisition in `_implement_one` and
    `_review_feedback_one`; emission errors are logged and never change the exit code;
  - `completion=` passed through `update_status_yaml` on the existing `implemented`,
    `_mark_needs_triage`, `_mark_rate_limited` and hand-back writes, using the
    `completion: {api_version, run_id, authoritative, other?, primary_observed}`
    projection;
  - a `--completion-out PATH` flag with a bounded writer (mirrors `_write_refusal_out`);
  - `_completion_write_allowed(existing, new)` keyed on `(run_id, step, attempt_id)`,
    combined with `_status_is_still_ours`;
  - no projection when the claim check fails;
  - when `step == fallback`, `_load_prior_handoff(Path("/tmp/prior-state"), ref, run_id)`
    reads the primary's `completion.authoritative` (bounded, validated; a `run_id`
    mismatch or non-`primary` step counts as absent) and applies `select_authoritative`.

  DoD: existing exit codes, `--refusal-out` payloads and status values are byte-identical
  in the existing tests; a missing `/tmp/prior-state` yields `primary_observed: false`.
- [ ] 4. (depends on 1) Extend `RefusalMarker` / `_read_refusal_marker` with an optional
  bounded `remaining: [{item_id, summary}]`. When present on an otherwise successful push,
  the outcome is `incomplete`.

  DoD: a marker without `remaining` behaves exactly as it does today.
- [ ] 7. (depends on 1-4) Add `docs/adr/021-implementation-completion-contract.md`
  covering: the scope statement; the outcome / stop-reason table; the v1alpha1 meaning of
  `complete` (orchestrator gates only; no check against `tasks.md`) and follow-up F1; the
  primary / fallback authority rule, including `primary_observed: false` and that
  `status` and `completion.authoritative` may differ after a failed fallback; the replay
  key; the carrier boundary; the non-authorities list; a "Consumers (follow-up)" section
  linking #679, #680 and mctl-gitops#1947.

  DoD: the ADR says explicitly "implementer-phase completion contract — not an independent
  review verdict, not approval, not another DevLoop".

## Reference only — OUT OF SCOPE for this attempt

These items are kept for the follow-up DevLoops. Do not implement them here.

- [ ] 5. (PR 2, mctlhq/mctl-agents#679; depends on PR 1 merged) In `run_shepherd.py`: pass
  `--completion-out` next to `--refusal-out`; add `_read_completion(path,
  expected_run_id)` and `_followup_kind_from_completion()`; always log
  `completion-disagreement` against `_followup_exit_codes()`; change charging only when
  `SHEPHERD_TRUST_COMPLETION` is on (default off); record `completion_id` in status notes;
  append a "Shepherd consumption" section to ADR 021. DoD: flag off means unchanged
  charging; with it on, a stale, mismatched or absent completion falls back to the exit
  code; the merge decision does not read `outcome`.
- [ ] 6. (PR 3, mctlhq/mctl-agents#680; depends on PR 1 merged) Temporal: add
  `read_proposal_completion(service, slug)` in
  `orchestrator/temporal/activities/proposals.py`, registered in `worker.py`; add optional
  `completion_id`, `completion_outcome`, `completion_stop_reason`, `completion_step` to
  `ExecutionRecord`; in `dev_loop._implement` and `implement_sweep`, read
  `completion.authoritative` behind `workflow.patched("implement-completion")`, accepted
  only when `completion.run_id == result.workflow_name`; expose
  `ImplementExecutionState.completion_outcome`; no control-flow change; pointer in
  `docs/temporal-flow.md` and an ADR 021 section. DoD: mismatched `run_id` is absent; a
  `step: fallback, primary_observed: false` record keeps its step; existing replay
  fixtures still replay.
- [ ] 8. (mctlhq/mctl-gitops#1947, outside this DevLoop) In
  `argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`, add an
  `optional: true` input artifact to `run-implementer` at the existing key
  `{{workflow.name}}/agents-state.tgz`, unpacked to `/tmp/prior-state`. No step-order
  change, no `outputs.parameters`. DoD: the primary step runs unchanged; the fallback pod
  sees the primary's handoff.

## Tests

In scope for this attempt:

- [ ] T1. `tests/test_implementation_completion.py`:
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
  - the docstring contains the v1alpha1 `complete` statement;
  - `select_authoritative` truth table (all four rows).
- [ ] T2. `tests/test_run_implementer_completion.py`: a parametrized table over every exit
  code and `ImplementResult` arm. Fails if a new `EXIT_*` constant is added without a
  mapping.
- [ ] T3. Primary / fallback authority, driven through `_implement_one` twice with
  `WORKFLOW_NAME` fixed, `IS_FALLBACK` false then true, and the primary's staged
  `.status.yaml` copied into a tmp `prior-state` dir. Each scenario runs with
  `WORKFLOW_UID` set (same `attempt_id`) and unset (different `HOSTNAME`):
  - T3a. **Primary fails, then fallback fails.** Primary ends `deterministic_failure` /
    `no_commits`; fallback ends `harness_failure` or `budget_exhausted` / `rate_limited`.
    Assert `completion.authoritative` is the primary's record, `completion.other.relation
    == fallback` with the fallback's outcome, and `primary_observed: true`.
  - T3b. **Primary fails, then fallback succeeds.** Primary ends `harness_failure`;
    fallback ends `complete` / `gates_passed`. Assert `authoritative` is the fallback's
    record and `other.relation == superseded` with the primary's outcome.
  - T3c. Fallback with no `prior-state`: `primary_observed: false`, fallback's own record
    authoritative.
  - T3d. `prior-state` from a different `run_id` is treated as absent.
- [ ] T4. Replay and staleness:
  - re-sealing the same step yields the same `completion_id`; re-projecting is a no-op;
  - a different completion under the same `(run_id, step, attempt_id)` is refused
    (including `budget_exhausted` → `complete` and `harness_failure` → `complete`);
  - an older attempt is refused when status holds a newer one;
  - `_check_claim_or_raise` raising at emission produces no projection and a
    `--completion-out` record of `harness_failure` / `fenced`.
- [ ] T7. Backward compatibility: the existing `tests/test_run_implementer_*.py` and
  shepherd tests pass unchanged; a `.status.yaml` without `completion:` parses everywhere;
  a `RefusalMarker` without `remaining` behaves as before.

Reference only, out of scope for this attempt:

- [ ] T5. (#679) Shepherd: `_read_completion` rejects oversize, invalid and mismatched
  files; kind table; disagreement logged and exit code used; flag off means no change.
- [ ] T6. (#680) Temporal: `record_execution` sends the optional keys and retries without
  them on 4xx; `success` + non-`complete` observed, not failed; `run_id` mismatch is
  absent; existing `tests/fixtures/histories/dev_loop_*.json` and `implement_sweep.json`
  replay under the new patch.

## Rollback

PR 1 is additive and changes no consumer behaviour. Revert the PR to remove the schema
module, `--completion-out`, the projection, the fallback authority logic and ADR 021.
Nothing reads `--completion-out` yet (the shepherd consumer is #679), and a stray
`completion:` key left in `.status.yaml` is ignored by every existing reader, so no data
cleanup is needed. If #679 or #680 has merged by then, revert those first (they depend on
PR 1). mctl-gitops#1947 can stay deployed after a revert: an unused optional input at
`/tmp/prior-state` is harmless.
