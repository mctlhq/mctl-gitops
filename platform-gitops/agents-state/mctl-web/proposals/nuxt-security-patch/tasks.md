# Tasks: nuxt-security-patch

- [ ] 1. Bump `nuxt` in `package.json` from `4.3.1` to `4.5.1` (or the latest 4.x patch
      release available at execution time) and update the lockfile — DoD: `package.json`
      and lockfile reflect the new version; `nuxt --version` (or equivalent) reports
      >= 4.5.1.
- [ ] 2. Review and resolve any forced peer dependency changes (Vue, vue-router,
      Nitro) triggered by the bump (depends on 1) — DoD: install completes with no
      unresolved peer dependency warnings; any forced version changes are listed
      explicitly in the PR description.
- [ ] 3. Review `nuxt.config.ts` for `vue.runtimeCompiler` usage and confirm it is
      disabled or not present in production config (depends on 1) — DoD: config
      reviewed and documented; if enabled, a decision is recorded on whether it can be
      turned off.
- [ ] 4. Audit `routeRules` in `nuxt.config.ts` for mixed-case keys guarding
      `appMiddleware` authorization and normalize to lowercase as defense in depth
      (depends on 1) — DoD: all `routeRules` keys reviewed; any mixed-case keys
      guarding auth middleware are normalized.
- [ ] 5. Run a full local/CI build and confirm prerender succeeds for `/`, `/privacy`,
      `/docs` (depends on 1, 2) — DoD: `nuxt build` completes with zero errors and the
      three prerendered routes are present in `dist/`.
- [ ] 6. Write a new ADR under `context/decisions/` documenting the version bump,
      the CVEs it addresses, and any forced peer dependency changes (depends on 1-5)
      — DoD: ADR file committed following the existing ADR format (see ADR 0001).
- [ ] 7. Deploy to `admins` and confirm the live image tag reflects the new Nuxt
      version (depends on 5, 6) — DoD: `mctl_get_service_status`/config for
      admins/mctl-web reports the updated build; site loads correctly at `mctl.ai`.

## Tests
- [ ] T1. Automated/CI build test: `nuxt build` completes without errors after the
      bump.
- [ ] T2. Manual smoke test of `/`, `/privacy`, `/docs` in a preview/staging
      environment — pages render correctly, no console errors.
- [ ] T3. Manual smoke test of the tenant onboarding form and GitHub OAuth login flow
      (island/interactive component regression check).
- [ ] T4. Send a request with an oversized/malformed JSON body to `/__nuxt_island/...`
      in a non-production environment and confirm it is rejected or safely bounded
      (no runaway CPU/memory).
- [ ] T5. Confirm `routeRules`-gated routes correctly enforce `appMiddleware`
      authorization regardless of path case.

## Rollback
If the deploy introduces a regression (build failure caught pre-deploy, or a runtime
issue caught post-deploy): revert the `nuxt` version bump and lockfile change in
`package.json`, redeploy the previous known-good build (Nuxt 4.3.1), and re-open this
proposal for a follow-up attempt. Since this is a static prerendered site with no
database migrations, rollback is a straightforward revert-and-redeploy with no data
cleanup required. If the issue is isolated to the `routeRules`/`runtimeCompiler`
config review (tasks 3-4) rather than the version bump itself, those config changes
can be reverted independently while keeping the version bump in place.
