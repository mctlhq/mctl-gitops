# Vue 3.5.34 Patch Upgrade

## Context
mctl-web is currently pinned to Vue 3.5.30 (see `context/architecture.md`). Vue 3.5.34 was released on 2026-05-06 and is the latest stable patch. It delivers six targeted bug fixes across compiler-sfc, reactivity, runtime-core, and suspense, with the most notable being DOM leak prevention. Running four patch versions behind in a Nuxt SSG app means the DOM leak can surface during client-side hydration of the prerendered routes (`/`, `/docs`, `/privacy`), potentially degrading long-session browser tab performance.

An existing proposal (`vue-patch-3-5-33`) targeted 3.5.33. That proposal has been superseded by 3.5.34; the current proposal targets the latest release directly, making 3.5.33 an intermediate step that can be skipped.

## User stories
- AS a frontend developer I WANT Vue core to be updated to 3.5.34 SO THAT known DOM leak regressions and reactivity bugs do not affect end users of mctl.ai.
- AS a platform engineer I WANT the dependency update to be verified in CI SO THAT no runtime regressions are introduced into the prerendered landing, docs, or privacy pages.
- AS a user browsing mctl.ai SO THAT long-session tab memory usage remains stable and the DOM leak fix is applied.

## Acceptance criteria (EARS)
- WHEN a developer runs `npm install` inside the `app/` directory THE SYSTEM SHALL resolve `vue` to version 3.5.34 or higher within the 3.5.x range.
- WHEN the Nuxt build (`nuxt build`) completes THE SYSTEM SHALL produce a `dist/` artefact with no new TypeScript or build errors compared to the 3.5.30 baseline.
- WHEN any prerendered route (`/`, `/docs`, `/privacy`) is loaded in a browser THE SYSTEM SHALL hydrate without console errors related to Vue reactivity, suspense, or DOM management.
- WHILE the CI pipeline runs the build THE SYSTEM SHALL pass all existing lint and type-check steps without modification.
- IF a Vue patch release newer than 3.5.34 is available at the time of implementation THEN the implementer SHALL update to that latest patch instead.

## Out of scope
- Upgrading Vue to a minor or major version (e.g., 3.6.x or 4.x).
- Changing vue-router, vee-validate, or @vueuse/core versions in the same PR.
- Adding new Vue composables or features introduced in 3.5.31–3.5.34.
- Any changes to the Cloudflare Worker (`cloudflare-worker/`).
