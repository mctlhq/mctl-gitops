# Design: vue-router-v5-migration-v3

## Current state
As documented in `context/architecture.md`, mctl-web uses vue-router 4.6.4 alongside Nuxt 4.3.1 and Vue 3.5.30. The service has three pages managed by Nuxt's file-based routing: `app/pages/index.vue`, `app/pages/docs/index.vue`, and `app/pages/privacy/index.vue`. Navigation between these pages uses Nuxt's `<NuxtLink>` component (which wraps `<RouterLink>`) and programmatic navigation via `useRouter()` where applicable. The Worker's routing (`/api/*`) is handled entirely by the Cloudflare Worker runtime, independent of vue-router.

## Proposed solution
The migration proceeds in two phases to reduce risk:

**Phase 1 — Compatibility validation (no code changes to ship).**
Before touching `package.json`, audit all usages of vue-router APIs in the codebase: `useRouter`, `useRoute`, `<RouterLink>`, `<NuxtLink>`, `router.push`, `router.replace`, `onBeforeRouteLeave`, etc. Cross-reference each API against the vue-router v5 changelog and migration guide to confirm it is either unchanged or has a documented upgrade path. Document findings in the PR description.

**Phase 2 — Version bump and fix-up.**
Update `vue-router` in `package.json` to `5.0.6`, regenerate the lockfile, and resolve any TypeScript or runtime errors surfaced by the change. Because Nuxt 4.x ships its own vue-router integration, confirm that Nuxt 4.4.x (targeted by `nuxt-minor-upgrade-v2`) is compatible with vue-router 5.x. If Nuxt pins or re-exports vue-router internally, the Nuxt upgrade may already bring in a compatible version — in that case this proposal's changes may be a no-op at the `package.json` level, and the value is in the explicit confirmation and documentation.

The rationale for this approach:
- The upstream claim of "no breaking changes from v4" lowers risk but does not eliminate it; the audit step provides evidence.
- A phased approach keeps the diff reviewable and makes regression bisection straightforward.
- This proposal is explicitly ordered after `nuxt-minor-upgrade-v2` to avoid conflating the Nuxt upgrade and router upgrade in the same commit.

## Alternatives

**Option A — Upgrade vue-router as part of the Nuxt upgrade PR.**
Conflates two distinct changes. If a regression occurs, it is harder to determine whether Nuxt or vue-router caused it. Rejected in favor of a separate PR with explicit ordering.

**Option B — Stay on vue-router 4.6.4 indefinitely.**
vue-router 4.x will eventually enter maintenance-only mode as v5 matures. The DX benefit of typed file-based routing is meaningful for a Nuxt SSG project. Remaining on v4 incurs upgrade debt. Rejected.

**Option C — Adopt typed file-based routing as part of this migration.**
This would involve enabling `experimental.typedPages` or equivalent Nuxt config and updating all route references to use generated typed route names. This is a larger scope change that should be its own proposal after the basic v5 compatibility is confirmed. Rejected for this proposal; left as a follow-up.

## Platform impact
- **Migrations:** No database or infrastructure migrations. Changes are limited to `package.json`, `package-lock.json`, and any source files requiring API compatibility fixes.
- **Backward compatibility:** The upgrade targets the same Nuxt 4.4.x environment targeted by `nuxt-minor-upgrade-v2`. If Nuxt 4.4.x internally bundles vue-router 5.x, the effective change is zero. If it does not, the upgrade must be validated against Nuxt's `useRouter` and `useRoute` composables which proxy the vue-router instance.
- **Resource impact:** No runtime memory or CPU impact on the Kubernetes cluster — mctl-web's frontend is served statically via Cloudflare Pages. The `labs` tenant is unaffected.
- **Risks and mitigations:** The primary risk is a Nuxt 4.4.x incompatibility with vue-router 5.x that is not surfaced until build or runtime. Mitigation: run the full build and deploy to a Cloudflare Pages preview before merging. Secondary risk: programmatic `router.push` calls in the OAuth flow behave differently under v5. Mitigation: test the GitHub OAuth login and redirect flow end-to-end in the preview environment.
