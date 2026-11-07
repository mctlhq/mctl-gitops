# Tasks: playwright-1-65-upgrade

- [ ] 1. Bump `@playwright/test` to 1.65.x and reinstall browsers — DoD: lockfile updated, CI image builds.
- [ ] 2. Triage failures vs breaking changes (depends on 1) — DoD: all tests pass or are fixed with notes.
- [ ] 3. Add `failures` reporter in CI config (depends on 1) — DoD: CI log shows failures output.

## Tests
- [ ] T1. Full e2e on Node 22 and Node 24.
- [ ] T2. Three consecutive green runs to rule out flakiness.

## Rollback
Revert the dependency bump and lockfile.
