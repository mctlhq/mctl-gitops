# Tasks: issue-67-feat-roadmap-control-plane-reconcile-epi

- [ ] 1. Add `roadmap/schemas/github-graph-snapshot.schema.json` defining the provider-neutral observed graph. Include explicit provenance under `source`:
      - `mode: live-capture` with `capturedAt` and `apiBase`, or
      - `mode: synthetic-fixture` with optional `derivedFrom` and no live timestamp claim.
      Keep `additionalProperties: false` and the existing issue-ref shape. — DoD: schema self-check passes; unknown top-level fields are rejected; invalid provenance combinations fail.
- [ ] 2. Add `roadmap/schemas/roadmap-diff.schema.json` defining `kind: RoadmapDiff` with epic, exact manifest path/SHA-256, source metadata copied from the snapshot, summary counts, and separate `binding` / `hierarchy` / `dependency` collections. — DoD: converged and drifting examples validate.
- [ ] 3. Add `roadmap/scripts/github_graph.py` with snapshot loading, schema validation, `FixtureGraphSource`, and `observed_graph()` normalization: lowercase repository identity for comparison, sort/deduplicate relations, drop self-edges, retain requested vs resolved identity. — DoD: schema-invalid snapshots fail with JSON-path style diagnostics.
- [ ] 4. Add `LiveGraphSource` using **GitHub REST GET-only** reads. For each referenced issue use:
      - `GET /repos/{owner}/{repo}/issues/{number}` for existence/state and canonical/redirect identity;
      - `GET .../parent`;
      - `GET .../sub_issues`;
      - `GET .../dependencies/blocked_by`.
      Do not use GraphQL in this slice. Funnel all HTTP through one helper that rejects any non-GET method or request body before transmission. — DoD: stubbed-opener tests prove only GET is emitted; forced POST/body raises `WriteAttempted`; transferred/redirected issue preserves requested and resolved keys.
- [ ] 5. Add validation preflight in `roadmap/scripts/reconcile.py`: load all selected manifests, run `validate.validate_document` for each, then run the existing `validate.corpus_errors` across the whole selected set **before any live GitHub read**. — DoD: duplicate `metadata.name` and duplicate GitHub issue binding across two individually valid manifests both exit 2 and the stubbed live source records zero requests.
- [ ] 6. Add `desired_graph()` to `reconcile.py`: derive `(parent, child)` hierarchy edges from root/`parent`, `(blocked, blocker)` dependency edges from `dependsOn` and `externalDependsOn`, and suppressions for intentionally unbound endpoints. Phase order must never produce an edge. — DoD: Human Input yields the expected bound hierarchy/dependency set and unbound `devloop-e2e` contributes no edge.
- [ ] 7. Implement `diff()` with separate binding/hierarchy/dependency collections and these types: `BindingIssueNotFound`, `BindingRedirected`, `BindingAmbiguous`, `BindingUnbound`, `HierarchyMissingParent`, `HierarchyWrongParent`, `HierarchyUnexpectedChild`, `DependencyMissing`, `DependencyUnexpected`. Compute binding failures first and suppress dependent edge comparisons. — DoD: every type is reachable in tests; one missing binding produces no cascade of hierarchy/dependency noise.
- [ ] 8. Implement deterministic serialization: sorted collections, exact manifest-byte SHA-256, source metadata copied from snapshot, no clock/randomness in `RoadmapDiff`, stable JSON encoding. — DoD: two runs over identical bytes produce byte-identical output regardless of input ordering.
- [ ] 9. Add the CLI with positional manifests plus `--snapshot`, `--live`, `--capture`, `--output`. Preserve exit codes 0 converged / 1 drift / 2 usage-IO-credentials-validation error. Live mode must not start until schema, semantic, and corpus validation all pass. — DoD: tests exercise all three codes and prove invalid/corpus-invalid input causes zero network calls.
- [ ] 10. Capture optional immutable `roadmap/fixtures/human-input/live-capture.json` from GitHub if useful for evidence/debugging. It must be marked `source.mode: live-capture`, include real capture provenance, and must not be hand-edited to become green. — DoD: the artifact, if committed, validates and is reproducible via documented capture command.
- [ ] 11. Add `roadmap/fixtures/human-input/converged-fixture.json` as the **synthetic** green test graph. It may be derived from a live capture but must be marked `source.mode: synthetic-fixture`; if derived, record `derivedFrom`, and do not claim a live capture timestamp. — DoD: Human Input reconciles with zero drift-severity entries and only informational `BindingUnbound` for `devloop-e2e`.
- [ ] 12. Add `roadmap/tests/mutations.py` with pure deep-copy mutators for parent edge, dependency edge, and issue binding changes. — DoD: input object remains unchanged; inverse/restoration returns an object equal to the original fixture.
- [ ] 13. Add `roadmap/tests/test_reconcile.py` covering converged, hierarchy drift, dependency drift, binding drift, wrong parent, unexpected dependency, ambiguity, normalization, unbound info, redirect handling, corpus-validation preflight, read-only transport, deterministic output, provenance rules, and all exit codes. — DoD: full unittest discovery passes offline.
- [ ] 14. Add fixture-mode reconciliation to `.github/workflows/roadmap-validate.yml` after existing validation. Keep top-level `permissions: {}`, no token, no live mode, SHA-pinned checkout unchanged. — DoD: roadmap-only PR runs green without secrets.
- [ ] 15. Extend `roadmap/README.md` with reconciliation modes, exit codes, diff types, corpus-validation preflight, GET-only live contract, redirect semantics, capture command, and the distinction between immutable live capture and synthetic green fixture. — DoD: commands run as written from a clean checkout.
- [ ] 16. Confirm `roadmap/requirements.txt` is unchanged and no new runtime dependency is introduced. — DoD: installing existing requirements is sufficient for validator, reconciler, and tests.

## Tests

- [ ] T1. Converged: `human-input.yaml` + `converged-fixture.json` produce zero drift-severity entries and exit 0.
- [ ] T2. Hierarchy missing: drop one expected parent edge → exactly one `HierarchyMissingParent`, dependency collection unchanged, exit 1.
- [ ] T3. Wrong parent: re-point one child → exactly one `HierarchyWrongParent` with expected + observed parent.
- [ ] T4. Dependency missing: drop one authored blocker → exactly one `DependencyMissing`, hierarchy unchanged.
- [ ] T5. Unexpected dependency: add one unauthored `blockedBy` edge → exactly one `DependencyUnexpected`.
- [ ] T6. Binding failure: change one bound issue identity → one binding failure and no cascaded edge failures.
- [ ] T7. Redirect/transfer: requested issue resolving to another repo/number → exactly one `BindingRedirected`, requested/resolved identities retained.
- [ ] T8. Restoration: each mutation restored to the original object reconciles green again.
- [ ] T9. Phase order is not dependency.
- [ ] T10. Unbound `devloop-e2e` → one informational `BindingUnbound`, no edge, exit remains 0.
- [ ] T11. Corpus invariant: two individually valid manifests binding the same GitHub issue fail with exit 2 before any network request.
- [ ] T12. Corpus invariant: duplicate `metadata.name` fails with exit 2 before any network request.
- [ ] T13. Read-only transport: live adapter emits only GET and no body; forced non-GET/body raises before I/O.
- [ ] T14. REST relation coverage: issue, parent, sub-issues, and blocked-by responses normalize into the same provider-neutral graph shape.
- [ ] T15. Determinism: same manifest/snapshot bytes → byte-identical JSON; shuffled issue/relation order does not affect output.
- [ ] T16. Output contract validates in converged and drifting cases.
- [ ] T17. Exit codes: 0 converged, 1 drift, 2 malformed snapshot / invalid manifest / corpus failure / missing live credentials.
- [ ] T18. Ambiguity: one issue observed under two parents → one `BindingAmbiguous`.
- [ ] T19. Repository casing differences still reconcile green.
- [ ] T20. Provenance: synthetic fixture cannot claim `source.mode: live-capture`; live capture requires capture provenance; hand-converged test fixture is represented only as `synthetic-fixture`.

## Rollback

Everything remains additive and read-only. Rollback is a plain revert of the implementation PR: remove reconciler scripts/schemas/fixtures/tests and revert the CI/README additions. No GitHub graph state or manifest is mutated by this slice.

If only live REST handling breaks because GitHub changes an API shape, fixture mode and detector logic remain valid and the adapter can be fixed independently. If only the CI fixture step causes trouble, remove that one step while leaving the offline validator untouched.
