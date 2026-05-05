# Enable VueUse Nuxt Auto-Import Composables

## Context
@vueuse/core 14.3.0 (released May 1, 2026) ships dedicated Nuxt composable variants that
register with Nuxt's auto-import system. This means composables such as `useStorage`,
`useLocalStorage`, `useDark`, `useMediaQuery`, and `useWindowSize` can be used directly in
Nuxt pages and components without explicit `import { useX } from '@vueuse/core'` statements,
consistent with how Nuxt 4 already auto-imports its own composables.

mctl-web currently uses @vueuse/core 14.2.1 (pinned). Upgrading to 14.3.0 (covered by the
separate `vueuse-upgrade-14-3` proposal) unlocks this integration, but a configuration step
in `nuxt.config.ts` is required to activate it. This proposal covers that configuration work,
which is distinct from the version bump and provides a measurable DX improvement for all
future page component development.

## User stories
- AS a frontend developer I WANT vueuse composables to be available without imports
  SO THAT I can write new page components more quickly and consistently with Nuxt conventions.
- AS a code reviewer I WANT a uniform import style across all page components
  SO THAT I spend less time on style comments in PRs.

## Acceptance criteria (EARS)
- WHEN @vueuse/core ≥ 14.3.0 is installed and the Nuxt VueUse module is configured,
  THE SYSTEM SHALL resolve vueuse composables (e.g. `useStorage`) without explicit import
  statements in any `.vue` file under `app/`.
- WHEN `nuxt build` is run, THE SYSTEM SHALL produce no TypeScript errors related to
  unresolved vueuse composable names.
- WHEN the Nuxt dev server starts, THE SYSTEM SHALL surface vueuse composables in the
  auto-import declarations file (`.nuxt/imports.d.ts`) so editors provide type completion.
- IF the @vueuse/core version is below 14.3.0, THEN THE SYSTEM SHALL not attempt to enable
  the auto-import integration (it is gated on the version upgrade).
- WHILE SSG prerender runs for `/`, `/privacy`, and `/docs`, THE SYSTEM SHALL produce
  identical HTML output to the pre-change baseline (no regression in rendered content).

## Out of scope
- Upgrading @vueuse/core to 14.3.0 (covered by `vueuse-upgrade-14-3`).
- Removing existing explicit veeuse imports from files that already have them (can be done
  incrementally; not a hard requirement for this proposal).
- Adding new vueuse composables to existing components (this proposal only enables the integration).
