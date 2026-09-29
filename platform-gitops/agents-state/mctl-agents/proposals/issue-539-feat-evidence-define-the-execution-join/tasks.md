# Tasks: issue-539-feat-evidence-define-the-execution-join

- [ ] 1. Extract `CONTEXT_ID_PREFIX = "ex-"` in
      `orchestrator/execution_identity.py` and use it at the two literal sites
      (`seal()` line 651, `load_from_environment()` line 812); add it to that
      module's `__all__`. — DoD: pure literal-to-constant substitution, no
      behaviour change; `uv run pytest tests/test_execution_identity.py` passes
      unchanged; `uv run ruff check orchestrator` and `uv run mypy` clean.

- [ ] 2. Add the new constants to `orchestrator/execution_evidence.py`
      alongside the existing deliberate duplicates (`:83-96`):
      `RUNTIME_EXECUTION_ID_PREFIX = "ex-"` with a docstring citing
      `orchestrator/execution_identity.py`,
      `_RUNTIME_EXECUTION_ID_PATTERN = re.compile(r"ex-[0-9a-f]{16}")`, and
      `EXECUTION_REF_KINDS = frozenset({"work", "runtime"})`. Export the two
      public names in `__all__`. (depends on 1) — DoD: module still imports
      stdlib-only (T9 passes); `__all__` stays alphabetically sorted.

- [ ] 3. Extend `ExecutionJoin` (`execution_evidence.py:245-270`): add
      `runtime_execution_id: str = ""`, default `execution_id` to `""`, add
      `runtime_execution_id` to the `_reject_unknown_keys` allow-list and to
      `from_dict` (with `allow_empty=True`, matching the other leaves), and
      make `to_dict()` emit the key **only when non-blank**. (depends on 2) —
      DoD: `ExecutionJoin(execution_id="we_x").to_dict()` returns exactly the
      three keys it returns today; a mapping with an unknown key still raises
      `ExecutionEvidenceError` naming it.

- [ ] 4. Add the derived `ExecutionJoin.primary_execution_ref` property
      returning `(kind, id)` with `kind in EXECUTION_REF_KINDS`: `("work",
      execution_id)` when `execution_id` is set, else `("runtime",
      runtime_execution_id)` when that is set, else `("", "")`. (depends on 3)
      — DoD: a `@property`, not a field; not in `__init__`; not accepted by
      `from_dict`; never enters `_content_payload`.

- [ ] 5. Make `_check_execution_join` (`execution_evidence.py:869-874`)
      symmetric and cross-rejecting: `execution_id` must start with
      `EXECUTION_ID_PREFIX` and must NOT start with
      `RUNTIME_EXECUTION_ID_PREFIX`; `runtime_execution_id` must fullmatch
      `_RUNTIME_EXECUTION_ID_PATTERN` and must NOT start with
      `EXECUTION_ID_PREFIX`. Each raise names the field the value belongs in.
      Blank values are still skipped, per the module's documented rule.
      (depends on 3) — DoD: four distinct error messages, each naming the
      correct destination field.

- [ ] 6. Apply the hash-neutral prune. In `seal()`
      (`execution_evidence.py:1087-1090`), after `_safe()` and before
      `clean_execution` and the hash, delete
      `safe_payload["execution"]["runtime_execution_id"]` when it is blank.
      Add a one-line module comment tying this to `_REDACTED_LEAF`
      (`:159-168`) and to `_content_payload`'s block-level absent-when-empty
      rule (`:984-991`). (depends on 3) — DoD: for every input, the hashed
      `execution` block contains `runtime_execution_id` iff the sealed
      envelope's field is non-blank; `recompute_content_hash(seal(...)) ==
      seal(...).content_hash` holds including the redacted case.

- [ ] 7. Update the completeness rule: `_check_required_blocks`
      (`execution_evidence.py:1041`) becomes
      `_check("execution", True, not (execution.execution_id or
      execution.runtime_execution_id))`. (depends on 3) — DoD: a runtime-only
      envelope seals `COMPLETE`; an envelope with neither identity and no
      required `Gap(block="execution")` raises.

- [ ] 8. Add `"primary_execution_kind": self.execution.primary_execution_ref[0]`
      to `ExecutionEvidence.to_log_dict()` (`:843-858`). The id is deliberately
      not exported. (depends on 4) — DoD: T13's `to_log_dict` bounds test still
      passes; the value is always a member of `EXECUTION_REF_KINDS` or `""`.

- [ ] 9. Add the two new golden vectors under `tests/fixtures/evidence/`:
      `implementer-evidence.json` (`ex-` only, with `policy_decisions` and an
      `approvals` entry bound to that runtime id) and `shepherd-evidence.json`
      (both identities, modelling the #519/#524 gated merge). Generate each by
      calling `seal()` and writing `to_dict()` with `json.dumps(..., indent=2,
      sort_keys=True)` plus a trailing newline, matching
      `investigator-evidence.json`'s formatting. (depends on 6, 7) — DoD: both
      files committed; `investigator-evidence.json` byte-identical to `main`.

- [ ] 10. Amend `docs/adr/018-execution-evidence-envelope-contract.md`: append
      `## Amendment 1 — the execution join: two typed identities
      (mctlhq/mctl-agents#539)` following ADR 009's appended-section precedent
      (`docs/adr/009-context-snapshot-contract.md:328`, `:405`), and edit sec.
      1's `ExecutionJoin` line and sec. 5's execution-identity boundary row in
      place. The amendment must state: model (B) chosen and why (A) was
      rejected; the exact four-field `ExecutionJoin` table; that
      `primary_execution_ref` is the execution-scoped retrieval identity while
      `evidence_id` stays the envelope's own key; the deterministic-linkage
      rule (policy decisions and `aar_` intents bind to `runtime_execution_id`
      per `policy_checkpoint.py:641` and `action_approvals.py:140-148`); that
      Tier B must store and index `execution_id` and `runtime_execution_id`
      as two separate typed columns, each independently queryable, with
      `primary_execution_ref` a derived convenience and never the only lookup
      key; the
      completeness rule for a runtime-only run; the `v1alpha1`-stays-additive
      justification; and the named follow-ups. (depends on 7) — DoD: one join
      model named, no contradiction with the shipped code, no emoji, English
      only.

- [ ] 11. Update `docs/adr/018-...`'s Implementation map and
      `orchestrator/execution_evidence.py`'s module docstring to mention the
      two-identity join and the new fixtures. (depends on 10) — DoD: docstring
      still states the module is inert, stdlib-only and imports exactly three
      intra-repo modules.

## Tests

All in `tests/test_execution_evidence.py` unless stated, added as a new
`# T15 — execution join: two typed identities` section following the file's
existing banner convention, plus targeted extensions to T3 and T11.

- [ ] T1. `test_execution_id_rejects_a_runtime_context_id` — `seal()` with
      `ExecutionJoin(execution_id="ex-0123456789abcdef")` raises
      `ExecutionEvidenceError` matching `runtime_execution_id`. Fails if the
      cross-check in task 5 is removed (issue acceptance criterion).
- [ ] T2. `test_runtime_execution_id_rejects_a_work_execution_id` — the exact
      reverse: `runtime_execution_id="we_01J8ZQ…"` raises, message names
      `execution_id`.
- [ ] T3. `test_runtime_execution_id_rejects_a_malformed_shape` —
      parametrized over `"ex-"`, `"ex-XYZ"`, `"ex-0123456789abcde"` (one
      short), `"ex-0123456789ABCDEF"` (wrong alphabet), `"ex-" + "a"*17`.
- [ ] T4. `test_execution_id_still_rejects_a_foreign_prefix` — `"cs_abc"`
      raises, pinning the pre-existing `we_` check.
- [ ] T5. `test_from_dict_rejects_an_unknown_execution_key` — a near-miss key
      (`runtime_execution`) raises `match="unknown key"`.
- [ ] T6. `test_runtime_only_envelope_seals_complete` — an `ex-`-only join
      with an outcome and one policy decision yields `completeness ==
      ee.COMPLETE` and no gaps.
- [ ] T7. `test_seal_raises_when_both_identities_are_blank_and_ungapped`, and
      its partner `test_seal_succeeds_when_that_absence_carries_a_required_gap`
      using `Gap(block="execution", code="not_produced", required=True)`.
- [ ] T8. `test_blank_runtime_identity_is_hash_neutral` — `seal()` of a
      `we_`-only join with `runtime_execution_id=""` produces the same
      `content_hash` and `evidence_id` as the same join constructed without
      the field, and the same hash as a hand-built payload whose `execution`
      block omits the key (the T2 idiom at `test_execution_evidence.py:155`).
- [ ] T9. `test_adding_a_runtime_identity_changes_the_hash` — the converse.
- [ ] T10. `test_recompute_content_hash_agrees_for_all_three_join_shapes` —
      `we_`-only, `ex-`-only, both.
- [ ] T11. Extend T5's redaction parametrization: plant a credential in
      `execution.runtime_execution_id`, assert exactly one `redacted_out` Gap,
      that the field reads `""`, and that `recompute_content_hash` still
      agrees (the `seal()`-side prune from task 6).
- [ ] T12. `test_primary_execution_ref_precedence` — parametrized over the
      four combinations; `work` wins when both are set; `("", "")` when
      neither; every returned kind is in `EXECUTION_REF_KINDS` or `""`.
- [ ] T13. `test_primary_execution_ref_is_not_an_init_parameter` and
      `test_primary_execution_ref_is_rejected_as_a_from_dict_key` — mirrors
      T6's `completeness` tests at `:371` and `:385`.
- [ ] T14. Extend `test_prefixes_agree_with_their_owning_modules` (`:508`):
      `ee.RUNTIME_EXECUTION_ID_PREFIX == ei.CONTEXT_ID_PREFIX == "ex-"`.
- [ ] T15. Extend T3 (`:218`) into a parametrized loader over all three
      fixtures, each asserting `to_dict() == raw`, its literal `content_hash`,
      its literal `evidence_id`, `recompute_content_hash()` agreement and its
      expected `primary_execution_ref` kind. The investigator fixture's two
      existing literals stay byte-identical.
- [ ] T16. `test_no_authorization_field_name_anywhere_in_the_schema` (T10 at
      `:496`) re-run over all three fixtures.
- [ ] T17. `tests/test_execution_identity.py` — assert
      `ei.CONTEXT_ID_PREFIX == "ex-"` and that a sealed context's `context_id`
      starts with it; the existing identity fixture test passes unchanged.
- [ ] T18. Gate: `uv run pytest tests/`, `uv run ruff check orchestrator
      config tests`, `uv run mypy` all green
      (`CONTRIBUTING.md:33-42`).

## Rollback

The change is additive, inert and hash-neutral, so rollback is a plain revert
with no data or state to unwind:

1. `git revert` the merge commit. Nothing imports
   `orchestrator/execution_evidence.py` in production
   (`run_issue_investigator.py`, `run_implementer.py`, `run_shepherd.py` and
   `orchestrator/temporal/workflows/dev_loop.py` are untouched), nothing is
   persisted, no migration ran, and no ArgoCD application or Helm value
   changes. No deploy is required.
2. Partial rollback is available and safe in either direction. Reverting only
   the `orchestrator/execution_identity.py` extraction (task 1) restores the
   `"ex-"` literals and costs only the T14 drift assertion. Reverting only the
   evidence-module change leaves the ADR amendment as an unimplemented
   proposal, which the ADR's `Status` line should then be updated to say.
3. If the prune rule turns out to be wrong after merge, the failure is loud,
   not silent: `test_golden_fixture_round_trips_and_hash_and_id_match_literals`
   and T8/T10 above fail in CI on the first run, before any envelope is ever
   produced by a driver.
4. mctl-api#409 has not shipped, so no stored envelope, index or route depends
   on the new field. If #409 has already ported the vectors, reverting here
   means it must pin the two-identity fixtures as its own contract copy, or
   revert with it — coordinate through the parent issue mctlhq/mctl-agents#199,
   which stays the acceptance owner.
