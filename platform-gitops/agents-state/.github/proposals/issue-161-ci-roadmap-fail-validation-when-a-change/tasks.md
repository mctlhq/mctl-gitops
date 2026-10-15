# Tasks: issue-161-ci-roadmap-fail-validation-when-a-change

- [ ] 1. Add manifest mutators `add_required_item`, `set_required` and `set_lifecycle` to `roadmap/tests/mutations.py`. Keep them pure and deep-copying, like `unbind`. — DoD: each returns a copy; the input is unchanged; the result still passes `validate.validate_document` (an unbound added item carries `title`/`owner`).
- [ ] 2. Implement `roadmap/scripts/lifecycle_guard.py`: `BaseError`, `load_base_from_git`, `load_base_from_dir`, head loading through `validate` helpers, the pure `check()` returning `RequiredItemAdded`/`RequiredFlagRaised`/`BornCompletedUnbound`, and a `main()` with exit codes 0/1/2 and the `base-unresolvable:`/`base-unreadable:`/`base-malformed:`/`head-invalid:` prefixes. — DoD: `python3 roadmap/scripts/lifecycle_guard.py --base-dir roadmap/epics --head-dir roadmap/epics` exits 0; `git` runs only with fixed argv and no shell; no network I/O.
- [ ] 3. (depends on 2) Wire the guard into `.github/workflows/roadmap-validate.yml`: `fetch-depth: 0` on checkout, and a new guard step after "Validate EpicDefinition manifests" that computes `git merge-base "$BASE_SHA" "$HEAD_SHA"` on `pull_request` (and fails the job if that fails), uses `$BEFORE` on `push`, and emits a `::warning::` no-base notice on an all-zero `before`. Event values go through `env:`. — DoD: `permissions: {}` unchanged; the workflow parses (actionlint or a dry YAML load); the step is green on a no-op roadmap PR.
- [ ] 4. (depends on 2) Add one paragraph to `roadmap/README.md` under `## Validation` describing the guard, its error codes and the two legitimate ways to extend a completed epic. Add `lifecycle_guard.py` and `test_lifecycle_guard.py` to the file listing near line 65/80. — DoD: the README matches the implemented CLI and codes.
- [ ] 5. (depends on 3) Prove it both ways in CI and paste the three run links in the PR description. (a) The PR itself: guard green on the current `roadmap/epics` against its merge base. (b) A throwaway branch that reapplies the #152 hunk, adding a required `trajectory-economics` item to `roadmap/epics/agent-finops.yaml` while it stays `lifecycle: completed`: guard red with `RequiredItemAdded`. (c) The same mutation with the guard step removed: green, showing the guard is the only thing that catches it. Also confirm the guard passes on #162 rebased onto current `main`. — DoD: three links in the PR plus the #162 result.

## Tests
- [ ] T1. Unchanged corpus: `check(corpus, corpus)` is empty for the real `roadmap/epics`.
- [ ] T2. #152 mutation: `add_required_item(agent-finops, "trajectory-economics")` with lifecycle `completed` gives exactly one `RequiredItemAdded` naming that id.
- [ ] T3. Optional addition: the same item with `required: false` gives no violation.
- [ ] T4. Flip: `set_required(item, True)` on an item that is optional in base gives `RequiredFlagRaised`.
- [ ] T5. Reopen: the mutation plus `set_lifecycle("active")`, and separately `"paused"`, gives no violation.
- [ ] T6. Stale base: base `active`, head `completed` with an added required item gives `RequiredItemAdded`.
- [ ] T7. Born completed: a new manifest, `completed`, with an unbound required item gives `BornCompletedUnbound`. The same manifest with all required items bound passes and prints them as "closure not verified".
- [ ] T8. Deleted in head: a completed base epic absent from head gives no violation. Removing required items, or lowering `required`, gives no violation.
- [ ] T9. Pairing: a manifest moved to a new path with the same `metadata.name` is paired, not treated as new.
- [ ] T10. Git base: in a temp repo, `main(["--base-ref", <parent>])` exits 1 on the mutation and 0 on the converged commit.
- [ ] T11. Errors (exit 2, distinct prefix each): an unknown SHA gives `base-unresolvable:`; a `git clone --depth 1` without the base commit gives `base-unresolvable:` with a shallow hint; a base manifest with invalid YAML, or one missing `required` on an item, gives `base-malformed:`; an unlistable or unreadable base path (simulated by a stubbed git runner) gives `base-unreadable:`; a schema-invalid head gives `head-invalid:`.
- [ ] T12. Revert proof: patching `check` to return `[]` makes the T2 assertion fail. Implement this with `unittest.mock.patch` inside a helper that runs T2's body and asserts the failure, so the suite proves the guard is load-bearing.
- [ ] T13. `python3 -m unittest discover -s roadmap/tests -p 'test_*.py'` passes, and `validate.py roadmap/epics` passes unchanged.

## Rollback
Revert the PR. The guard is additive: one new script, one new test file, mutators, one workflow step, `fetch-depth: 0` and a README paragraph. No manifest, schema or other script depends on it. For an urgent unblock without a full revert, delete only the guard step from `roadmap-validate.yml` in a reviewed PR. That restores the previous behaviour exactly; `fetch-depth: 0` is harmless if left in place.
