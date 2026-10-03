# Tasks: issue-428-architecture-implementer-define-bounded

- [ ] 1. Write `docs/adr/012-implementation-completion-contract.md` — the decision,
      the outcome vocabulary table, the lifecycle-boundary table, the replay rules,
      and an opening paragraph stating in as many words that this is an
      implementer-phase completion contract, not an independent review verdict and
      not another DevLoop. Cross-reference ADR-009 (schema precedent), ADR-010
      (§6 fencing, §7 projection rule, §8 idempotency), ADR-011 (envelope), #395,
      #418, #423. — DoD: ADR lands with `Status: proposed`, matches the file it
      documents field-for-field, and is reachable from `docs/adr/`.

- [ ] 2. Add `orchestrator/implementation_completion.py` (depends on 1) —
      stdlib-only frozen dataclasses `ImplementationCompletion`, `WorkItemRef`,
      `AttemptRef`, `SourceRef`, `StopReason`, `VerificationRecord`,
      `RemainingWork`, `EvidenceRef`; `API_VERSION =
      "implementation.mctl.ai/v1alpha1"`, `KIND = "ImplementationCompletion"`,
      `SUPPORTED_API_VERSIONS`; closed `OUTCOMES` / `STOP_REASON_CODES` /
      `VERIFICATION_RESULTS` frozensets; `MAX_VERIFICATION_RECORDS`,
      `MAX_REMAINING_WORK`, `MAX_EVIDENCE_REFS`, `MAX_EVIDENCE_REF_LENGTH`,
      `MAX_MESSAGE_LENGTH`; `to_dict` / `from_dict` / `validate` /
      `seal` / `recompute_content_hash`; `ImplementationCompletionError`.
      Hashing reuses `context_snapshot.hash_bytes` and `canonical_json` — no
      second hash convention. — DoD: `uv run mypy .` and `uv run ruff check .`
      clean; no import of `claude_agent_sdk`, `httpx` or `yaml`; module is not
      imported by any production path yet.

- [ ] 3. Add the replay/staleness functions to the same module (depends on 2) —
      `idempotency_key_for_completion(...)` delegating to
      `lifecycle.contract.idempotency_key_for` with
      `action="implementation-complete"`; `reconcile(prior, new) -> "duplicate" |
      "accepted" | "refused"`; `staleness_of(doc, *, observed_head_sha,
      claim_verdict, status_attempt_id) -> "fresh" | "stale"`;
      `effective_outcome(doc, staleness)`; `reconcile_with_argo(argo_outcome,
      doc)` consuming `implement_outcome.Outcome`. — DoD: every disagreement
      resolves to the non-complete side, and no function can return `complete`
      for an input that did not already carry it.

- [ ] 4. Add `followup_kind_for(outcome, stop_reason_code)` beside
      `run_shepherd._followup_code_sets()` (depends on 3) — mapping the six
      outcomes onto the existing `FollowupKind` literal. The shepherd is NOT
      rewired to prefer the document in this proposal. — DoD: the function exists,
      is typed `-> FollowupKind`, and T4 proves it agrees with the current
      exit-code classification for every sentinel code.

- [ ] 5. Add `--completion-out <path>` to `orchestrator/run_implementer.py`
      (depends on 3) — argparse flag next to `--refusal-out` (`:3592`), a
      `_build_completion(...)` helper, and a `_write_completion_out(path, doc)`
      with the same best-effort discipline as `_write_refusal_out` (`:444`):
      broad except, warn to stderr, never change the exit code. Emit from the
      `implemented` arm (`:3302`), `_mark_needs_triage` (`:2772`), the refusal
      arms (`:3710-3725`) and the `--review-feedback` exit path (`:3709/3726`).
      Emit NOTHING on the `EXIT_FENCED` / `EXIT_CLAIM_REFUSED` arms. — DoD: with
      the flag absent, behaviour is byte-identical to today; with it present, one
      sealed document is written whose `stop_reason.exit_code` equals the process
      exit code.

- [ ] 6. Extend `ExecutionRecord` in `orchestrator/temporal/activities/state.py`
      (depends on 2) — trailing `attempt_id: str = ""` and
      `completion: dict[str, Any] | None = None`, posted as optional JSON keys in
      `record_execution`'s body. No new activity call is added to
      `DevLoopWorkflow._implement`, so no `workflow.patched()` marker is needed
      (an extra argument to an existing activity is replay-invisible; an extra
      activity call is not). — DoD: `tests/test_workflow_replay.py` and
      `tests/test_implement_sweep_replay.py` stay green with the existing
      fixtures, and all four existing `_record*` call sites compile unchanged.

- [ ] 7. Add the bounded `.status.yaml` projection helper (depends on 5) —
      `completion_projection(doc) -> dict` returning only `{api_version,
      completion_id, content_hash, outcome, attempt_id, stop_reason_code,
      verification: {passed, failed, unknown, required_failed}}`, written through
      `update_status_yaml` behind the existing `_status_is_still_ours`
      compare-and-swap, carrying a `# derived, not authoritative` marker. — DoD:
      no timing, token-count or log-excerpt field can appear in the projection,
      proved by T7.

- [ ] 8. Add a fixture and a generator (depends on 2) —
      `tests/fixtures/completion/implementation-completion.json` plus the seal
      script path, mirroring `tests/fixtures/context/investigator-snapshot.json`.
      — DoD: the fixture round-trips through `from_dict`/`to_dict` with a stable
      `content_hash`, and regenerating it produces no diff.

- [ ] 9. Update `LLMS.md` and `docs/agent-inventory.yaml` (depends on 1) with one
      paragraph naming the contract and its boundary. — DoD: `uv run pytest
      tests/test_agent_inventory.py` and `tests/test_diagram_facts.py` pass.

## Tests

`tests/test_implementation_completion.py` unless noted.

- [ ] T1. Serialization is pinned: the fixture round-trips byte-stably;
      `content_hash` is independent of `created_at`; `completion_id` equals
      `"ic-" + content_hash[7:23]`; an unknown key, an unsupported `api_version`,
      an unsupported `kind` and an out-of-vocabulary `outcome` each raise
      `ImplementationCompletionError` rather than falling back to a default shape.
- [ ] T2. Semantic validation, proved by mutation in both directions:
      `complete` with a failing `required_for_completion` verification is
      rejected; `incomplete` with empty `remaining_work` is rejected; `complete`
      with a non-null `stop_reason` is rejected; a non-`complete` outcome with a
      null `stop_reason` is rejected.
- [ ] T3. Bounds: exceeding `MAX_VERIFICATION_RECORDS`, `MAX_REMAINING_WORK`,
      `MAX_EVIDENCE_REFS`, `MAX_EVIDENCE_REF_LENGTH` or `MAX_MESSAGE_LENGTH`
      raises rather than truncating — so a payload cannot be smuggled through an
      evidence reference.
- [ ] T4. Equivalence: for every sentinel in `run_implementer` (42, 43, 44, 46,
      47, 48, 49, 50, 0, 1), the outcome `_build_completion` derives maps through
      `followup_kind_for` to exactly the `FollowupKind` that
      `_followup_code_sets()` / `_refusal_codes()` / `_fenced_codes()` produce
      today. A new exit code with no mapping fails this test.
- [ ] T5. Replay and idempotency: sealing the same attempt twice yields identical
      `completion_id`, `content_hash` and `idempotency_key`; `reconcile` returns
      `duplicate` for identical content, and `refused` for the same `attempt_id`
      with a different outcome — asserted specifically for
      `budget_exhausted -> complete` and `harness_failure -> complete`; a new
      `attempt_id` is `accepted`. No `uuid` import in the module (same assertion
      style as `tests/test_run_implementer_claims.py`).
- [ ] T6. Stale-attempt fail-closed: a moved `head_sha`, a `CLAIM_FENCED` /
      `CLAIM_HELD_BY_OTHER` / `CLAIM_UNKNOWN` / `CLAIM_UNCLAIMED` verdict, and a
      `.status.yaml` attempt block naming another attempt each classify `stale`
      and downgrade `complete` to `harness_failure` with
      `stop_reason.code = "stale-attempt"`. `reconcile_with_argo` resolves every
      disagreement to the non-complete side, including
      `("finalization", complete)` and `("execution", complete)`.
- [ ] T7. Lifecycle boundary: no dataclass field name in the module matches
      `approve|approval|merge|release|authoriz|grant|review_clean|lease|owner_state`;
      and a mutation test that flips a document to `complete` leaves
      `proposal_state.human_approval_satisfied`,
      `proposal_state.execution_authorization` and the shepherd's merge path
      returning exactly what they returned before.
- [ ] T8. No-document fallback: with no completion available, the shepherd's
      existing exit-code classification and `implement_outcome.classify` are used
      unchanged, and nothing synthesizes `complete`.
- [ ] T9. `tests/test_run_implementer_refusal.py` extension: `--completion-out`
      absent leaves every existing exit code and status write unchanged;
      `--completion-out` pointing at an unwritable path warns and still exits with
      the correct sentinel; the fenced/claim-refused arms write no document.
- [ ] T10. `tests/test_worker_isolation.py` still passes with
      `implementation_completion` importable from the Temporal worker.

## Rollback

Every step is additive and inert, so rollback is removal rather than migration.

1. **Fastest revert (no deploy coordination):** stop passing
   `--completion-out` — nothing does yet, and without it `run_implementer`
   behaves exactly as before. The contract module, ADR and tests can stay in
   place with zero runtime effect.
2. **Full revert:** delete `orchestrator/implementation_completion.py`,
   `docs/adr/012-implementation-completion-contract.md`, the fixture, the
   `followup_kind_for` helper and the `--completion-out` flag, and drop the two
   trailing fields from `ExecutionRecord`. No database migration, no gitops
   schema change, no Temporal patch marker was added, so no history is stranded
   and `dev_loop_full.*.json` / `implement_sweep.json` replay unchanged.
3. **Projection revert:** the `.status.yaml` block is derived and
   preserved-by-default; removing the writer stops new writes, and existing
   blocks are inert because nothing reads them for a decision (T7). They can be
   left in place or swept by the next ordinary status write.
4. **If mctl-api rejects the extra JSON keys** (rather than ignoring them),
   `record_execution` starts failing — the workflow already treats that as
   best-effort (`except ActivityError` → warn and continue), but the correct fix
   is to drop the two fields from the POST body, which is a one-line change
   isolated to `activities/state.py`.
