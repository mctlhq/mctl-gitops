# Nuxt 4.4.5 Patch Upgrade

## Context
mctl-web runs Nuxt 4.3.1 as its SSG/SSR framework (see `context/architecture.md`). Nuxt 4.4.5 was released on 2026-05-10 and is the current latest stable release. It is more than a minor release ahead of the pinned version and introduces performance improvements to the prerender pipeline: a caching layer for roots and short-circuit evaluation of `isIgnored` relative path lookups. Both optimisations directly reduce build time and server warm-up cost for mctl-web's three prerendered routes (`/`, `/docs`, `/privacy`).

An existing proposal (`nuxt-upgrade-4-4-4`) targeted the previous latest. The current proposal supersedes it with the actual latest release (4.4.5), which also bundles the Vite, Nitro, and server component bug fixes included in 4.4.4.

## User stories
- AS a frontend developer I WANT Nuxt upgraded to 4.4.5 SO THAT SSG prerender builds are faster and bug fixes in Vite/Nitro integration are applied.
- AS a platform engineer I WANT the build pipeline (`deploy.yml`) to pass without modification after the upgrade SO THAT delivery confidence is maintained.
- AS an end user visiting mctl.ai SO THAT the prerendered pages load correctly after the upgrade.

## Acceptance criteria (EARS)
- WHEN a developer runs `npm install` inside the `app/` directory THE SYSTEM SHALL resolve `nuxt` to version 4.4.5 or higher within the 4.x range.
- WHEN `nuxt build` is executed THE SYSTEM SHALL complete without errors and produce a valid `dist/` artefact.
- WHEN the prerendered routes (`/`, `/docs`, `/privacy`) are requested THE SYSTEM SHALL return HTTP 200 with correct HTML content.
- WHILE the CI pipeline runs THE SYSTEM SHALL pass lint, type-check, and build steps without new failures.
- IF Nuxt 4.4.x releases a version higher than 4.4.5 before implementation THE SYSTEM SHALL target that newer version instead.
- WHEN the `nuxt.config.ts` references runtime configuration THE SYSTEM SHALL retain the existing shape without modification (the placeholder `apiSecret` field is out of scope).

## Out of scope
- Upgrading to Nuxt 4.5.x or beyond — that is a separate minor-version decision.
- Changes to the Cloudflare Worker or wrangler configuration.
- Enabling new Nuxt 4.4.x features not already in use (e.g., new prerender hooks).
- Modifying Kubernetes deployment manifests in `mctl-gitops` — the `admins` tenant build is self-contained in `deploy.yml`.
