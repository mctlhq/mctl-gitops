# Tasks: vueuse-nuxt-autoimports

- [ ] 1. Confirm `vueuse-upgrade-14-3` has been merged (pre-condition) — DoD: `@vueuse/core`
  in `package.json` is ≥ 14.3.0; `npm ls @vueuse/core` confirms the installed version.

- [ ] 2. Add `'@vueuse/nuxt'` to the `modules` array in `nuxt.config.ts` (depends on 1) —
  DoD: `nuxt.config.ts` contains `modules: ['@vueuse/nuxt']` (or appended to an existing
  modules array); file committed with no other changes.

- [ ] 3. Run `nuxt build` and verify auto-import declarations (depends on 2) — DoD: build
  completes without TypeScript errors; `.nuxt/imports.d.ts` contains entries for vueuse
  composables (e.g. `useStorage`, `useDark`).

- [ ] 4. Verify SSG prerender output is unchanged (depends on 3) — DoD: `nuxt generate`
  produces HTML for `/`, `/privacy`, and `/docs`; a byte-level diff against the pre-change
  baseline shows no meaningful content changes (timestamps and build hashes may differ).

- [ ] 5. Update IDE / editor setup notes if applicable (depends on 3) — DoD: if the project
  has an `.editorconfig`, `tsconfig.json`, or developer guide referencing vueuse imports,
  note that explicit `@vueuse/core` imports are now optional; committed alongside step 2.

- [ ] 6. Open PR and pass CI (depends on 4, 5) — DoD: GitHub Actions build step (which
  includes `nuxt build`) exits 0; PR description notes the dependency on `vueuse-upgrade-14-3`
  and includes a screenshot or log excerpt showing vueuse entries in `.nuxt/imports.d.ts`.

## Tests
- [ ] T1. Auto-import smoke test: add a temporary `const isDark = useDark()` line in a page
  component without an import statement; confirm `nuxt build` succeeds and TypeScript does
  not report an "unknown identifier" error; revert the temporary line before merging.
- [ ] T2. SSG regression: run `nuxt generate` and confirm the three prerendered pages
  (`/`, `/privacy`, `/docs`) produce valid HTML with no missing content (spot-check
  `<title>`, `<meta>`, and the first visible heading).
- [ ] T3. Existing explicit imports unchanged: confirm that any `.vue` file already
  containing `import { useX } from '@vueuse/core'` still compiles cleanly (no duplicate
  symbol errors or import conflicts).

## Rollback
1. Remove `'@vueuse/nuxt'` from the `modules` array in `nuxt.config.ts`.
2. Run `nuxt build` locally to confirm the build still succeeds (explicit imports in
   existing files remain valid).
3. Trigger `deploy.yml` on the reverted commit to redeploy; no infrastructure changes are
   required.
