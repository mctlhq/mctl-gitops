# Tasks: issue-99-feat-roadmap-control-plane-derive-depend

- [ ] 1. Publish `roadmap/schemas/roadmap-ready-set.schema.json` for `RoadmapReadySet`
      and `RoadmapReadySetList` — DoD: `additionalProperties: false` throughout; closed
      `state` enum (`complete`, `ready`, `blocked`, `unknown`) and closed `reason` enum
      (`closed`, `dependencies_complete`, `dependency_incomplete`, `dependency_unknown`,
      `unbound`, `issue_not_found`, `unobserved`, `state_not_observed`,
      `binding_ambiguous`, `closed_reason_unrecognized`); reuses the `issueRef` and
      `source` shapes of `epic-definition.schema.json` /
      `github-graph-snapshot.schema.json`; blocker is a `oneOf` on `kind`
      (`internal` requires `id`, `external` requires `issue`); `dependsOn`,
      `externalDependsOn` and `blockers` are required arrays (possibly empty); the list
      envelope mirrors `roadmap-health.schema.json`'s `RoadmapHealthList`. The schema
      loads under `Draft202012Validator` in a unit test.

- [ ] 2. Promote `completion._colliding_bindings()` to public
      `completion.colliding_bindings()` (depends on 1 only for review ordering) — DoD:
      new public name, private alias retained, no behaviour change; existing
      `python -m unittest roadmap.tests.test_completion` passes byte-for-byte identical
      `RoadmapHealth` output for epic #66 and human-input.

- [ ] 3. Implement the pure core `ready.compute(document, observed, unobserved)` in
      `roadmap/scripts/ready.py` (depends on 2) — DoD: signature mirrors
      `completion.compute()`; per-item own status comes only from
      `completion.item_status()`; predecessor set is authored `dependsOn` plus
      `externalDependsOn` and nothing else; precedence `complete` > own-unknown >
      `blocked` > `dependency_unknown` > `ready`; items sorted by id, blockers sorted by
      `(kind, id|repository, number)`, `dependsOn`/`externalDependsOn` in authored order;
      no import of `time`, `datetime`, `random` or any network module; each item echoes a
      `completion: {status, reason}` block.

- [ ] 4. Implement `ready.consistency_errors(document)` (depends on 3) — DoD: returns a
      message list (never raises) for: summary/`required` counts disagreeing with items;
      top-level `ready` not exactly the `ready`-state ids; a `ready` or `complete` item
      with a non-empty `blockers`; a `blocked` item with no `incomplete` blocker; an
      `unknown` item with neither an own-unknown reason nor an `unknown` blocker; a
      `ready` item with no `issue`; a blocker naming an id or ref absent from that item's
      authored `dependsOn`/`externalDependsOn`. Returns `[]` for every document the
      compute path produces.

- [ ] 5. Build the `RoadmapReadySet` document builder and `render()` (depends on 3) —
      DoD: `epic` block identical in shape to `health._epic()` (name, manifest path via
      `reconcile._manifest_label()`, sha256 from `LoadedManifest`, root `issue`); `source`
      copied verbatim from the snapshot; one manifest renders a bare `RoadmapReadySet`,
      several render a `RoadmapReadySetList` ordered by manifest path.

- [ ] 6. Add the `ready.py` CLI (depends on 4, 5) — DoD: positional manifests, `--corpus`
      (whole corpus validated first via `reconcile.validate_corpus()`), `--schema`,
      `--ready-schema`, `--snapshot`, `--live`, `--capture`, `--api-base`, `--output`;
      `--snapshot` and `--live` mutually exclusive; observation through
      `reconcile._build_source()` with `require_complete=False`; output validated against
      the schema and `consistency_errors()` before emission; exit codes `0` no unknown,
      `1` at least one unknown, `2` usage/IO, `3` invalid manifest/corpus, `4` observation
      failure.

- [ ] 7. Author `roadmap/fixtures/lifecycle-ownership/converged-fixture.json` (depends
      on 6) — DoD: `source.mode: synthetic-fixture`; observes mctlhq/.github#57 plus
      mctl-agents#350/#351/#352/#353 and mctl-api#293/#294; every issue open; hierarchy
      and `blockedBy` edges match `roadmap/epics/lifecycle-ownership.yaml`, proven by
      `reconcile.py` reporting zero drift against it.

- [ ] 8. Author `roadmap/fixtures/unified-identity/root-only-fixture.json` (depends on 6)
      — DoD: `source.mode: synthetic-fixture`; observes only mctlhq/.github#91 (the epic
      has no bound work items); `ready.py` against it exits `1` and reports every work
      item `unknown/unbound`.

- [ ] 9. Add `mutations.set_state(snapshot, issue, state, reason)` to
      `roadmap/tests/mutations.py` (depends on 7) — DoD: pure deep-copy mutator in the
      style of the existing `drop_dependency`/`redirect`; `test_completion._set_state` is
      replaced by it with the completion suite still green.

- [ ] 10. Document readiness in `roadmap/README.md` (depends on 6) — DoD: a "Readiness"
      section after "Completion" carrying the state/reason table, the
      `blocked` > `unknown` precedence rule and why, the two deliberate divergences from
      the completion axis (`unbound`, `issue_not_found`), the CLI invocation and exit
      codes, and the statement that runtime/Temporal state cannot enter because the input
      vocabulary has no field for it. `roadmap/README.md`'s layout tree lists the new
      script, schema, tests and fixtures.

- [ ] 11. Extend `.github/workflows/roadmap-validate.yml` (depends on 6, 7) — DoD: two
      new offline steps, no token, `--live` never used: `ready.py` on
      `roadmap/epics/human-input.yaml` with the synthetic converged fixture asserting
      `ready == ["human-input-core"]`, and `ready.py` on
      `roadmap/epics/roadmap-control-plane.yaml` with its live capture asserting
      `ready-work-items` and `temporal-health` are `ready` and `epic-status-api` is
      `blocked`. Both steps assert `kind == "RoadmapReadySet"` and tolerate the documented
      non-zero exit codes explicitly rather than by `|| true`.

## Tests

`roadmap/tests/test_ready.py`, run by the existing
`python -m unittest discover -s roadmap/tests -p 'test_*.py'`.

- [ ] T1. Linear chain: with `lifecycle-ownership` all open, only `ownership-contract` is
      `ready`; closing it makes `devloop-ownership` `ready` and leaves
      `ownership-inspection` `blocked`.
- [ ] T2. Fan-out: closing `ownership-contract` and `devloop-ownership` makes
      `ownership-inspection` and `executor-fencing` both `ready` in one set.
- [ ] T3. Fan-in with one predecessor open: closing #293 and #352 but not #353 leaves
      `guarded-recovery` `blocked` with exactly one blocker, `ownership-reconciler`.
- [ ] T4. Issue acceptance case: with #293, #352 and #353 all closed as `completed`,
      `guarded-recovery` is `ready` with `blockers: []`.
- [ ] T5. Human Input fresh graph: against `human-input/converged-fixture.json` the
      top-level `ready` list is exactly `["human-input-core"]`.
- [ ] T6. Optional ready item: against the epic #66 live capture, `temporal-health`
      (`required: false`) is `ready` and appears in `ready` while
      `required.ready` counts it zero.
- [ ] T7. Optional item as a real blocker: a required item authored to depend on an
      optional open item is `blocked` on it, proving optionality does not weaken an edge.
- [ ] T8. Unbound item: `unified-identity`'s `principal-model` is `unknown/unbound` and
      never appears in `ready`; the whole epic yields zero `ready` items.
- [ ] T9. Unobserved predecessor: drop one predecessor's observation from the snapshot —
      the dependent item is `unknown/dependency_unknown` with that predecessor listed
      `unknown/unobserved`, and no item flips to `ready`.
- [ ] T10. Missing, redirected and ambiguous bindings, via `mutations.mark_missing()`,
      `mutations.redirect()` and `mutations.add_second_parent()`: `unknown/issue_not_found`,
      the redirected item still scored on its resolved identity, and
      `unknown/binding_ambiguous` respectively — none of the three ever `ready`.
- [ ] T11. External dependency: `telegram-adapter` with mctl-telegram#443 open is
      `blocked` on an `external` blocker; with #443 closed as completed and its internal
      predecessors complete it is `ready`; with #443 unobserved it is `unknown`.
- [ ] T12. Precedence: one predecessor observed incomplete and another unobserved yields
      `blocked`, with both listed in `blockers`.
- [ ] T13. Determinism: the same manifest bytes and snapshot bytes produce byte-identical
      JSON across two runs and across a snapshot whose `issues` array is reordered.
- [ ] T14. Runtime independence: assert `github-graph-snapshot.schema.json` admits no
      runtime/workflow field (`additionalProperties: false`, no such property), and that
      `ready` imports no clock or randomness module — the projection cannot observe
      Temporal/DevLoop state.
- [ ] T15. Schema and consistency: every computed document validates against
      `roadmap-ready-set.schema.json` and yields `consistency_errors() == []`; hand-built
      contradictory documents (a `ready` item with a blocker, a `blocked` item with only
      `complete` blockers, wrong counts, a blocker outside `dependsOn`, a `ready` item with
      no `issue`) are each rejected with a message.
- [ ] T16. Cross-axis agreement: for every epic/fixture pair, each item's echoed
      `completion` block equals the entry `completion.compute()` produces for the same id.
- [ ] T17. No regression: `RoadmapHealth` output for epic #66 and human-input is
      byte-identical before and after the change (golden comparison in `test_ready.py` or
      an assertion added to `test_health.py`), and `ready.py` exit codes match the
      documented table for the healthy, unknown, invalid-corpus and missing-snapshot cases.

## Rollback

The change is additive and confined to `roadmap/`, with no deployed service, no stored
state and no GitHub write path. Reverting the merge commit removes
`roadmap/scripts/ready.py`, `roadmap/schemas/roadmap-ready-set.schema.json`,
`roadmap/tests/test_ready.py` and the two new fixtures, restores the README and the CI
workflow, and undoes the rename in `roadmap/scripts/completion.py`. Nothing else imports
`ready`, so no other module breaks.

If only the CI steps are a problem (for example a fixture turns out to disagree with a
live capture), delete the two new steps from `.github/workflows/roadmap-validate.yml` and
keep the module: `ready.py` is never invoked by `reconcile.py`, `health.py`, `plan.py` or
`apply.py`, so a broken readiness projection cannot affect drift detection, health,
completion or the write boundary. If step 2 is implicated, restore
`completion._colliding_bindings()` as the sole name; `test_completion.py` is the check
that the completion contract is back exactly as it was.
