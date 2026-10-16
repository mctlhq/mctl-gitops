# Tasks: issue-655-spike-devloop-evaluate-openspec-compatib

- [ ] 1. Write `docs/adr/021-sdd-artifact-contract.md` (status: proposed): the
  change-package layout, requirement and scenario grammar, delta operations
  and apply order, MCTL extension sections, `Source:` and `Change-Class:`
  lines, forbidden `.status.yaml` keys, change classes, the Shepherd boundary
  and the pinned OpenSpec-compatible grammar it targets. — DoD: the ADR
  states invariants 1-8 from #655 and names `.status.yaml`, approval,
  authorization, Temporal and execution identity as outside the contract.
- [ ] 2. Add `orchestrator/spec_contract.py` (stdlib only):
  `parse_legacy_triplet`, `export_change`, `render_change`, `import_change`,
  `render_legacy`, `parse_canonical`, `parse_delta`, `apply_delta` (order
  RENAMED, REMOVED, MODIFIED, ADDED; all-or-nothing `DeltaConflict`),
  `validate` -> `list[Diagnostic]`, and `archive` (writes only under the given
  roots) (depends on 1). — DoD: the module imports nothing outside the stdlib
  and is not imported by any `orchestrator/run_*.py`,
  `orchestrator/temporal/**` or `proposal_state.py`.
- [ ] 3. Add `tools/spec_contract.py` with argparse subcommands `validate`,
  `diff`, `export`, `import`, `apply` and `measure` (bytes plus
  `ceil(chars/4)` token estimate) (depends on 2). — DoD: each subcommand runs
  against the fixtures and exits non-zero on diagnostics or conflicts. No
  console-script entry is added to `pyproject.toml`.
- [ ] 4. Add fixtures under `tests/fixtures/spec_contract/`:
  `canonical/devloop-approval/spec.md` (each requirement cites
  `orchestrator/proposal_state.py` or
  `orchestrator/temporal/workflows/dev_loop.py`),
  `changes/approval-content-binding/` (proposal.md, tasks.md and a
  specs/devloop-approval/spec.md with at least one ADDED and one MODIFIED),
  `legacy/issue-655/` (copy of this proposal's triplet from `$PROPOSAL_DIR`),
  and `legacy/issue-623/` if readable, with an `expected/` export of each
  (depends on 2). — DoD: fixtures validate cleanly, or their diagnostics are
  the expected findings and are listed in the report. If issue-623 is
  unreadable, that is recorded as a gap and not replaced by invented content.
- [ ] 5. Run the demonstration: export, then import (round trip) for each
  legacy fixture, `apply` the delta to the canonical spec, `archive` into a
  temp tree, and `measure` all artifacts (depends on 3, 4). — DoD: the
  outputs are captured in the report verbatim, including the before and
  after canonical spec.
- [ ] 6. Simulate the agent boundaries: for issue #623 (issue text + code at
  its pre-merge commit + `devloop-approval` or the relevant canonical spec),
  hand-author the change package the investigator would produce, then read
  it as the implementer would against the `_build_prompt` contract in
  `run_implementer.py`. Score clarity, task completeness, context size,
  ambiguity, implementation feasibility and capability identification
  (depends on 5). — DoD: the scores and rationale are in the report, labeled
  "simulated", with the inputs listed.
- [ ] 7. Write `docs/spikes/655-openspec-compatible-artifact-contract.md`:
  the measured mapping table, information lost or duplicated, size and token
  table, validator findings the current pipeline misses, the sync/archive
  demo, agent-fit results, the Shepherd boundary checked against the review
  loop states, change classes, the OpenSpec coupling statement (none), a
  migration cost estimate for the 92 existing proposals, the effect on the
  DevLoop state machine and APIs, and exactly one recommendation chosen by
  the design.md rubric (depends on 5, 6). — DoD: the report contains exactly
  one of `ADOPT_CONTRACT`, `ADAPTER_ONLY` or `NO_GO`. For ADOPT or ADAPTER it
  also has a staged plan and follow-up issue drafts (title + one-paragraph
  body), including "bind approval to proposal content digest" as a
  standalone follow-up.

## Tests

- [ ] T1. `tests/test_spec_contract.py`: export then import of each legacy
  fixture equals the original after the documented normalization.
- [ ] T2. `apply_delta` on the canonical fixture yields the expected new
  spec. MODIFIED, REMOVED or RENAMED of a missing name, and ADDED of an
  existing name, each raise `DeltaConflict` and leave inputs unchanged.
- [ ] T3. The validator flags: a requirement without SHALL/MUST, a requirement
  without a scenario, duplicate names, a `normal` change with no delta, a
  `governed` change without design.md, a malformed `Source:`, and each
  forbidden `.status.yaml` key.
- [ ] T4. A `trivial` change with no `specs/` passes validation, and no
  `Change-Class` value changes any approval-related output.
- [ ] T5. `archive` writes only under the provided temp roots (assert that
  no file is created outside `tmp_path`).
- [ ] T6. Import isolation: an AST scan of `orchestrator/**/*.py` finds no
  import of `spec_contract` outside `tools/` and `tests/`.
- [ ] T7. `tools/spec_contract.py validate` exits 0 on clean fixtures and
  non-zero on an invalid one.

## Rollback

Everything is additive and isolated: delete `orchestrator/spec_contract.py`,
`tools/spec_contract.py`, `tests/test_spec_contract.py`,
`tests/fixtures/spec_contract/`, `docs/adr/021-sdd-artifact-contract.md`
and `docs/spikes/655-openspec-compatible-artifact-contract.md`, or revert the
single PR. No production path, `.status.yaml`, Temporal history or
mctl-gitops content is touched, so nothing else needs reverting.
