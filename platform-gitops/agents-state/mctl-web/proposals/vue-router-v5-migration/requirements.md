# Plan Migration from vue-router 4.6.4 to vue-router v5

## Context
mctl-web currently uses vue-router 4.6.4, two major versions behind the latest stable release (v5.0.6, March 2026). vue-router v5 integrates `unplugin-vue-router` into core, providing first-class typed routes out of the box — a developer-experience improvement relevant to the TypeScript-based Nuxt 4 stack. mctl-web does not currently use `unplugin-vue-router`, placing it in the "non-breaking migration" category per the vue-router v5 release notes. Planning the migration now avoids a forced, time-pressured upgrade once v4.x reaches end-of-support.

## User stories
- AS a platform engineer I WANT to understand the exact migration steps for vue-router v5 SO THAT the upgrade can be planned and executed without regression.
- AS a developer I WANT typed route names and params in the Nuxt project SO THAT route mismatches are caught at compile time rather than runtime.
- AS a platform engineer I WANT the framework dependency tree to remain on supported major versions SO THAT security patches and bug fixes are available.

## Acceptance criteria (EARS)
- WHEN the migration is executed THE SYSTEM SHALL pass `nuxt build` without errors on vue-router v5.
- WHEN a user navigates between `/`, `/docs`, and `/privacy` THE SYSTEM SHALL render the correct page with no router warnings in the console.
- WHEN a developer references a route by name in a component THE SYSTEM SHALL provide TypeScript type-checking for route names and params (typed routes via unplugin-vue-router integration).
- IF Nuxt 4.x does not yet officially support vue-router v5 THEN the migration SHALL be deferred until Nuxt compatibility is confirmed and documented in a follow-up ADR.
- WHILE the migration is in progress THE SYSTEM SHALL maintain all existing prerender targets (`/`, `/docs`, `/privacy`) and the Cloudflare Worker routes (`/api/*`).

## Out of scope
- Introducing new routes or changing the routing structure.
- Migrating to a different router library.
- Changes to the Cloudflare Worker routing (handled separately by Worker config).
