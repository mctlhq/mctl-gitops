# Tasks: issue-161-ci-roadmap-fail-validation-when-a-change

- [ ] 1. Add pure, deep-copying manifest mutators to `roadmap/tests/mutations.py`: `add_required_item`, `set_required` and `set_lifecycle`. — DoD: input documents are unchanged; outputs remain valid EpicDefinitions where intended.
- [ ] 2. Implement `roadmap/scripts/lifecycle_guard.py` with:
  - `BaseError` and exit-code mapping 0/1/2;
  - `load_base_from_git` using fixed argv/no shell;
  - recursive base enumeration via `git ls-tree -rz --name-only`;
  - `load_base_from_dir` for tests;
  - head validation through both `validate.validate_document` and `validate.corpus_errors`;
  - pure `check()` returning `RequiredItemAdded`, `RequiredFlagRaised` and `BornCompletedUnverified`.
  — DoD: `python3 roadmap/scripts/lifecycle_guard.py --base-dir roadmap/epics --head-dir roadmap/epics` exits 0; no network I/O.
- [ ] 3. (depends on 2) Wire the guard into `.github/workflows/roadmap-validate.yml`:
  - checkout with `fetch-depth: 0`;
  - on `pull_request`, compute `git merge-base "$BASE_SHA" "$HEAD_SHA"`, failing if it cannot be resolved;
  - on normal push, use `$BEFORE`;
  - for all-zero `before`, add a dedicated warning step and make the real guard step conditionally **skipped**, not green-by-`exit 0`;
  - pass event values through `env:`;
  - keep `permissions: {}`.
  — DoD: workflow YAML parses/actionlint passes; zero-base push shows a warning and a skipped guard step.
- [ ] 4. (depends on 2) Add one paragraph to `roadmap/README.md` under `## Validation`, plus file-list entries for the new script/test. Document the three violation codes, exit-2 fail-closed behavior, legitimate reopen/optional paths, and why a new epic with required work cannot be born completed in offline CI.
- [ ] 5. (depends on 3) Produce CI evidence in the implementation PR:
  - current/converged tree: green;
  - #152 mutation (`trajectory-economics` required while FinOps stays completed): red with `RequiredItemAdded`;
  - same mutation with the guard workflow step removed: green, proving the guard is the load-bearing control;
  - #162 rebased on current main: green.
  Add links/results to the PR description. Do not claim the third run is red.

## Tests

- [ ] T1. Unchanged corpus: `check(corpus, corpus)` is empty.
- [ ] T2. #152 mutation gives exactly one `RequiredItemAdded` naming `trajectory-economics`.
- [ ] T3. Same addition with `required: false` gives no violation.
- [ ] T4. Existing optional item raised to required gives `RequiredFlagRaised`.
- [ ] T5. Mutation plus lifecycle `active`, and separately `paused`, gives no violation.
- [ ] T6. Stale-base case: base active, head completed with added required item gives `RequiredItemAdded`.
- [ ] T7. Born-completed fail-closed behavior:
  - new completed manifest with an unbound required item gives `BornCompletedUnverified`;
  - new completed manifest with a **bound** required item also gives `BornCompletedUnverified` because closed state is not observable offline;
  - a new active/paused manifest with the same work is allowed.
- [ ] T8. Deleted-in-head completed epic gives no violation. Removing required work or lowering `required` gives no violation.
- [ ] T9. Pairing: moving a manifest while retaining the same `metadata.name` pairs it with the base rather than treating it as new.
- [ ] T10. Git base loader:
  - temp repository parent/head path works;
  - multiple YAML manifests under `roadmap/epics/` are all enumerated;
  - a test fails if recursive `-r` is removed from `git ls-tree`.
- [ ] T11. Exit-2 errors have distinct prefixes:
  - unknown/missing base -> `base-unresolvable:`;
  - shallow clone missing the base -> `base-unresolvable:` plus shallow hint;
  - invalid base YAML/shape -> `base-malformed:`;
  - failed tree/blob read -> `base-unreadable:`;
  - schema-invalid or corpus-invalid/duplicate-name head -> `head-invalid:`.
- [ ] T12. Workflow zero-base behavior is pinned by a focused workflow-text/YAML test or equivalent: the warning path exists and the real guard step has an `if:` that skips that case rather than exiting 0 inside the guard.
- [ ] T13. Revert/load-bearing proof: patch `check` to return `[]` and assert the #152 mutation assertion fails.
- [ ] T14. `python3 -m unittest discover -s roadmap/tests -p 'test_*.py'` and `python3 roadmap/scripts/validate.py roadmap/epics` remain green.

## Rollback

Revert the implementation PR. The guard is additive: script, tests, workflow wiring and README only. No schema or manifest format changes are introduced.
