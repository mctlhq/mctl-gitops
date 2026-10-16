# Tasks: issue-655-spike-devloop-evaluate-openspec-compatib

- [ ] 1. Write draft `docs/adr/021-sdd-artifact-contract.md` (status `proposed`) — DoD:
  - The draft defines the package layout, `proposal.md` front matter (`change_class`, `source`, `capabilities`), the delta header grammar, the canonical spec tree, the execution-key denylist and the change classes, as described in design.md section 1.
  - It states invariants 1-8 from the issue verbatim.
- [ ] 2. Implement `tools/spec_contract.py` (depends on 1) — DoD:
  - Pure functions `parse_legacy_triplet`, `export_change`, `import_change`, `validate`, `diff_delta`, `apply_delta` (raises `DeltaConflict`), `archive` and `measure`.
  - CLI sub-commands `validate`, `diff`, `apply`, `import`, `export` and `measure`.
  - Imports are limited to the standard library and `yaml`.
  - No `orchestrator.*` import.
- [ ] 3. Add canonical and delta fixtures under `tests/fixtures/spec_contract/` (depends on 1) — DoD:
  - `canonical/devloop-approval/spec.md` is grounded in `proposal_state.human_approval_satisfied` / `execution_authorization` and the `dev_loop.approve` signal.
  - `changes/devloop-approval-digest/` holds at least one `ADDED` and one `MODIFIED` requirement.
  - `expected/devloop-approval/spec.md` is the golden output.
- [ ] 4. Add legacy fixtures (depends on 1) — DoD:
  - A copy of `agents-state/mctl-agents/proposals/issue-623-tracing-record-cache-read-write-token-us/` triplet, plus its `source` block.
  - One proposal from another service, preferably one with `proposed-content.md`.
  - `invalid/` packages, one per diagnostic code.
- [ ] 5. Run `export`, `import`, `validate`, `apply` and `measure` over the fixtures (depends on 2, 3, 4) — DoD: the outputs are captured in the report, including:
  - the round-trip result;
  - byte and approximate token tables;
  - the traceability matrix;
  - the diagnostics.
- [ ] 6. Simulate the agent boundaries (depends on 5) — DoD:
  - The report records `improves`/`preserves`/`worsens`, with evidence, for clarity, completeness, context size, ambiguity, success risk and capability identification.
  - Each entry is labelled `simulated` unless a real run was performed.
- [ ] 7. Write `docs/spikes/655-openspec-compatible-artifact-contract.md` (depends on 5, 6) — DoD: the report contains:
  - the mapping table;
  - lost and duplicated information;
  - the measurements;
  - the Shepherd boundary and rejected designs;
  - the post-merge sync and archive flow;
  - the change-class strategy;
  - the OpenSpec coupling, with the checked revision or a recorded gap;
  - the migration cost estimate based on the gitops counts (2629 proposal `.md` files, 40 `proposed-content.md`);
  - answers to questions 1-10;
  - exactly one of `ADOPT_CONTRACT` / `ADAPTER_ONLY` / `NO_GO`, chosen by the design.md rubric;
  - if `ADOPT_CONTRACT`, a staged migration plan and follow-up issue titles and scopes, including approval binding to a package digest.
- [ ] 8. Add `tests/test_spec_contract.py` (depends on 2, 3, 4) — DoD: tests T1-T8 pass under the repo's existing pytest setup.

## Tests

- [ ] T1. Round trip: `import_change(export_change(parse_legacy_triplet(d)))` equals the original triplet for each legacy fixture, after the documented normalization. If the round trip is declared one-way, the test asserts a zero `lost` count instead.
- [ ] T2. `apply_delta(canonical, delta)` equals `expected/devloop-approval/spec.md` byte for byte.
- [ ] T3. Each of these raises `DeltaConflict` and leaves `tmp_path` empty:
  - `MODIFIED` of a missing requirement;
  - `REMOVED` of a missing requirement;
  - `ADDED` of an existing requirement.
- [ ] T4. Each `invalid/` fixture yields exactly its expected diagnostic code. This includes a package carrying `approval`/`status` keys (execution-state leak).
- [ ] T5. Change classes:
  - a `trivial` package without `specs/` validates;
  - a `normal` package that changes behavior without a delta fails;
  - a `governed` package without `## Alternatives` fails.
- [ ] T6. `archive()` produces the expected tree under `tmp_path`, and writes nothing outside it.
- [ ] T7. Isolation: no module under `orchestrator/` imports `spec_contract`. `TRIPLET`, `TRIPLET_FILENAMES` and the implementer prompt text are unchanged. Assert on the constants.
- [ ] T8. Runtime coupling: `tools/spec_contract.py` imports only the standard library and `yaml`, and never spawns an `openspec` process. This is checked with an AST scan of the file.

## Rollback

The spike only adds new files:
- `docs/adr/021-*`
- `docs/spikes/655-*`
- `tools/spec_contract.py`
- `tests/fixtures/spec_contract/**`
- `tests/test_spec_contract.py`

No runtime path imports them, and nothing under `platform-gitops/` changes. To roll back, revert the PR's merge commit. No data migration, workflow drain or redeploy is needed.
