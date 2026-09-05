# Tasks: playwright-test-locks-upgrade

- [ ] 1. Re-confirm the Playwright v1.63.0 release notes and version number against
      the live GitHub releases page (the researcher flagged the fetched date as
      possibly stale/cached) — DoD: version and Test Locks feature availability
      confirmed directly from source before proceeding.
- [ ] 2. Bump `playwright` / `@playwright/test` devDependency to the confirmed
      v1.63.0 (or later patch) in the workspace root `package.json`; update
      `yarn.lock` (depends on 1) — DoD: `yarn install` completes cleanly.
- [ ] 3. Run the full existing e2e suite against the bumped version with no spec
      changes (depends on 2) — DoD: suite passes at the same or better rate as
      pre-bump baseline; any new failures are triaged and fixed before proceeding.
- [ ] 4. Audit existing e2e specs to identify tests that touch shared external
      state (scaffolder-created test services, shared Dex auth sessions, shared k8s
      test namespaces) (depends on 3) — DoD: a short list of contention-prone specs
      is documented in the PR description.
- [ ] 5. Add named Test Lock annotations to the specs identified in task 4 (depends
      on 4) — DoD: annotated specs no longer run concurrently with others holding
      the same lock, verified by a local/CI run with parallel workers enabled.
- [ ] 6. Merge and monitor the next several CI runs for flakiness reduction (depends
      on 5) — DoD: no new flaky failures introduced; contention-related failures in
      the annotated specs are reduced or eliminated over the following week.

## Tests
- [ ] T1. CI: full e2e suite green immediately after the version bump (before any
      lock annotations), confirming the bump alone is non-breaking.
- [ ] T2. CI: full e2e suite green after Test Lock annotations are added.
- [ ] T3. Manual/CI: run the annotated specs with multiple parallel workers and
      confirm locked specs execute serially (no interleaved shared-state
      corruption).
- [ ] T4. Regression watch: track CI flake rate for the annotated specs over the
      following week to confirm the intended reliability improvement.

## Rollback
Revert the `playwright` / `@playwright/test` devDependency version bump and remove
any added Test Lock annotations, then restore the previous `yarn.lock`. Since this
is a dev/CI-tooling-only change with no production runtime component, rollback has
no user-facing or production impact — it only affects the CI pipeline and local
developer e2e runs.
