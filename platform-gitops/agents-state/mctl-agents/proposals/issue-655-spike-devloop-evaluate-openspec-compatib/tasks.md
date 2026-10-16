# Tasks: issue-655-spike-devloop-evaluate-openspec-compatib

Compatibility target for every task: OpenSpec **v1.14.2**, commit **`f80d860`**. Use only the facts pinned in mctlhq/mctl-agents#655, or facts verified against that commit.

- [ ] 1. Create `orchestrator/sdd/__init__.py`. The docstring cites v1.14.2 / `f80d860` and states that the package is a spike, unused by production code. — DoD: the package imports cleanly. No runner, workflow or activity imports it.
- [ ] 2. Implement `orchestrator/sdd/metadata.py` (depends on 1). It provides `.openspec.yaml` load/dump with the pinned known keys, `x-` passthrough, unknown-key warning (error when strict), `x-` keys rejected inside `initiative`, the `skip_specs`-with-specs error, missing file -> `None`, write-nothing-on-failure, and `FORBIDDEN_EXECUTION_KEYS`. — DoD: tests T1-T7 pass.
- [ ] 3. Implement `orchestrator/sdd/spec_model.py` (depends on 1). It parses and renders capability specs and delta files with the assumed grammar, isolated behind `GRAMMAR_VERIFIED = False`. It detects duplicate requirement headers and normalizes names for near-miss detection. — DoD: render(parse(x)) == x on the fixtures, and the duplicate-header fixture is rejected.
- [ ] 4. Implement `orchestrator/sdd/apply.py` (depends on 3). It provides pure `apply_change` and tmp-dir-only `archive_change`, following the pinned archive semantics, with abort-without-partial-output. — DoD: every delta comparison row has a fixture under `tests/fixtures/sdd/delta-rows/<row-id>/` and a passing test (T8).
- [ ] 5. Author the canonical capability fixture `tests/fixtures/sdd/capabilities/devloop-approval/spec.md`, derived from `proposal_state.human_approval_satisfied` / `execution_authorization` and the approval park in `temporal/workflows/dev_loop.py`. Author the change `changes/devloop-approval-content-digest/` with an ADDED, a MODIFIED and a REMOVED requirement, plus the expected post-archive spec (depends on 4). — DoD: T9 shows before -> delta -> after and an archive directory created exactly once.
- [ ] 6. Implement `orchestrator/sdd/convert.py` and `measure.py` (depends on 2, 3). They provide `triplet_to_change`, `change_to_triplet` and `loss_report`, plus bytes/approximate-token measurement (chars/4, documented). — DoD: the issue-596 fixture converts with an empty or explicitly justified loss report. Either the round-trip is stable at section and item level, or the one-way reason is documented (T10, T11).
- [ ] 7. Add `tests/fixtures/sdd/roundtrip/issue-596/` from a read-only copy of `agents-state/mctl-agents/proposals/issue-596-test-agent-platform-add-an-inert-authori` (triplet plus `source` block only). Optionally add 516 and 519 (depends on 6). — DoD: fixtures are committed in the mctl-agents repo only, with no approver identity or trace id.
- [ ] 8. Implement `orchestrator/sdd/verify.py` with a `SpecVerdict` limited to `pass` / `fail` / `unknown` plus findings (depends on 4). — DoD: T12 and T13 pass.
- [ ] 9. Add the candidate schema fixture `tests/fixtures/sdd/schemas/mctl-devloop/schema.yaml`, with artifacts proposal -> specs (`specs/**/spec.md`) -> design -> tasks and `apply: {requires: [tasks], tracks: tasks.md}`, plus a minimal `templates/` directory (depends on 1). — DoD: T14 passes, and the comparison with `spec-driven` and adapter-only is written in task 11.
- [ ] 10. Simulate the Investigator -> artifact -> Implementer boundary for issue 655 itself and for issue 596. Convert the investigator output into the candidate package. Check that every acceptance criterion and task is reachable from the package, and that the changed capability is identifiable from `specs/<capability>/` (depends on 6). — DoD: the six-dimension table (clarity, completeness, context size, ambiguity, implementation success, capability identification) is filled with improve/preserve/worsen and evidence.
- [ ] 11. Write `docs/spikes/655-openspec-contract.md` (depends on 2-10). It covers:
  - the mapping table and the `.openspec.yaml` field map (known keys, `x-mctl-*`, forbidden keys);
  - loss report and sizes;
  - delta comparison table (pinned rule / MCTL choice / test name);
  - the canonical sync demonstration;
  - the Shepherd boundary, with an explicit rejection of verify-replaces-Shepherd/CI/review/authorization;
  - change classes (`trivial` / `normal` / `governed` via `skip_specs` and `x-mctl-change-class`, no approval effect);
  - the schema comparison;
  - the OpenSpec coupling inventory, which should be none at runtime;
  - the unverified-facts list;
  - migration cost and effect on the state machine and APIs;
  - exactly one recommendation;
  - follow-up issue drafts, including "record proposal content digest in approval".

  DoD: the document cites v1.14.2 / `f80d860`, states one of `ADOPT_CONTRACT` / `ADAPTER_ONLY` / `NO_GO`, and, if `ADOPT_CONTRACT`, includes the staged migration plan.
- [ ] 12. Summarize the recommendation in the PR body for reviewer visibility (depends on 11). — DoD: the PR body names the recommendation and links the decision record.

## Tests

All tests go in `tests/test_sdd_*.py` and use fixtures under `tests/fixtures/sdd/`. No network, no Node, no OpenSpec CLI.

- [ ] T1. Valid `.openspec.yaml` (`schema`, `created`, `goal`, `affected_areas`, `x-mctl-issue`) loads in strict mode with no warnings.
- [ ] T2. An unknown top-level key warns in normal mode and fails in strict mode.
- [ ] T3. `x-mctl-*` top-level keys pass strict mode and survive load -> dump unchanged.
- [ ] T4. An `x-` key inside `initiative` is rejected, and a non-kebab-case `initiative.store` is rejected.
- [ ] T5. A missing `.openspec.yaml` returns `None` (no metadata), not an error.
- [ ] T6. `skip_specs: true` with files under `specs/` is a validation error. With an empty or absent `specs/` it passes with zero deltas.
- [ ] T7. Any `.status.yaml` key (`status`, `approval`, `control`, `execution`, `attempt`, `pr`, `github`, `merged_at`, `merge_commit`, `context`, `request`) is rejected even in non-strict mode. A failed dump writes no file.
- [ ] T8. Parametrized delta rows, one fixture each:
  - order R->R->M->A; RENAMED FROM also REMOVED aborts; RENAMED TO colliding with ADDED aborts;
  - RENAMED: source missing with target present is a no-op; both missing aborts;
  - REMOVED: missing warns and is a no-op; a near-miss aborts;
  - MODIFIED: missing aborts; identical is a no-op; dropping scenarios aborts;
  - ADDED: identical is a no-op; different aborts; a near-miss aborts;
  - new capability: ADDED only; MODIFIED/RENAMED abort; REMOVED skipped with a warning;
  - duplicate headers in the main spec are rejected before apply;
  - sync divergence: ADDED-existing-different aborts under the MCTL choice;
  - every abort leaves the input specs byte-identical.
- [ ] T9. The devloop-approval canonical spec + change gives exactly the expected post-archive spec. The first `archive_change` creates `archive/YYYY-MM-DD-<change>` and moves the change. A second call fails because the target exists, while a re-apply of the same delta to the new canonical is a per-requirement no-op.
- [ ] T10. issue-596 conversion: `loss_report` maps every heading, bullet, EARS line and checkbox. `source.url` appears as `x-mctl-issue`.
- [ ] T11. issue-596 round-trip (`change_to_triplet(triplet_to_change(x))`) is stable at section and item level, or the test asserts the documented one-way differences exactly.
- [ ] T12. `SpecVerdict.outcome` is restricted to `pass` / `fail` / `unknown`, and the type has no merge, approve or authorize field or method.
- [ ] T13. Import boundary: no module under `orchestrator/sdd` imports `orchestrator.run_shepherd`, `orchestrator.proposal_state`, `orchestrator.temporal` or `orchestrator.run_implementer`, and no production module imports `orchestrator.sdd`.
- [ ] T14. The `mctl-devloop` schema fixture parses. Required fields are present, `version` is a positive integer, and the `specs` artifact's `generates` starts with `specs/`.
- [ ] T15. Existing suites (`tests/test_run_issue_investigator.py`, shepherd and implementer tests) pass unchanged.

## Rollback

The spike is additive and isolated. To roll back, revert the PR: delete `orchestrator/sdd/`, `tests/fixtures/sdd/`, `tests/test_sdd_*.py` and `docs/spikes/655-openspec-contract.md`. No production module, deployed worker, `.status.yaml` or `agents-state` proposal is modified, so no data migration or redeploy is needed.
