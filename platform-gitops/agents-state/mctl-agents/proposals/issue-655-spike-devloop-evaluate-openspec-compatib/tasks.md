# Tasks: issue-655-spike-devloop-evaluate-openspec-compatib

Global constraint for every task: do not modify `run_issue_investigator.py`,
`run_implementer.py`, `run_shepherd.py`, `proposal_state.py`,
`orchestrator/temporal/**`, `pyproject.toml`, `uv.lock`, or anything outside
the clone.

- [ ] 1. Write the draft ADR `docs/adr/021-sdd-artifact-contract.md`
  (status: proposed). — DoD: the ADR covers all of the following:
  - the change-package layout and the canonical-spec layout;
  - the requirement and delta grammar (ADDED/MODIFIED/REMOVED/RENAMED, apply
    order, all-or-nothing);
  - the MCTL extension headings;
  - the `Source:` and `Change-Class:` lines;
  - the forbidden `.status.yaml` keys;
  - the change classes;
  - the pinned OpenSpec format assumptions;
  - a statement that approval, authorization, Temporal and `.status.yaml`
    are outside the contract.
- [ ] 2. Implement `orchestrator/spec_contract.py` (depends on 1), pure
  stdlib. — DoD: the module provides:
  - the dataclasses and functions named in design.md section 3;
  - `apply_delta` raising `DeltaConflict` and leaving its inputs untouched on
    any conflict;
  - `archive` writing only under the roots it is given;
  - no import of yaml, network or subprocess modules.
- [ ] 3. Implement `tools/spec_contract.py` (depends on 2), with the
  subcommands `validate`, `diff`, `export`, `import`, `apply` and `measure`.
  — DoD: each subcommand runs against the fixtures from task 4, and
  `measure` prints bytes and `ceil(chars/4)` tokens.
- [ ] 4. Add the canonical spec and change-delta fixtures under
  `tests/fixtures/spec_contract/` (depends on 1). — DoD:
  - `canonical/devloop-approval/spec.md` has at least 4 requirements, each
    citing the source file and symbol it was derived from;
  - `changes/approval-content-binding/` has at least one `ADDED` and one
    `MODIFIED` delta;
  - `expected/` holds the post-apply canonical spec;
  - `invalid/` has one negative fixture per validation rule.
- [ ] 5. Add the legacy proposal fixtures (depends on 4). — DoD:
  - `legacy/issue-655/` is a copy of this proposal's triplet from
    `$PROPOSAL_DIR`;
  - `legacy/issue-623/` is copied read-only from the mctl-gitops checkout if
    it is readable, otherwise a second available proposal is used and the
    substitution is noted;
  - each fixture has a hand-reviewed `expected/` change package and a
    capability map.
- [ ] 6. Run export, import, validate and measure over both legacy fixtures
  and the delta demonstration (depends on 2, 3, 5). — DoD: the raw outputs
  (size table, diagnostics, round-trip diff, before/after canonical spec,
  archive tree) are captured for the report.
- [ ] 7. Simulate the agent boundaries (depends on 6). — DoD: the report
  records both of the following, each labeled "simulated":
  - an Investigator pass for issue #623 (issue text, relevant code and the
    canonical spec in; change package out);
  - an Implementer reading of the resulting package, scored on clarity, task
    completeness, context size, ambiguity and exact capability
    identification.
- [ ] 8. Write `docs/spikes/655-openspec-compatible-artifact-contract.md`
  (depends on 6, 7). — DoD: the report contains:
  - the filled-in mapping table and the loss/duplication findings;
  - the measurements and validator findings;
  - the sync/archive demonstration;
  - the Shepherd boundary, mapped onto `decide()` outcomes;
  - the change classes and the coupling statement;
  - the migration cost estimate for the existing proposals;
  - the effect on the state machine and APIs;
  - exactly one of `ADOPT_CONTRACT` / `ADAPTER_ONLY` / `NO_GO`, chosen by
    the design.md rubric;
  - follow-up issue drafts, plus a staged migration plan if the
    recommendation is `ADOPT_CONTRACT`.
- [ ] 9. Add `tests/test_spec_contract.py` (depends on 2, 4, 5). — DoD: the
  tests T1-T9 below pass under `uv run pytest tests/test_spec_contract.py`,
  and the full suite stays green.

## Tests

- [ ] T1. Round trip: `import_change(export_change(parse_legacy_triplet(d)))`
  renders byte-identical files after normalization for both legacy fixtures,
  or the test asserts the exact documented list of one-way sections.
- [ ] T2. `apply_delta` on `devloop-approval` with the fixture delta equals
  `expected/devloop-approval.spec.md`.
- [ ] T3. Each of the following raises `DeltaConflict` and writes nothing:
  `MODIFIED`/`REMOVED`/`RENAMED` against a missing requirement, and `ADDED`
  of a requirement that already exists.
- [ ] T4. Each `invalid/` fixture yields exactly its expected diagnostic
  code. The cases are: a missing SHALL/MUST, a missing scenario, a duplicate
  name, `normal` with no delta, `governed` with no design.md, a bad `Source:`
  form, and a `.status.yaml` key present.
- [ ] T5. Change classes: a `trivial` package with no delta validates
  cleanly, and no code path in `spec_contract.py` reads or writes
  `control.requires_human_approval` (asserted by grep over the module
  source).
- [ ] T6. `archive()` into a `tmp_path` produces the expected tree, and no
  file is written outside `tmp_path`.
- [ ] T7. Import isolation: no module under `orchestrator/` other than
  `spec_contract.py` imports it, following the pattern in
  `tests/test_worker_isolation.py`.
- [ ] T8. The module has no runtime dependency: its imports are limited to
  the stdlib, and it has no reference to `openspec` executables or
  `subprocess`.
- [ ] T9. The `tools/spec_contract.py measure` output for a fixture matches
  the computed byte and token counts.

## Rollback

Every artifact is additive and unreferenced by production code:

- `orchestrator/spec_contract.py`;
- `tools/spec_contract.py`;
- `tests/fixtures/spec_contract/`;
- `tests/test_spec_contract.py`;
- `docs/adr/021-sdd-artifact-contract.md`;
- `docs/spikes/655-openspec-compatible-artifact-contract.md`.

To roll back, revert the implementation PR. No `.status.yaml`, Temporal
history, gitops state or deployed service changes, so nothing needs a data
migration or a redeploy.
