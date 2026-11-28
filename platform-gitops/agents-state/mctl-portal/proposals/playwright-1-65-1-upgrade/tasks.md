# Tasks: playwright-1-65-1-upgrade

- [ ] 1. Check the current Playwright version and reconcile with `playwright-1-65-1-bump` — DoD: decision recorded in the PR.
- [ ] 2. Bump `@playwright/test` to 1.65.1 (depends on 1) — DoD: lockfile updated, suite loads.
- [ ] 3. Add the catalog/scaffolder smoke spec (depends on 2) — DoD: passes locally and in CI.
- [ ] 4. Wire the smoke spec as a post-upgrade gate (depends on 3) — DoD: documented in the README.

## Tests
- [ ] T1. Full existing e2e suite passes on 1.65.1.
- [ ] T2. Smoke spec fails when a location is deliberately broken.

## Rollback
Revert the package.json and lockfile change; remove the smoke spec if flaky.
