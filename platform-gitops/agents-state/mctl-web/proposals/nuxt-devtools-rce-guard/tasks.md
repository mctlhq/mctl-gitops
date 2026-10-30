# Tasks: nuxt-devtools-rce-guard

- [ ] 1. Check resolved @nuxt/devtools version in lockfile — DoD: version recorded in PR.
- [ ] 2. Bump/override to >= 3.3.1 (depends on 1) — DoD: lockfile updated.
- [ ] 3. Gate devtools in nuxt.config.ts to dev only — DoD: prod build has no devtools.
- [ ] 4. Add CI lockfile version check (depends on 2) — DoD: fails on older version.

## Tests
- [ ] T1. Production build contains no devtools code.
- [ ] T2. CI check fails with a downgraded fixture.

## Rollback
Revert the PR; restore previous lockfile.
