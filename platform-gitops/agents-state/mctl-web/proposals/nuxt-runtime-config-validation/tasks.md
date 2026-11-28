# Tasks: nuxt-runtime-config-validation

- [ ] 1. Grep for apiSecret usage — DoD: usage list recorded.
- [ ] 2. Add yup schema to nuxt.config.ts (depends on proposal nuxt-security-upgrade-4-7) — DoD: invalid config fails build.
- [ ] 3. Remove placeholder (depends on 1) — DoD: no '123' value remains.

## Tests
- [ ] T1. CI build and prerender of /, /docs, /privacy succeed.
- [ ] T2. Smoke test of the affected behaviour (nuxt-runtime-config-validation).

## Rollback
Revert the PR (lockfile / config) and redeploy; for the Worker, redeploy the previous wrangler deploy.
