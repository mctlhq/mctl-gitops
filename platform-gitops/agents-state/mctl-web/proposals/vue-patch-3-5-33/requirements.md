# Upgrade Vue to 3.5.33

## Context

Production runs Vue 3.5.30, released in February 2025. The current version is Vue 3.5.33 (released 22 April 2026). It is a patch release within the v3.5.x branch with no declared breaking changes. Vue patch versions typically contain regression fixes, typing improvements, and minor performance fixes.

Updating to 3.5.33 is mandatory dependency hygiene and is recommended before the larger Nuxt/vue-router update so as to isolate potential sources of issues.

## User stories

- AS a developer I WANT Vue to be on the latest patch version SO THAT known bugs and regressions are fixed without any API changes.
- AS a platform operator I WANT dependencies to be kept current within minor/patch bounds SO THAT security fixes in patch releases are not missed.

## Acceptance criteria (EARS)

- WHEN `nuxt build` runs after the update THE SYSTEM SHALL complete without errors.
- WHEN the application is loaded in a browser THE SYSTEM SHALL produce no Vue-related console errors or hydration warnings.
- WHILE Vue 3.5.33 is active THE SYSTEM SHALL maintain all existing functionality of pages `/`, `/docs`, `/privacy` and the tenant form.
- IF Vue 3.5.34 or later is released THE SYSTEM SHALL be updated in the next daily cycle as part of regular dependency maintenance.

## Out of scope

- Using new Vue 3.5.x APIs introduced between .30 and .33.
- Component architecture changes.
- Updating vueuse/core or vue-router (separate tasks).
