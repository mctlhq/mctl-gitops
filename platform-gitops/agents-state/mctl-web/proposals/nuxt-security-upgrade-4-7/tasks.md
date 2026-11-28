# Tasks: nuxt-security-upgrade-4-7

- [ ] 1. Confirm actual installed versions from package.json — DoD: versions recorded in the PR.
- [ ] 2. Run nuxt upgrade --dedupe (depends on 1) — DoD: lockfile updated, nuxt>=4.6.4.
- [ ] 3. Fix new diagnostics/warnings (depends on 2) — DoD: clean build.
- [ ] 4. Purge CDN payload cache if route rules cache pages (depends on 2) — DoD: documented in PR.

## Tests
- [ ] T1. CI build and prerender of /, /docs, /privacy succeed.
- [ ] T2. Smoke test of the affected behaviour (nuxt-security-upgrade-4-7).

## Rollback
Revert the PR (lockfile / config) and redeploy; for the Worker, redeploy the previous wrangler deploy.
