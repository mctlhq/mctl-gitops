# Tasks: nuxt-security-upgrade

- [ ] 1. Capture baseline memory (RSS/working set) of mctl-web in `admins` and `labs` — DoD: numbers recorded in the PR description.
- [ ] 2. Bump `nuxt` to 4.6.4 and regenerate lockfile with nitropack 2.13.6 — DoD: lockfile shows both versions; `nuxt build` passes.
- [ ] 3. Verify prerender and SSR of `/`, `/privacy`, `/docs` (depends on 2) — DoD: outputs match expected content, no console errors.
- [ ] 4. Run dependency audit (depends on 2) — DoD: none of CVE-2026-114131, -119200, -114133, -120309, -114130 reported.
- [ ] 5. Coordinate with `nuxt-4-6-behavior-audit` (depends on 2) — DoD: audit findings merged together or immediately after.
- [ ] 6. Roll out to `admins` (depends on 3, 4, 5) — DoD: ArgoCD Synced/Healthy, smoke tests pass.
- [ ] 7. Measure memory in `admins`, then promote to `labs` only if delta is within 5% (depends on 1, 6) — DoD: delta recorded; `labs` promoted or held.
- [ ] 8. Ask maintainer to update `context/current-version.md` and add an ADR (depends on 6) — DoD: both updated.

## Tests
- [ ] T1. `nuxt build` succeeds and prerenders all three routes.
- [ ] T2. Request `/%2e/admin` and `/%2e/privacy` returns 404 or a redirect and does not render a keyed page.
- [ ] T3. Dependency audit reports none of the listed CVEs.
- [ ] T4. Memory on `labs` after rollout is within 5% of baseline over 24h.

## Rollback
Revert the PR (or pin `nuxt` back to 4.3.1 with the old lockfile) and redeploy the previous image tag via ArgoCD. If only `labs` regresses on memory, keep `labs` on the previous image and leave `admins` on 4.6.4.
