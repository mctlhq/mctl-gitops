# Tasks: nuxt-upgrade-4-6-2

- [ ] 1. Bump nuxt to 4.6.2 and refresh lockfile — DoD: install succeeds.
- [ ] 2. Run build and prerender (depends on 1) — DoD: 3 routes generated.
- [ ] 3. Diff dist output vs previous (depends on 2) — DoD: only expected changes.
- [ ] 4. Deploy to preview and smoke test (depends on 3) — DoD: pages render.

## Tests
- [ ] T1. nuxt build passes in CI.
- [ ] T2. Smoke test of /, /docs, /privacy.

## Rollback
Revert the bump commit; redeploy previous image tag via mctl rollback.
