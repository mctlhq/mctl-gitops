# Tasks: vue-router-v5-migration

- [ ] 1. Check Nuxt 4.4.4's `package.json` peer-dep range for vue-router to confirm whether v5 is within the accepted range — DoD: finding documented in the PR description (yes/no/partial).
- [ ] 2. Read the official vue-router v5 migration guide and flag any breaking changes relevant to SSR+prerender usage — DoD: short notes added to the PR description; no unresolved breaking changes, or issues listed.
- [ ] 3. Create a feature branch; bump `"vue-router"` in `package.json` to `"5.0.6"`; run `npm install` — DoD: no unresolved peer-dependency conflicts; lockfile committed.
- [ ] 4. Run `nuxt build` on the feature branch — DoD: build exits 0 with no new errors or warnings related to the router.
- [ ] 5. Smoke-test navigation on a preview deploy: visit `/`, `/docs`, `/privacy` and confirm correct rendering and no console warnings — DoD: all three pages render; browser console is clean.
- [ ] 6. If Phase 1 passes: enable typed routes (`experimental.typedPages: true` in `nuxt.config.ts`) and confirm TypeScript compilation succeeds — DoD: `tsc --noEmit` exits 0.
- [ ] 7. Write ADR `0002-vue-router-v5-migration.md` documenting the decision and outcome — DoD: ADR merged to `context/decisions/`.
- [ ] 8. (Phase 2, after ADR accepted) Merge to main and deploy — DoD: production site navigates correctly; no router errors in Cloudflare logs.

## Tests
- [ ] T1. `nuxt build` exits 0 on the feature branch with vue-router@5.0.6.
- [ ] T2. All three prerendered routes (`/`, `/docs`, `/privacy`) return HTTP 200 and correct HTML content.
- [ ] T3. TypeScript compilation (`tsc --noEmit`) exits 0 with typed routes enabled.
- [ ] T4. No `[Vue Router warn]` messages in the browser console during navigation.

## Rollback
Revert `package.json` to `vue-router@4.6.4`, run `npm install`, and redeploy. Since this proposal gates execution behind a Phase 1 audit, there is no production risk until Phase 2 is explicitly triggered.
