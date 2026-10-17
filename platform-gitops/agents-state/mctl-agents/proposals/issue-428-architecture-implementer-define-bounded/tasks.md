# Tasks: issue-428-architecture-implementer-define-bounded

- [ ] 1. Add `orchestrator/implementation_completion.py` with:
  - frozen dataclasses: `ImplementationCompletion`, `CompletionSubject`, `AttemptBinding`,
    `SourceBinding`, `ProposalBinding`, `VerificationRecord`, `RemainingWorkItem`,
    `StopReason`;
  - closed sets: `OUTCOMES`, `STOP_REASON_CODES`, `VERIFICATION_RESULTS`,
    `VERIFICATION_CLASSIFICATIONS`;
  - bounds: `MAX_VERIFICATION_RECORDS = 32`, `MAX_REMAINING_WORK = 32`,
    `MAX_EVIDENCE_REFS = 32`, leaf caps;
  - `seal()`, `to_dict()`, `from_dict()` and `ImplementationCompletionError`.

  Reuse the canonical-JSON / hash helpers from `context_snapshot.py`
  (`canonical_json`, `hash_bytes`) and the `we_` / `ex-` / `sha256:` validators' patterns
  from `execution_evidence.py`. Redact `detail` / `summary` via `orchestrator/redaction.py`.

  DoD: the module imports nothing from `run_implementer` / `run_shepherd`; the `complete` /
  `incomplete` invariants are enforced at construction; unknown and forbidden keys are
  rejected; `completion_id` is deterministic.
- [ ] 2. (depends on 1) Add `completion_from_result()` and `_AttemptObservations` to
  `orchestrator/run_implementer.py`. Compute `proposal_digest` at attempt start (next to
  the `attempt = {...}` dict in `_implement_one`) and `review_bundle_digest` in
  `_review_feedback_one`. Collect `base_sha` / `head_sha` and the orchestrator-side
  verification records (`commits_present`, `chart_major_guard`, `push_succeeded`,
  `claim_valid_at_push`), plus non-required ledger-observed commands from
  `CommandBudgetLedger`, with classification only.

  DoD: every exit code 0, 1, 42-54 and every `ImplementResult` arm maps to exactly one
  (outcome, stop_reason) pair per the design table; there is one mapping function.
- [ ] 3. (depends on 2) Emit once per attempt:
  - one `try/finally` emission point in `_implement_one` and `_review_feedback_one`;
  - pass `completion=` through `update_status_yaml` on the existing `implemented`,
    `_mark_needs_triage` and hand-back writes (projection shape per design);
  - add the `--completion-out PATH` argparse flag with a best-effort bounded writer
    mirroring `_write_refusal_out`;
  - add `_completion_write_allowed(existing, new)` combined with `_status_is_still_ours`;
  - skip the projection when the claim check fails.

  DoD: existing exit codes, `--refusal-out` payloads and status values are byte-identical
  in the existing tests.
- [ ] 4. (depends on 1) Extend the optional `remaining` field of `RefusalMarker` /
  `_read_refusal_marker`: a bounded list of `{item_id, summary}`, validated like `reason`.
  When present on an otherwise successful push it yields `incomplete`.

  DoD: a marker without `remaining` behaves exactly as today.
- [ ] 5. (depends on 3) Shepherd: in `run_shepherd.py`'s follow-up invocation (near the
  `--refusal-out` wiring, ~line 3215), pass `--completion-out`. Add `_read_completion(path,
  expected_attempt_id)` and `_followup_kind_from_completion()`. Log
  `completion-disagreement` against `_followup_exit_codes()`. Gate trust behind
  `SHEPHERD_TRUST_COMPLETION` (default off). Record `completion_id` in the shepherd's
  status notes.

  DoD: with the flag off, charging behaviour is unchanged; with it on, a stale or mismatched
  completion falls back to the exit code.
- [ ] 6. (depends on 3) Temporal:
  - add the `read_proposal_completion(service, slug)` activity in
    `orchestrator/temporal/activities/proposals.py` and register it in `worker.py`;
  - add the optional `completion_id`, `completion_outcome` and `completion_stop_reason` to
    `ExecutionRecord`, sent through `record_execution`'s `optional` dict;
  - in `dev_loop._implement` and `implement_sweep`, read and record the completion behind
    `workflow.patched("implement-completion")`;
  - expose `completion_outcome` on `ImplementExecutionState`;
  - make no control-flow change.

  DoD: an `attempt_id` that does not equal the Argo workflow UID is treated as absent;
  existing replay fixtures still replay.
- [ ] 7. (depends on 1-6) Docs: add `docs/adr/021-implementation-completion-contract.md`
  (scope statement, outcome and stop-reason tables, replay rules, carrier boundary,
  non-authorities list) and a pointer in `docs/temporal-flow.md`.

  DoD: the ADR says explicitly "implementer-phase completion contract — not an independent
  review verdict, not approval, not another DevLoop".

## Tests

- [ ] T1. `tests/test_implementation_completion.py`:
  - round-trip `to_dict` / `from_dict` for every outcome;
  - `content_hash` / `completion_id` are stable across key order and `created_at`;
  - unknown keys and forbidden keys (`approved`, `review_verdict`, `merge`, `release`,
    `owner`, `extend_budget`) are rejected;
  - unsupported `api_version` is rejected;
  - list bounds are enforced;
  - `complete` with a failed required check, non-empty `remaining_work` or a null head is
    rejected;
  - `incomplete` with empty `remaining_work` is rejected;
  - redaction of `detail`.
- [ ] T2. `tests/test_run_implementer_completion.py`: a parametrized table over every
  exit code and `ImplementResult` arm asserting the (outcome, stop_reason) pair. A test
  also fails if a new `EXIT_*` constant is added without a mapping.
- [ ] T3. Replay / idempotency:
  - re-sealing the same attempt yields the same `completion_id`;
  - re-projecting the same completion is a no-op;
  - a second, different completion under the same `attempt_id` is refused (in particular
    `budget_exhausted` → `complete` and `harness_failure` → `complete`);
  - a completion from an older `attempt_id` is refused when status holds a newer one.
- [ ] T4. Stale claim: `_check_claim_or_raise` raising at emission produces no
  `.status.yaml` projection and a `--completion-out` record with `harness_failure` /
  `fenced`.
- [ ] T5. Shepherd: `_read_completion` rejects oversize, invalid and mismatched-attempt
  files; the kind derivation matches the design table; disagreement with the exit code
  logs and uses the exit code; flag off = no behaviour change.
- [ ] T6. Temporal: `record_execution` sends the new optional keys and retries without
  them on 4xx (extend the existing state-activity tests). There are workflow tests for
  `success` + `incomplete` (observed, not failing) and for a stale `attempt_id` (absent).
  A replay of the existing `tests/fixtures/histories/dev_loop_*.json` and
  `implement_sweep.json` passes under the new patch marker.
- [ ] T7. Backward compatibility: existing `tests/test_run_implementer_*.py` and shepherd
  tests pass unchanged; `.status.yaml` without `completion:` parses everywhere it did
  before.

## Rollback

Every piece is additive and independently revertible:
- Set `SHEPHERD_TRUST_COMPLETION` off (the default) to return the shepherd to exit-code
  classification immediately.
- Revert the PR to remove `--completion-out` and the projection. A stray `completion:` key
  left in `.status.yaml` is ignored by every reader, so no data cleanup is required.
- The Temporal side sits behind `workflow.patched("implement-completion")`. To remove it,
  first ship a build that keeps the patch branch as a no-op until in-flight DevLoops
  drain, then delete it, following the existing `implement-outcome` patch practice.
- `record_execution`'s optional keys are dropped by mctl-api today, and the existing 4xx
  fallback protects the row if that changes.
