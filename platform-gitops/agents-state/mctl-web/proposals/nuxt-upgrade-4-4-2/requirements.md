# Upgrade Nuxt to 4.4.2 and migrate to vue-router v5

## Context

The current stack uses Nuxt 4.3.1 + vue-router 4.6.4. Nuxt 4.4.2 was released on 12 March 2026 and requires vue-router v5; the vue-router v4.x branch is declared EOL (v4.6.4 is the final release). Deferring the migration accumulates technical debt: security patches and new features in Nuxt 4.4+ will ship only against vue-router v5.

For mctl-web with three pages (`/`, `/docs`, `/privacy`), the volume of routing-config changes required is minimal. The migration also delivers up to 28x faster routing (via `unrouting`), typed layout props, and the new `useAnnouncer` composable for a11y.

## User stories

- AS a developer I WANT to run Nuxt 4.4.2 with vue-router v5 SO THAT the project stays on supported dependency branches and receives future security patches.
- AS a developer I WANT typed layout props and fast routing SO THAT the DX improves and routing bugs are caught at compile time.
- AS a platform operator I WANT critical dependencies (router) to be on a maintained major version SO THAT EOL components do not block future upgrades.

## Acceptance criteria (EARS)

- WHEN the build runs with Nuxt 4.4.2 THE SYSTEM SHALL compile successfully without errors or deprecation warnings related to vue-router v4.
- WHEN a user navigates to `/`, `/docs`, or `/privacy` THE SYSTEM SHALL render the correct page without hydration errors.
- WHEN the prerender step executes THE SYSTEM SHALL generate static HTML for all three prerendered routes (`/`, `/privacy`, `/docs`).
- WHILE vue-router v5 is active THE SYSTEM SHALL preserve all existing route definitions and redirect behaviour of the Cloudflare Worker.
- IF a composable or component uses a vue-router v4-only API THE SYSTEM SHALL be updated to the v5 equivalent before merging.
- WHEN `nuxt build` finishes THE SYSTEM SHALL produce a bundle with no vue-router v4 packages in the dependency graph.

## Out of scope

- Adding new pages or routes.
- Replacing vee-validate or yup (forbidden by ADR 0001 without a specific bug/perf justification).
- Changes to the Cloudflare Worker (`cloudflare-worker/`) — it does not import vue-router.
- Updating @vueuse/core or sass (already on current versions).
