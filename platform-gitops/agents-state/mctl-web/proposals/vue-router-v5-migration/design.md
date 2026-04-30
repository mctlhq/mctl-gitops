# Design: vue-router-v5-migration

## Current state
`package.json` pins `"vue-router": "4.6.4"`. In a Nuxt project, vue-router is typically a peer dependency managed by Nuxt's own `@nuxt/kit` / `nuxt` package — the effective version in `node_modules` is resolved by Nuxt's peer-dep range. mctl-web does not use `unplugin-vue-router` or typed routes today. Routes are three simple pages: `/`, `/docs`, `/privacy`.

## Proposed solution
This is a **planning proposal** with two phases:

**Phase 1 — Compatibility audit (this proposal):**
1. Determine whether Nuxt 4.4.4 (post upgrade from `nuxt-upgrade-4-4`) declares a peer-dep range that includes vue-router v5.
2. Review the vue-router v5 migration guide for any breaking changes relevant to Nuxt SSR+prerender mode.
3. Test the upgrade in a feature branch: bump `"vue-router": "5.0.6"` in `package.json`, run `npm install`, and run the three smoke-test scenarios.
4. Document findings in an ADR (`0002-vue-router-v5-migration.md`).

**Phase 2 — Execution (follow-up PR, after Phase 1 confirms compatibility):**
1. Bump vue-router to v5 in `package.json`.
2. Enable typed routes in `nuxt.config.ts` (`experimental.typedPages: true` or the v5 equivalent).
3. Update any `useRouter()` / `useRoute()` calls if their API changed.
4. Merge and deploy.

The migration is expected to be low-risk for mctl-web given:
- Only three routes exist; none use dynamic segments or nested named views.
- No `unplugin-vue-router` is present, placing mctl-web in the "zero breaking changes" migration category per v5 release notes.
- The Cloudflare Worker handles `/api/*` independently of vue-router.

## Alternatives
1. **Stay on vue-router 4.6.4 indefinitely** — defers risk but accumulates technical debt and may eventually block Nuxt upgrades that require v5. Rejected.
2. **Adopt unplugin-vue-router first, then upgrade to v5** — unnecessary complexity; v5 already integrates it. Rejected.
3. **Switch to a different router** — violates the spirit of ADR 0001 (stay in the Nuxt/Vue ecosystem). Rejected.

## Platform impact
- **Migrations:** Requires a compatibility audit before any code change. Phase 2 may require minor updates to `nuxt.config.ts`.
- **Backward compatibility:** vue-router v5 is declared backward-compatible for projects not using `unplugin-vue-router`. Risk is low.
- **Resource impact:** No meaningful bundle size change for three static routes. No impact on `labs` tenant memory.
- **Risks and mitigations:** Primary risk is Nuxt 4.x not yet officially supporting vue-router v5 in its peer-dep range. Mitigation: Phase 1 audit gate; do not proceed to Phase 2 without confirmed Nuxt compatibility.
