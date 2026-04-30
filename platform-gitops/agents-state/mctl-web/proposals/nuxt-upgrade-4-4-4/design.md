# Design: nuxt-upgrade-4-4-4

## Current state
See `context/architecture.md` for the full stack description.

mctl-web is a Nuxt 4.3.1 SSG site. SSR is enabled in the Nuxt config but pages `/`, `/docs`, and `/privacy` are prerendered at build time and served as static assets via Cloudflare Pages. Dynamic API traffic is handled by a separate Cloudflare Worker (`cloudflare-worker/`). Vue 3.5.30, vue-router 4.6.4, vee-validate 4.15.1, yup 1.7.1, and @vueuse/core 14.2.1 are the primary runtime dependencies.

The project has an outstanding older proposal (`nuxt-upgrade-4-4-2`) that was written for an intermediate release. This proposal replaces it with the final stable target.

## Proposed solution

Bump `nuxt` in `package.json` from `4.3.1` to `4.4.4` (and lock-file update). No other direct dependency changes are introduced unless Nuxt's own peer-dependency requirements mandate them.

Key improvements included in this bump:

| Area | Change | Mechanism |
|---|---|---|
| Dev server | Up to 28x faster route change HMR | TypeScript path-resolution cache introduced in v4.4.2 |
| Build performance | Parallel module loading | Nuxt internals change, no config required |
| Bundle size | Nitro import optimization | Automatic via updated Nitro version shipped with Nuxt 4.4.x |
| Bug fixes | Cookie serialization, async data, hook cleanup, error handling | Patch-level fixes in v4.4.0–4.4.4 |
| Router | Vue Router v5 opt-in support | Available but not activated in this proposal |

The upgrade is intentionally narrow: only `nuxt` is bumped. Vue Router v5 opt-in is left for a dedicated migration proposal (previously tracked under `nuxt-upgrade-4-4-2`) because it carries its own breaking-change surface.

After bumping, the CI pipeline (`deploy.yml`) runs `nuxt build` and the output is deployed to Cloudflare Pages unchanged — no serving-layer changes are needed.

## Alternatives

**1. Upgrade to 4.4.4 and simultaneously migrate to Vue Router v5**
This was the approach in `nuxt-upgrade-4-4-2`. Dropped here because combining the Nuxt bump with a router major migration increases the blast radius: if a regression appears post-deploy it is harder to bisect. Keeping them separate gives a clean rollback boundary.

**2. Stay on 4.3.1 until a future LTS or security release**
Dropped because the accumulated bug fixes (cookie serialization, async data handling) directly affect the tenant registration flow which is a critical user path. The 28x dev-server speedup also has a real developer-productivity cost that compounds daily. There is no known breaking change in 4.4.x that would justify delaying.

**3. Pin to 4.4.3 instead of 4.4.4**
v4.4.4 is a clean re-publish of v4.4.3 issued because the v4.4.3 release script had an artifact issue. Using 4.4.4 ensures npm resolves the intended, correctly published package. Pinning to 4.4.3 would pull the same code but via the affected release artifact — dropped for that reason.

## Platform impact

**Migrations**
- `package.json` and `package-lock.json` (or `pnpm-lock.yaml`) updated to pin `nuxt@4.4.4`.
- Any transitive peer-dependency warnings surfaced by `npm install` / `pnpm install` must be reviewed and resolved before merge.

**Backward compatibility**
- Nuxt 4.4.x maintains the same public API as 4.3.x; no page or composable rewrites are expected.
- Vue Router v5 is opt-in only; the existing `vue-router@4.6.4` dependency is not touched, so all routing behavior is preserved.
- The Cloudflare Worker is not affected by the Nuxt bump.

**Resource impact**
- `mctl-web` runs under the `admins` tenant, not `labs`. This change does not touch `labs` resources.
- Nitro import optimizations are expected to reduce the production bundle size slightly, which benefits Cloudflare Pages edge distribution. No increase in resource usage is anticipated.
- Dev-server memory footprint may change marginally due to the TypeScript cache; this is a developer-machine concern, not a platform concern.

**Risks and mitigations**
| Risk | Likelihood | Mitigation |
|---|---|---|
| Transitive dependency conflict with vee-validate or @vueuse/core | Low | Run `npm install` in a branch; inspect peer-dep warnings; pin if needed |
| A patch in 4.4.x changes behavior relied upon by existing composables | Low | Full smoke-test of all three prerendered routes + tenant form in staging |
| Nitro output format change breaks Cloudflare Pages deployment | Very low | Verify Cloudflare Pages build settings; compare `dist/` structure before/after |
| Cookie serialization fix changes client-side cookie format mid-session | Low | Test OAuth flow end-to-end in staging before promoting to production |
