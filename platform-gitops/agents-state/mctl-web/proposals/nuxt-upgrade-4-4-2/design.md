# Design: nuxt-upgrade-4-4-2

## Current state

According to `context/architecture.md` and `context/current-version.md`:
- Nuxt **4.3.1** (SSR=true, prerender `/`, `/privacy`, `/docs`)
- Vue **3.5.30**
- vue-router **4.6.4** (EOL — final release of the v4 branch)
- Three pages: `app/pages/index.vue`, `app/pages/docs/index.vue`, `app/pages/privacy/index.vue`

vue-router v4.x no longer receives updates. Nuxt 4.4.2 ships `unrouting` (routing speed-up up to 28x) and requires vue-router v5, which folds `unplugin-vue-router` into the core.

## Proposed solution

**Staged dependency bump:**

1. Update `nuxt` to `"^4.4.2"` in `package.json`.
2. Drop the explicit `vue-router` from `dependencies`/`devDependencies` — Nuxt 4.4.2 will pull vue-router v5 transitively; alternatively pin `"vue-router": "^5.0.6"`.
3. Inspect vue-router API usage in pages and composables:
   - `useRoute()`, `useRouter()`, `navigateTo()` — compatible with v5 via the Nuxt wrappers.
   - Direct imports from `vue-router` (e.g. `import { RouterLink } from 'vue-router'`) may need to be replaced with Nuxt components (`<NuxtLink>`).
4. Update `nuxt.config.ts` for any deprecated options (verify per the Nuxt 4.4 migration guide).
5. Run `nuxt build` and `nuxt generate` to validate prerendering.

**Optional Nuxt 4.4.2 features:**
- `useAnnouncer()` — improves a11y for SPA navigation.
- Typed layout props — can be enabled gradually.

## Alternatives

1. **Stay on Nuxt 4.3.1 + vue-router 4.6.4** — EOL, no security patches for the router. Dropped: tech debt only grows.
2. **Move directly to Nuxt 5 (if it exists)** — overshooting; Nuxt 4.4.x is actively supported and is the current stable. Dropped: extra risk without benefit.
3. **Use `@vitejs/plugin-vue-router` instead of the built-in** — adds complexity unnecessarily, unplugin-vue-router is already part of Nuxt 4.4. Dropped.

## Platform impact

- **Migration:** changes are limited to `app/` (frontend), the Worker is untouched. Prerender paths do not change.
- **Backward compatibility:** vue-router v5 has breaking changes around direct imports; Nuxt wrappers (`useRoute`, `useRouter`, `NuxtLink`) are backward compatible. Pages need to be checked for direct imports from `vue-router`.
- **Resource impact:** zero for the `labs` and `admins` tenants — this is a static frontend and a Worker, not pod workloads in k8s.
- **Risks and mitigations:** the main risk is a breaking change in the vue-router v5 API. Mitigation: run `nuxt typecheck` + a prerender test in staging. The bundle may change in size slightly due to the new `unrouting` module — this is acceptable.
