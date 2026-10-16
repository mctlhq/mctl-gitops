# Tasks: issue-655-spike-devloop-evaluate-openspec-compatib

- [ ] 1. Write `docs/spikes/655-sdd-artifact-contract.md` with these sections:
  - the targeted OpenSpec grammar, with a pinned version or docs commit;
  - the change-package and canonical-spec layouts;
  - the EARS-to-Requirement/Scenario mapping rules;
  - the list of forbidden execution-state keys;
  - the change-class table (`trivial`/`normal`/`governed`);
  - the decision criteria from design.md section 9.
  DoD: the criteria are committed before any measurement in task 6. The
  document states explicitly that `.status.yaml`, approval, authorization,
  Temporal and execution identity are outside the contract.
- [ ] 2. Write the mapping table in the same document (depends on 1). It needs
  one row per current section: `requirements.md` (Context, User stories,
  Acceptance criteria (EARS), Out of scope, Open questions), `design.md`
  (Current state incl. `Deployed state checked:`, Proposed solution,
  Alternatives, Platform impact), `tasks.md` (tasks, Tests, Rollback),
  `.status.yaml` `source`, mctl-docs `proposed-content.md` and `incident-*`.
  DoD: every row is marked lossless, lossy (with what is lost) or duplicated,
  or not covered.
- [ ] 3. Add `orchestrator/spec_contract.py` (depends on 1). It contains
  dataclasses `Requirement`, `Scenario`, `Delta`, `ChangePackage` and
  `CapabilitySpec`, and the functions `parse_change`, `parse_canonical`,
  `validate_change`, `apply_delta`, `render_canonical`, `from_triplet`,
  `to_triplet`, `import_openspec` and `export_openspec`. DoD: pure Python, no
  new dependency in `pyproject.toml`, no subprocess, and not imported by any
  module under `orchestrator/` other than tests and tools.
- [ ] 4. Add the fixtures under `tests/fixtures/spec_contract/` (depends on 1).
  DoD: every fixture below exists, and each requirement in the canonical spec
  cites the file and symbol it encodes.
  - `canonical/devloop-approval/spec.md`, grounded in
    `proposal_state.human_approval_satisfied`, `execution_authorization`,
    `unrunnable_reason` and `DevLoopWorkflow.approve`.
  - Two deltas, together covering ADDED, MODIFIED and REMOVED.
  - Historical copies of the `issue-516-fix-devloop-end-devloopworkflow-when-its`
    triplet and one smaller `mctl-agents` proposal, each with only its
    `.status.yaml` `source` block.
  - One OpenSpec-layout change.
  - Golden `expected/` outputs.
- [ ] 5. Add `tools/spec_contract.py` with the subcommands `validate`, `diff`,
  `import`, `export` and `archive` (depends on 3, 4). DoD: `archive` writes
  only into the `--out` directory, refuses any path under `agents-state/`, and
  shows verify, then sync, then archive on the fixtures.
- [ ] 6. Run and record the measurements in the spike report (depends on 2, 5).
  DoD: every bullet below appears with numbers or observations. Results are
  recorded, not wired into CI. Prompts in `run_issue_investigator.py` and
  `run_implementer.py` stay unchanged.
  - Byte size and estimated tokens (bytes/4) for each of the two proposals,
    current versus candidate.
  - Loss-check results.
  - Round-trip result: byte-identical after normalisation, or a documented
    one-way migration.
  - Validator findings on the historical corpus (read-only scan of a local
    gitops checkout), for example the 29 `mctl-agents` proposals with no
    `## Acceptance criteria` heading.
  - Results of the offline investigator simulation, current versus candidate
    prompt variant, on issues 516 and the smaller one: clarity, ambiguity,
    task completeness, and whether the capability is identified.
  - The implementer consumption result.
- [ ] 7. Document the boundary between verification and Shepherd, and the
  post-merge verify, sync and archive path (depends on 1). DoD: the
  `spec_conformance` input is defined, with its rank below CI and P1/P2
  findings. The three rejected designs are named. A walk through
  `run_shepherd` decision inputs shows no existing input is replaced.
- [ ] 8. Write the recommendation (depends on 6, 7). DoD: exactly one of
  `ADOPT_CONTRACT`, `ADAPTER_ONLY` or `NO_GO`, scored against the criteria from
  task 1. The report also states:
  - the migration and interop cost estimate for the 855 existing proposals;
  - the effect on the DevLoop state machine and APIs (expected: none);
  - which file is authored and which is generated in the recommended end state.
  If the recommendation is `ADOPT_CONTRACT`, it adds a staged migration plan and
  drafts follow-up issues. Candidates are: an investigator delta-output behind
  an agent release; an implementer reading `proposal.md` + `specs/**`; a
  validator gate before publication in `_investigate`; Shepherd
  `spec_conformance`; reconcile sync/archive; approval digest-binding.

## Tests

- [ ] T1. `tests/test_spec_contract.py::test_apply_delta_is_deterministic`:
  applying the same delta twice to the canonical fixture gives byte-identical
  output equal to `expected/`.
- [ ] T2. `test_modified_unknown_requirement_fails`: a MODIFIED, REMOVED or
  RENAMED entry naming an absent requirement gives a `ContractError` that
  names the capability and the requirement.
- [ ] T3. `test_added_collision_fails`: an ADDED requirement whose name already
  exists is rejected.
- [ ] T4. `test_execution_state_keys_rejected`: a package carrying `status:`,
  `approval:`, `attempt:`, `pr:`, `merge_commit:` or `control:` as structured
  data fails validation.
- [ ] T5. `test_requirement_needs_shall_and_scenario`: a requirement with no
  SHALL or MUST, or with no scenario, fails validation.
- [ ] T6. `test_triplet_round_trip_issue_516`: `to_triplet(from_triplet(...))`
  matches the fixture after whitespace normalisation, or the test pins the
  documented one-way differences.
- [ ] T7. `test_loss_check_issue_516`: every EARS line, task line, test line
  and heading from the original appears exactly once in the converted package.
- [ ] T8. `test_openspec_import_export_round_trip`: importing the OpenSpec
  fixture and exporting it again gives the same layout and content.
- [ ] T9. `test_change_class_consistency`: `trivial` with delta specs, or
  `normal` without them, fails validation. `trivial` with `proposal.md` +
  `tasks.md` passes.
- [ ] T10. `test_archive_refuses_agents_state`: `tools/spec_contract.py archive`
  refuses an `--out` path under `agents-state/`.
- [ ] T11. `test_spec_contract_not_imported_by_runtime`: no module under
  `orchestrator/` (excluding tests) imports `orchestrator.spec_contract`.
  This guards the inert invariant.
- [ ] T12. The existing suite passes unchanged, notably
  `tests/test_proposal_identity.py`, `tests/test_dev_loop_workflow.py` and the
  `proposal_state` tests.

## Rollback

Every change is additive and inert: one module, one tool, fixtures, tests and a
docs page. To roll back, revert the PR or delete those files. Nothing in
production imports them, no gitops state is written, and no agent version is
published or promoted, so no runtime rollback is needed.
