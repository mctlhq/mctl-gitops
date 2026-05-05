# Design: vueuse-nuxt-autoimports

## Current state
@vueuse/core is listed as a direct dependency (`"@vueuse/core": "14.2.1"` per
`context/architecture.md`). In the current setup, every composable must be explicitly
imported in `.vue` files:
```js
import { useStorage, useMediaQuery } from '@vueuse/core'
```
Nuxt 4 auto-imports its own composables (`useFetch`, `useRoute`, `useRuntimeConfig`, etc.)
from the `#imports` virtual module, but third-party composables — including vueuse — require
explicit imports unless a module or `imports` configuration is added to `nuxt.config.ts`.

Starting in @vueuse/core 14.3.0, the package ships a dedicated Nuxt module entry point
(`@vueuse/nuxt`) that registers all vueuse composables with Nuxt's auto-import resolver.
This is a separate capability from the raw `@vueuse/core` export; it must be explicitly
activated in `nuxt.config.ts`.

## Proposed solution
**Add `@vueuse/nuxt` to the `modules` array in `nuxt.config.ts` after @vueuse/core is
upgraded to ≥ 14.3.0.**

### Change to `nuxt.config.ts`
```ts
export default defineNuxtConfig({
  modules: [
    '@vueuse/nuxt',   // ← add this line
  ],
  // ... rest of config unchanged
})
```

`@vueuse/nuxt` is included in the `@vueuse/core` package starting from 14.3.0; no separate
npm install is required (it is a sub-entry-point, not a separate package).

### Effect
After this change:
- All vueuse composables are available in any `.vue` file without import statements.
- Nuxt generates type declarations for them in `.nuxt/imports.d.ts`, providing full IDE
  completion and TypeScript narrowing.
- SSG prerender (`nuxt build` with prerender targets `/`, `/privacy`, `/docs`) is
  unaffected — auto-imports are resolved at build time, not runtime.

### Existing explicit imports
Files that already contain `import { useX } from '@vueuse/core'` will continue to work
(explicit imports take precedence over auto-imports and are not broken by enabling the
module). Cleanup of redundant imports can be done incrementally via IDE refactoring.

## Alternatives

**A. Manually configure `imports.dirs` in nuxt.config.ts**
Nuxt allows adding arbitrary import directories. One could point to the `@vueuse/core`
dist folder. This is fragile across vueuse versions and does not benefit from the officially
maintained Nuxt module. Rejected.

**B. Use `unplugin-auto-import` directly**
The `unplugin-auto-import` Vite plugin can register vueuse composables for auto-import
at the Vite layer. This works but duplicates functionality now natively available via
`@vueuse/nuxt` and adds a third-party devDependency. Rejected in favour of the official
Nuxt module.

**C. Keep explicit imports everywhere**
Explicit imports are unambiguous and zero-risk. However, Nuxt 4's design philosophy is
auto-imports for first-class composables, and @vueuse is effectively a first-class community
dependency given its use in mctl-web. Consistency with the Nuxt 4 style reduces onboarding
friction. Rejected as the status-quo option.

## Platform impact
- **Migrations:** Single line addition to `nuxt.config.ts`. Depends on `vueuse-upgrade-14-3`
  being merged first (or both landing in the same PR).
- **Backward compatibility:** Fully additive. No existing imports break. SSG prerender output
  is identical.
- **Resource impact:** Auto-imports are resolved at build time by Nuxt; the compiled output
  is equivalent to explicit imports. Bundle size is unchanged. No CPU/memory impact at runtime
  on the cluster. No risk for the `labs` tenant.
- **Risks:** Very low. The only risk is a build-time error if the `@vueuse/nuxt` entry point
  is not available in the installed version — mitigated by gating this proposal on the
  `vueuse-upgrade-14-3` proposal.
- **Rollback:** Remove `'@vueuse/nuxt'` from the `modules` array in `nuxt.config.ts` and
  redeploy. No data migrations required.
