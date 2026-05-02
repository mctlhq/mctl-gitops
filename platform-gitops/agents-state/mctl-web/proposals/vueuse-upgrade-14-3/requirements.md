# Upgrade @vueuse/core from 14.2.1 to 14.3.0

## Context
mctl-web depends on `@vueuse/core 14.2.1` (confirmed in `context/architecture.md`) for reactive
composables used throughout the Nuxt 4 frontend. Version 14.3.0 was released on 2026-05-01 and
ships targeted bug fixes in `useWebSocket`, `useWakeLock`, and `useTextareaAutosize`, plus
pointer-event handling improvements for `useLongPress`. Although mctl-web's architecture does not
explicitly document WebSocket or WakeLock usage today, the fixes apply to the shared composable
surface consumed by all pages. Staying current on a minor semver bump (no breaking changes)
prevents accumulation of version debt and keeps the dependency aligned with the Nuxt 4 / Vue 3
ecosystem release cadence.

## User stories
- AS a frontend engineer I WANT @vueuse/core upgraded to 14.3.0 SO THAT the fixed composable
  behaviour (useWebSocket, useWakeLock, useTextareaAutosize) is available without carrying known
  bugs in the shipped bundle.
- AS a developer I WANT the dependency updated while the delta is small SO THAT future upgrades
  within the 14.x line do not require reasoning about skipped bug-fix ranges.
- AS a platform engineer I WANT a clean, up-to-date dependency graph SO THAT security scans do
  not flag easily-avoidable stale minor releases.

## Acceptance criteria (EARS)
- WHEN `npm install` is run after the version bump THE SYSTEM SHALL resolve `@vueuse/core` to
  exactly `14.3.0` (or the newest 14.3.x patch if one is available at install time).
- WHEN `nuxt build` completes with @vueuse/core 14.3.0 THE SYSTEM SHALL produce a build with no
  new warnings or errors compared to 14.2.1.
- WHILE the Nuxt dev server is running under 14.3.0 THE SYSTEM SHALL serve all existing pages
  (`/`, `/docs`, `/privacy`, and the tenant onboarding form) without console errors attributable
  to @vueuse/core.
- IF a composable from @vueuse/core is imported and used in a Vue SFC THE SYSTEM SHALL continue
  to behave as specified in the 14.x API contract — no regressions in form interactions or
  navigation composables.
- WHEN the upgrade is committed THE SYSTEM SHALL include a matching update to `package-lock.json`
  in the same changeset.

## Out of scope
- Upgrading @vueuse/core beyond the 14.3.x line (tracked as a future inbox item).
- Changes to Cloudflare Worker code, wrangler configuration, or Kubernetes manifests.
- Replacing any composable with a custom implementation.
- Upgrading Nuxt, Vue, vue-router, or sass as part of this change (separate proposals exist).
