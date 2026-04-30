# Upgrade Nuxt from 4.3.1 to 4.4.4

## Context
mctl-web runs Nuxt 4.3.1 in SSR+prerender mode. Two minor releases (v4.4.x) have shipped since, accumulating 40+ bug fixes and six performance improvements including Nitro import caching, Vite/Webpack manifest handling, and TypeScript resolution caching. Cookie serialization fixes and hydration error handling improvements are particularly relevant to the tenant onboarding flow which relies on server-set cookies and a multi-step registration form.

## User stories
- AS a site visitor I WANT the landing page to hydrate without errors SO THAT interactive elements (forms, nav) work immediately on load.
- AS a platform engineer I WANT the Nuxt build to complete faster SO THAT CI turnaround time is reduced.
- AS a platform engineer I WANT the framework to be current SO THAT future minor/major upgrades are incremental rather than large jumps.

## Acceptance criteria (EARS)
- WHEN `nuxt build` is run after the upgrade THE SYSTEM SHALL complete without errors or deprecation warnings introduced by the version change.
- WHEN a user visits `/` or `/docs` or `/privacy` THE SYSTEM SHALL serve correctly prerendered HTML with no hydration mismatch errors in the browser console.
- WHEN the tenant onboarding form submits and a server-side cookie is set THE SYSTEM SHALL correctly serialize and transmit the cookie per the RFC (cookie serialization fix in v4.4.x).
- IF any peer-dependency version conflict is detected by `npm install` THEN the upgrade SHALL NOT be merged until conflicts are resolved.
- WHILE the service is running in production THE SYSTEM SHALL maintain the existing prerender targets (`/`, `/privacy`, `/docs`).

## Out of scope
- Upgrading Vue 3, vue-router, vee-validate, yup, or vueuse as part of this proposal (separate concerns).
- Changing the Nuxt configuration beyond what is required to run on v4.4.4.
- Migrating from SSR+prerender to a different rendering mode.
