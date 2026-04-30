# Design: nuxt-upgrade-4-4

## Current state
`package.json` pins `"nuxt": "4.3.1"`. The build pipeline runs `nuxt build` → output served as static from `dist/`. SSR is enabled with prerender for `/`, `/privacy`, `/docs`. Vue 3.5.30, vue-router 4.6.4, vee-validate 4.15.1, yup 1.7.1, @vueuse/core 14.2.1, sass 1.98.0 are co-dependencies.

## Proposed solution
Bump `"nuxt"` in `package.json` from `"4.3.1"` to `"4.4.4"` and run `npm install` to regenerate the lockfile. v4.4.4 is a re-publish of v4.4.3 (identical code); use 4.4.4 as the target. No changes to `nuxt.config.ts` are expected; the upgrade is within the same minor semver band and declared non-breaking.

Key improvements landed in this upgrade:
- **Hydration fixes** — reduced hydration mismatch errors on first load, improving UX for the registration flow.
- **Cookie serialization** — server-set cookies now correctly follow RFC serialization; relevant to OAuth callback in the Cloudflare Worker handing off state to Nuxt.
- **Nitro import caching** — reduces cold-start time for the Nitro server layer.
- **Vite/Webpack manifest handling** — faster `nuxt build` and more reliable chunk references in the output.

## Alternatives
1. **Stay on 4.3.1** — no risk, but accumulates technical debt; the hydration and cookie bugs are active issues for the onboarding flow. Rejected.
2. **Jump directly to Nuxt 5 (if available)** — not yet stable; premature. Rejected.
3. **Pin to 4.4.3 instead of 4.4.4** — 4.4.4 is identical code, just a clean re-publish. No reason to prefer 4.4.3. Rejected.

## Platform impact
- **Migrations:** None expected; v4.4.x is backward-compatible with v4.3.x configurations.
- **Backward compatibility:** All existing routes (`/`, `/docs`, `/privacy`) and the Cloudflare Worker (`/api/*`) are unaffected.
- **Resource impact:** Nitro import caching may slightly reduce build memory peak. No runtime memory change for the Worker. No impact on `labs` tenant.
- **Risks and mitigations:** Low. Mitigation: run `nuxt build` locally and inspect the output before merging; check browser console for hydration errors on a staging deploy.
