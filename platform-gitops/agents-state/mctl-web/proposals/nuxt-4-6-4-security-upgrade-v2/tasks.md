# Tasks: nuxt-4-6-4-security-upgrade-v2

- [ ] 1. Confirm real Nuxt version in package.json — DoD: recorded in PR.
- [ ] 2. Bump nuxt and lockfile (depends on 1) — DoD: npm audit shows no Nuxt advisories.
- [ ] 3. Build and prerender (depends on 2) — DoD: dist/ output matches expected routes.
- [ ] 4. Update context/current-version.md and add an ADR via the owner process (depends on 3) — DoD: docs match.

## Tests
- [ ] T1. nuxt build succeeds with prerender of 3 routes.
- [ ] T2. Dev server works with default host.

## Rollback
Revert the PR and redeploy the previous build (Worker: wrangler rollback).
