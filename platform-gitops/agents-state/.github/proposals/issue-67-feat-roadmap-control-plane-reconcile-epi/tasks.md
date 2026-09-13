# Tasks: issue-67-feat-roadmap-control-plane-reconcile-epi

- [ ] 1. Add `roadmap/schemas/github-graph-snapshot.schema.json` defining the
      provider-neutral observed-graph capture (`apiVersion:
      roadmap.mctl.ai/v1alpha1`, `kind: GitHubGraphSnapshot`, `capturedAt`,
      `issues[]` with `repository`/`number`/`found`/`state`/`title`/`parent`/
      `subIssues`/`blockedBy`/`blocking`), reusing the `issueRef` shape and
      `additionalProperties: false` style of
      `roadmap/schemas/epic-definition.schema.json` — DoD:
      `Draft202012Validator.check_schema` passes and the schema rejects an
      unknown top-level field.
- [ ] 2. Add `roadmap/schemas/roadmap-diff.schema.json` defining `kind:
      RoadmapDiff` with `epic`, `manifest` (`path`, `sha256`), `source`
      (`mode`, `capturedAt`), `summary` counts, and the three separate entry
      collections `binding` / `hierarchy` / `dependency`, each entry carrying
      `type`, `severity` (`drift` | `info`), and a typed payload — DoD: schema
      self-check passes and a hand-written converged example validates.
- [ ] 3. Add `roadmap/scripts/github_graph.py` with the `GraphSnapshot` loader,
      `observed_graph()` normalization (lowercase repository keys, sorted and
      deduplicated relation lists, self-edges dropped), and `FixtureGraphSource`
      (depends on 1) — DoD: loading the schema-valid snapshot yields a
      normalized observed graph; loading a schema-invalid snapshot raises with a
      JSON-path style message.
- [ ] 4. Add `LiveGraphSource` to `roadmap/scripts/github_graph.py`: batched
      GraphQL read for existence/state/`parent`/`subIssues`, REST
      `dependencies/blocked_by` per issue, all funnelled through a single
      `_get()` helper that hardcodes `method="GET"` and raises `WriteAttempted`
      for any other method or a request body; token from the environment; plus a
      `--capture` path that writes a schema-valid snapshot (depends on 3) —
      DoD: unit test with a stubbed opener proves only GET is issued and that
      forcing another method raises.
- [ ] 5. Add `desired_graph()` to `roadmap/scripts/reconcile.py`: resolve
      bindings via `validate._issue_key`, derive `(parent, child)` hierarchy
      edges (epic root when `parent` is absent), derive `(blocked, blocker)`
      dependency edges from `dependsOn` and `externalDependsOn`, and record
      suppressions for edges touching unbound work items; `spec.phases` never
      produces an edge — DoD: `human-input.yaml` yields exactly 5 hierarchy
      edges (one per bound work item, all under epic root `mctlhq/.github#42`),
      7 dependency edges (6 local plus the single `externalDependsOn` to
      `mctlhq/mctl-telegram#443`), and 2 suppressions for the unbound
      `devloop-e2e` item (its hierarchy edge and its `dependsOn` edge).
- [ ] 6. Implement `diff()` in `roadmap/scripts/reconcile.py` producing the
      three separate collections and the nine entry types
      (`BindingIssueNotFound`, `BindingRedirected`, `BindingAmbiguous`,
      `BindingUnbound`, `HierarchyMissingParent`, `HierarchyWrongParent`,
      `HierarchyUnexpectedChild`, `DependencyMissing`, `DependencyUnexpected`),
      computing binding entries first and suppressing edges whose endpoints are
      unresolvable (depends on 3, 5) — DoD: each entry type is reachable from a
      crafted snapshot in tests, and an unreachable issue produces exactly one
      binding entry and no hierarchy/dependency cascade.
- [ ] 7. Implement deterministic serialization: sorted entry collections by
      `(type, subject, object)`, `manifest.sha256` over the exact manifest bytes,
      `capturedAt` copied from the snapshot only, `json.dumps(sort_keys=True,
      indent=2)`, no clock or randomness (depends on 2, 6) — DoD: output
      validates against `roadmap-diff.schema.json` and two runs are
      byte-identical.
- [ ] 8. Add the `reconcile.py` CLI: positional manifest paths reusing
      `validate._manifest_paths`, `--snapshot`, `--live`, `--capture`,
      `--output`, validation-before-reconcile via `validate.validate_document`,
      and exit codes 0 converged / 1 drift / 2 usage-or-validation error,
      matching `validate.main` (depends on 7) — DoD: all three exit codes are
      exercised by tests; a manifest that fails validation is never reconciled.
- [ ] 9. Capture and commit `roadmap/fixtures/human-input/converged.json`, a
      snapshot in which every desired edge of `roadmap/epics/human-input.yaml`
      is present (generated with `--capture` then hand-converged; the unbound
      `devloop-e2e` item contributes no issue) (depends on 4, 5) — DoD:
      `reconcile.py roadmap/epics/human-input.yaml --snapshot
      roadmap/fixtures/human-input/converged.json` exits 0 with zero drift
      entries and only the informational `BindingUnbound` entry.
- [ ] 10. Add `roadmap/tests/mutations.py` with pure snapshot mutators
      `drop_parent_edge`, `drop_dependency_edge`, `rebind_issue`, each returning
      a deep-copied snapshot and leaving the input untouched (depends on 9) —
      DoD: applying a mutator and its inverse returns an object equal to the
      original snapshot.
- [ ] 11. Add `roadmap/tests/test_reconcile.py` covering the mutation matrix and
      the unit-level behaviours below (depends on 10) — DoD: all tests pass
      under `python -m unittest discover -s roadmap/tests -p 'test_*.py'`.
- [ ] 12. Add the reconcile step to `.github/workflows/roadmap-validate.yml`
      after the existing validator step, running fixture mode only; keep
      top-level `permissions: {}`, keep the SHA-pinned checkout, and add no
      secret (depends on 9) — DoD: the workflow runs green on a roadmap-only PR
      with no token available.
- [ ] 13. Extend `roadmap/README.md` with a "Reconciliation" section: the CLI
      invocation, the snapshot/live modes, exit codes, the `RoadmapDiff` entry
      types, the read-only guarantee, and how to re-capture the fixture (depends
      on 8, 9) — DoD: every command in the section runs as written from a clean
      checkout with `roadmap/requirements.txt` installed.
- [ ] 14. Confirm `roadmap/requirements.txt` needs no change (stdlib plus the
      already pinned `jsonschema` and `PyYAML`) and that no new runtime
      dependency was introduced (depends on 4) — DoD: `pip install -r
      roadmap/requirements.txt` in a clean venv is sufficient to run both
      scripts and the whole test suite.

## Tests

- [ ] T1. Converged direction: the committed snapshot plus
      `roadmap/epics/human-input.yaml` produce zero `hierarchy`, zero
      `dependency`, and zero drift-severity `binding` entries, and exit code 0.
- [ ] T2. Red direction — hierarchy: `drop_parent_edge` on one bound work item
      yields exactly one `HierarchyMissingParent` entry, an empty `dependency`
      collection, and exit code 1.
- [ ] T3. Red direction — wrong parent: re-pointing one child's observed parent
      at another bound issue yields exactly one `HierarchyWrongParent` entry
      carrying both expected and observed parents.
- [ ] T4. Red direction — dependency: `drop_dependency_edge` on
      `telegram-adapter -> human-input-api` yields exactly one
      `DependencyMissing` entry and an empty `hierarchy` collection.
- [ ] T5. Red direction — unexpected dependency: adding an observed `blockedBy`
      edge with no authored counterpart yields exactly one
      `DependencyUnexpected` entry.
- [ ] T6. Red direction — binding: `rebind_issue` changing one bound issue
      number yields exactly one `BindingIssueNotFound` entry and no cascaded
      hierarchy/dependency entries for that issue.
- [ ] T7. Restoration: for each of T2-T6, applying the inverse mutation returns
      an object equal to the committed snapshot and reconciles green again
      (exit 0).
- [ ] T8. Phase order is not a dependency: two work items in different phases
      with no `dependsOn` produce no dependency edge and no dependency entry.
- [ ] T9. Unbound work item: `devloop-e2e` produces exactly one informational
      `BindingUnbound` entry carrying its `title` and `owner`, contributes no
      edge, and does not change the exit code.
- [ ] T10. Read-only guarantee: a stubbed HTTP opener records every request from
      `LiveGraphSource`; all are GET, and forcing a non-GET method or a body
      raises `WriteAttempted`.
- [ ] T11. Determinism: reconciling the same manifest and snapshot twice yields
      byte-identical JSON, and entry order is independent of input ordering
      (shuffled `issues[]` and shuffled relation lists give identical output).
- [ ] T12. Output contract: the emitted `RoadmapDiff` validates against
      `roadmap/schemas/roadmap-diff.schema.json` for both the converged and the
      drifting cases.
- [ ] T13. Exit codes: 0 converged, 1 drift, 2 for an unreadable snapshot and
      for a manifest that fails `validate.validate_document`.
- [ ] T14. Ambiguity: a snapshot where one issue is a sub-issue of two parents
      yields exactly one `BindingAmbiguous` entry.
- [ ] T15. Normalization: a snapshot using different repository letter casing
      than the manifest still reconciles green.

## Rollback

Everything in this proposal is additive and read-only, so rollback is a plain
revert of the single PR: delete `roadmap/scripts/reconcile.py`,
`roadmap/scripts/github_graph.py`, `roadmap/schemas/roadmap-diff.schema.json`,
`roadmap/schemas/github-graph-snapshot.schema.json`, `roadmap/fixtures/`,
`roadmap/tests/test_reconcile.py`, `roadmap/tests/mutations.py`, and revert the
`.github/workflows/roadmap-validate.yml` and `roadmap/README.md` edits. No
manifest, schema, or GitHub state is mutated by this change, so there is nothing
to undo outside the repository and no data migration to reverse.

If only CI is the problem (for example the new fixture step fails after an
unrelated change), the narrower rollback is to delete the reconcile step from
`.github/workflows/roadmap-validate.yml` while leaving the scripts and tests in
place; the validator path continues to work exactly as it does today. If
`LiveGraphSource` breaks because a GitHub API surface changed, fixture mode is
unaffected, so the adapter can be fixed independently without touching the
detector or the diff contract.
