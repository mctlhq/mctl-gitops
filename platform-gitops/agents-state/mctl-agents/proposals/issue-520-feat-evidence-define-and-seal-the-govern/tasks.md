# Tasks: issue-520-feat-evidence-define-and-seal-the-govern

- [ ] 1. Extract the credential/value screen from `orchestrator/tracing_sdk.py` into
      a new stdlib-only `orchestrator/redaction.py` (`_CREDENTIAL_VALUE`,
      `_DENIED_KEY`, `_TOKEN_KEY`, `MAX_ATTRIBUTE_CHARS`, `_scalar_allowed`,
      `value_allowed`), and re-import them in `tracing_sdk.py`. Export
      `contains_credential(text) -> bool` and `safe_scalar(value, *, max_chars) -> bool`.
      — DoD: `orchestrator/redaction.py` imports `re` and nothing else;
      `tracing_sdk.key_allowed`, `value_allowed`, `redact_attributes`,
      `redacted_name` and `GuardedExporter` are byte-for-byte behaviourally
      unchanged; `tests/test_tracing.py`, `tests/test_tracing_agents.py` and
      `tests/test_tracing_temporal.py` pass with no edits.

- [ ] 2. Write `docs/adr/018-execution-evidence-envelope-contract.md` (depends on
      nothing; do it first so the module docstring can cite it). Follow the
      `009`/`011-execution-identity`/`017` template: `# ADR 018 — <title>` with
      em dash, blockquote front matter (`**Status:** proposed`, `**Date:**`,
      `**Issue:** mctlhq/mctl-agents#520 (parent #199)`, `**Supersedes:**`), then
      `## Context`, `## Decision` (numbered `### N.` subsections: canonical shape
      table, identity and immutability, redaction, completeness and gaps, boundary
      rules table), `## Alternatives`, `## Non-goals`, `## Platform impact`,
      `## Implementation map`.
      — DoD: the ADR states the hash rule verbatim, names mctl-api as the Tier B
      owner of persistence and retrieval, records #483's gitops-persistence design
      as superseded, and the `## Non-goals` section restates every non-goal from
      issue #520. `python tools/check_diagrams.py` (if it touches ADRs) still passes.

- [ ] 3. Create `orchestrator/execution_evidence.py` skeleton (depends on 2):
      module docstring citing #520, #199 and the ADR path, plus the stdlib-only
      sentence and the explicit non-goals; `from __future__ import annotations`;
      `API_VERSION = "evidence.mctl.ai/v1alpha1"`, `KIND = "ExecutionEvidence"`,
      `SUPPORTED_API_VERSIONS`; `EVIDENCE_ID_PREFIX = "ev-"`; closed vocabularies
      (`OUTCOME_CODES`, `GAP_CODES`, `BLOCK_NAMES`, `COMPLETE`, `INCOMPLETE`) as
      `frozenset`s / `str` constants; `class ExecutionEvidenceError(ValueError)`
      with the standard fail-closed docstring; the `_reject_unknown_keys` /
      `_require_mapping` / `_require_str` / `_require_int` / `_require_bool` /
      `_optional_str` / `_require_sha256` helper block retyped to that error; an
      alphabetical `__all__`.
      — DoD: module imports cleanly; `ruff check` and `mypy` pass; the only
      same-repo module-scope imports are `context_snapshot` (`hash_bytes`,
      `canonical_json`), `policy_checkpoint` (`UNDECIDED_CODES`, `VERDICTS`) and
      `redaction`; no `pathlib`, `os`, `open`, `httpx` or `urllib` anywhere.

- [ ] 4. Add the reference block dataclasses (depends on 3), all
      `@dataclass(frozen=True)` with `to_dict()` / `from_dict()`:
      `ExecutionJoin`, `SnapshotRef`, `ExecutionRequestRef`, `UsageRef`,
      `ApprovalRef`, `PolicyDecisionRef`, `ArtifactRef`, `Outcome`, `Gap`.
      `PolicyDecisionRef.undecided` is `self.code in UNDECIDED_CODES`, the same
      expression as `policy_checkpoint.Decision.undecided` (`:180-181`).
      — DoD: every `from_dict` rejects unknown keys; no block has a free-text or
      body field; `UsageRef` carries only `session_id` / `result_uuid` /
      `model_key` / `devloop_stage` and no counter or cost; `ArtifactRef.name` is
      validated against a bounded pattern rejecting `/`, `\`, `..` and a leading
      `~`; no undecided-code literal appears anywhere in the file.

- [ ] 5. Add `_safe()` (depends on 4): a recursive walk over the whole assembled
      envelope payload returning `(redacted_payload, extra_gaps)`. Drops — never
      masks — any leaf that is non-scalar, over its per-field cap, or matches
      `redaction.contains_credential`, and emits a
      `Gap(block=..., code="redacted_out", required=...)` per drop. Account for
      drops the way `context_snapshot.Redaction` (`:296-324`) describes: rule ids
      and volume only, never matched text.
      — DoD: a unit test proves that a credential-shaped string planted in *every*
      block is absent from the sealed bytes and that each planted value produced
      exactly one `redacted_out` gap.

- [ ] 6. Add `ExecutionEvidence`, `completeness`, `validate()` and `to_log_dict()`
      (depends on 5). `completeness` is a `@property` returning `INCOMPLETE` if
      `any(g.required for g in self.gaps)` else `COMPLETE` — never a field, never
      in `__init__`, never accepted by `from_dict`. `to_log_dict()` returns
      `evidence_id`, `content_hash`, `completeness`, the outcome code and integer
      `*_count` values only, matching `ContextSnapshot.to_log_dict`'s
      `evidence_ref_count` idiom (`context_snapshot.py:1082`).
      — DoD: `ExecutionEvidence(completeness=...)` is a `TypeError`;
      `from_dict({... "completeness": "COMPLETE" ...})` raises
      `ExecutionEvidenceError` for the unknown key; no value in `to_log_dict()`'s
      output is a string other than an id, a hash or a closed-vocabulary code.

- [ ] 7. Add `Requirements`, `_content_payload()`, `seal()` and
      `recompute_content_hash()` (depends on 6). `seal()` is keyword-only, is the
      only constructor, runs `_safe()` *before* hashing, computes
      `content_hash = hash_bytes(canonical_json(payload))` excluding
      `content_hash` / `evidence_id` / `created_at`, mints
      `evidence_id = "ev-" + content_hash[7:23]`, and calls `validate()` before
      returning. Optional blocks enter `_content_payload` only when present.
      — DoD: sealing identical inputs at two different `created_at` values yields
      one `evidence_id`; changing any referenced id or hash changes it; `seal()`
      raises `ExecutionEvidenceError` when a block the `Requirements` marks
      required is both absent and ungapped; `recompute_content_hash` reproduces a
      sealed envelope's hash without mutating it.

- [ ] 8. Add `evidence_ref(evidence, kind) -> dict[str, str]` (depends on 7).
      — DoD: its output is accepted unchanged by
      `context_snapshot.EvidenceRef.from_dict`, and
      `f"evidence:{evidence.evidence_id}"` is accepted by
      `human_input.seal_request`'s `CONTEXT_REF_PREFIXES` check (`human_input.py:46`).

- [ ] 9. Add a golden fixture `tests/fixtures/evidence/investigator-evidence.json`
      (depends on 7).
      — DoD: the file round-trips through `from_dict` / `to_dict` unchanged and its
      `content_hash` and `evidence_id` are asserted byte-for-byte in the test file,
      the way `tests/fixtures/context/investigator-snapshot.json` is.

## Tests

`tests/test_execution_evidence.py`, plain pytest functions with
`# T<n> — <what this proves>` banner comments and `_builder(**overrides)` helpers,
matching `tests/test_context_snapshot.py`.

- [ ] T1. Seal determinism and identity: same inputs + different `created_at` ->
      identical `evidence_id` and `content_hash`; any changed reference -> a
      different `evidence_id`; `evidence_id == "ev-" + content_hash[7:23]`;
      `recompute_content_hash` agrees.
- [ ] T2. Optional-block hash stability: sealing without an optional block
      produces the same `content_hash` as a build of the payload that omits the key
      entirely (the `context_snapshot.py:1199-1206` rule), so a future optional
      block cannot re-identify sealed envelopes.
- [ ] T3. Golden fixture: `tests/fixtures/evidence/investigator-evidence.json`
      round-trips and its hash and id match the checked-in literals.
- [ ] T4. `undecided` derives from the canonical set:
      `@pytest.mark.parametrize("code", sorted(pc.UNDECIDED_CODES))` asserts each
      code makes `PolicyDecisionRef.undecided` true, and a source-text assertion
      fails if `execution_evidence.py` contains any literal from `UNDECIDED_CODES`.
- [ ] T5. Redaction covers every block: a credential-shaped value
      (`ghp_...`, `sk-...`, a JWT, a PEM header, `bearer ...`, a basic-auth URL)
      planted into each block in turn is absent from `canonical_json(to_dict())`
      and yields exactly one `redacted_out` gap; a masked placeholder never appears.
- [ ] T6. Completeness is derived and iff: no required gap -> `COMPLETE`; one
      required gap -> `INCOMPLETE`; a non-required gap alone leaves `COMPLETE`;
      `completeness` is not an `__init__` parameter and not a `from_dict` key.
- [ ] T7. Required-block enforcement: `seal()` raises when a required block is
      absent and ungapped, and succeeds when the same absence carries a `Gap`.
- [ ] T8. No paths, no I/O: a source-text assertion that the module never imports
      `pathlib`, `os`, `open`, `httpx`, `urllib` or `subprocess`; and that no
      public function parameter or returned string can carry `/`, `\` or `..` in
      an `ArtifactRef.name`.
- [ ] T9. Stdlib-only import, copied from `tests/test_policy_checkpoint.py:233-242`:
      a subprocess `import orchestrator.execution_evidence` leaks none of
      `claude_agent_sdk`, `temporalio`, `httpx`, `yaml`, `anyio`,
      `opentelemetry`.
- [ ] T10. No-authorization invariant, copied from
      `tests/test_context_snapshot.py:281-304`: recursively assert no field name in
      the schema contains `allow`, `deny`, `permit`, `grant` or `authorized` —
      evidence records what happened, it never grants anything.
- [ ] T11. Prefix agreement: assert the module's prefixes equal
      `work_context.snapshots.EXECUTION_ID_PREFIX` (`we_`),
      `work_context.snapshots.SNAPSHOT_ID_PREFIX` (`cs_`),
      `work_context.execution_requests.REQUEST_ID_PREFIX` (`xr_`) and
      `action_approvals.ID_PREFIX` (`aar_`), so a rename in an owning module
      breaks this test rather than silently diverging.
- [ ] T12. No second hashing convention: a source-text assertion that
      `execution_evidence.py` contains no `hashlib.` and no `json.dumps(`.
- [ ] T13. Seam compatibility: `evidence_ref()` output is accepted by
      `context_snapshot.EvidenceRef.from_dict` and rejected if a third key is
      added; `to_log_dict()` contains no key whose value is unbounded text.
- [ ] T14. `tracing_sdk` regression (task 1): existing tracing tests pass
      unchanged, and `redaction.contains_credential` returns the same verdict as
      the old inline `_CREDENTIAL_VALUE.search` for a table of known token shapes.

## Rollback

Every change is additive and inert, so rollback is a revert with no state to undo.

1. **Nothing is persisted.** The module writes no file, opens no socket and
   touches no store, so there is no data to clean up, no gitops commit to revert
   and no ArgoCD application to sync. Deleting the code deletes the feature
   completely.
2. **Nothing imports it.** `orchestrator/execution_evidence.py` ships with no
   production caller, so `git rm orchestrator/execution_evidence.py
   tests/test_execution_evidence.py tests/fixtures/evidence/
   docs/adr/018-execution-evidence-envelope-contract.md` cannot break any running
   agent, poller, workflow or worker.
3. **The one edit to existing code is separable.** If task 1's extraction causes
   trouble, revert `orchestrator/redaction.py` and the `tracing_sdk.py` import
   independently of the evidence module (the evidence module would then need the
   two helpers inlined, or be reverted with it). Because the extraction is a pure
   move, its blast radius is the three tracing test files, and a failure shows up
   in CI before merge rather than in production.
4. **No hashes change.** No `snapshot_id`, `content_hash`, `context_id` or
   `.status.yaml` value is affected by this proposal, so a revert cannot orphan or
   re-identify an already-sealed document.
5. **If the schema turns out wrong after Tier B starts**, the `v1alpha1`
   `api_version` plus `SUPPORTED_API_VERSIONS` is the intended escape hatch: add
   `v1alpha2` beside it rather than reverting, since nothing durable exists at
   `v1alpha1` to migrate.
