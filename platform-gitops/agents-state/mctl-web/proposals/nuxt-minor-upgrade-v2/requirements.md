# Nuxt Minor Upgrade: 4.3.1 to 4.4.3

## Context
mctl-web currently runs Nuxt 4.3.1 as its core SSG framework (see `context/architecture.md`). Nuxt 4.4.3 was released on 2026-04-29, representing two minor versions of advancement. Minor releases in the Nuxt 4.x line typically include bug fixes, performance improvements, and compatibility refinements for the Vue 3.5.x patch series. The service uses Nuxt in SSG mode with SSR enabled for prerendering `/`, `/privacy`, and `/docs`.

Nuxt is the most foundational dependency of mctl-web's frontend build. Staying two minor versions behind creates compounding upgrade risk: each skipped minor may introduce internal API changes that make future upgrades harder. Additionally, Vue 3.5.30 → 3.5.34 patch fixes are pulled in naturally as a transitive dependency of this upgrade, consolidating two dependency bumps into one.

## User stories
- AS a developer I WANT Nuxt upgraded to 4.4.3 SO THAT I benefit from upstream bug fixes and avoid accumulating upgrade debt against the core framework.
- AS a developer I WANT Vue 3.5.x patch fixes included in the same upgrade SO THAT I do not need a separate PR for Vue core.
- AS a platform engineer I WANT the upgrade validated in CI before merging SO THAT regressions in prerendering or build output are caught before reaching production.

## Acceptance criteria (EARS)
- WHEN `nuxt build` is executed after the upgrade THE SYSTEM SHALL complete without errors and produce a `dist/` directory containing prerendered output for `/`, `/docs`, and `/privacy`.
- WHEN `nuxt build` is executed after the upgrade THE SYSTEM SHALL resolve nuxt at version 4.4.3 (confirmed via `nuxt --version` or lockfile inspection).
- WHEN the upgraded application is deployed to a preview environment THE SYSTEM SHALL serve all three prerendered routes with HTTP 200 and correct HTML content.
- IF any Nuxt 4.4.x release note documents a breaking change for SSG or prerendering THE SYSTEM SHALL have a documented mitigation applied before the upgrade is merged.
- WHILE the application is running after upgrade THE SYSTEM SHALL maintain existing vee-validate and yup form behavior on the tenant request form without regression.

## Out of scope
- Upgrading Nuxt to 4.5.x or beyond.
- Upgrading Vue Router (tracked separately as `vue-router-v5-migration`).
- Upgrading vee-validate, yup, or @vueuse/core independently — minor updates to those packages may be bundled if they are required for compatibility but are not the primary objective.
- Changes to the Cloudflare Worker or `wrangler.toml`.
- Any changes to the server-side API routes or Worker endpoints.
