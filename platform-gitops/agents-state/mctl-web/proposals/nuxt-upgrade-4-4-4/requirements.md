# Nuxt Upgrade to v4.4.4

## Context
mctl-web currently runs Nuxt 4.3.1 in production. Nuxt v4.4.4 was released on 2026-04-29 (a clean re-publish of v4.4.3, which was affected by a release-script issue). The release train from 4.3.1 to 4.4.4 delivers meaningful improvements: Vue Router v5 support (introduced in v4.4.2), TypeScript path-resolution caching, parallel module loading, Nitro import optimizations, and up to 28x faster dev-server route changes. Several bug fixes also land across cookie serialization, async data handling, hook cleanup, and error handling.

An older proposal `nuxt-upgrade-4-4-2` targeted an intermediate version; this proposal supersedes it with the correct final target of v4.4.4. Staying on 4.3.1 means missing compounding performance gains in both development and production builds, as well as accumulated bug fixes that affect reliability of the tenant registration flow.

## User stories
- AS a developer I WANT the dev server to reflect route changes up to 28x faster SO THAT I spend less time waiting and more time building features.
- AS a developer I WANT TypeScript path resolution to be cached SO THAT IDE responsiveness and incremental build times improve.
- AS a site visitor I WANT the mctl-web pages to load with a smaller JavaScript bundle SO THAT the site is faster on low-bandwidth connections.
- AS an operator I WANT the tenant registration form to handle cookies and async data reliably SO THAT users do not encounter silent failures during onboarding.
- AS a developer I WANT the project to track the current stable Nuxt release SO THAT security patches and ecosystem compatibility are maintained.

## Acceptance criteria (EARS)

- WHEN the production build completes THEN THE SYSTEM SHALL use Nuxt 4.4.4 as reported by `nuxt --version`.
- WHEN `nuxt build` runs in CI THEN THE SYSTEM SHALL complete without TypeScript errors or build warnings introduced by the upgrade.
- WHEN a developer starts the dev server and edits a route file THEN THE SYSTEM SHALL reflect the change in the browser within the performance bounds expected of v4.4.4 (no regression versus v4.3.1).
- WHEN a user submits the tenant registration form THEN THE SYSTEM SHALL correctly serialize and transmit cookies as per the v4.4.x cookie serialization fix.
- WHEN async data composables (`useAsyncData`, `useFetch`) are used on any page THEN THE SYSTEM SHALL resolve and hydrate data without errors introduced by the upgrade.
- WHILE the site is deployed on Cloudflare Pages THEN THE SYSTEM SHALL serve all prerendered routes (`/`, `/docs`, `/privacy`) with HTTP 200 and correct content.
- IF the upgrade introduces a breaking change in vue-router 4.6.4 compatibility THEN THE SYSTEM SHALL document the required migration step before the change is merged.
- WHEN the Cloudflare Worker endpoints (`/api/*`) are invoked after the upgrade THEN THE SYSTEM SHALL respond correctly and without regression in rate-limit or OAuth behavior.

## Out of scope
- Migration to Vue Router v5 (tracked separately; the nuxt-upgrade-4-4-2 proposal addressed it — that work is not duplicated here unless v4.4.4 forces it).
- Upgrading Vue core beyond 3.5.30, vee-validate, yup, or @vueuse/core as part of this proposal.
- Any changes to the Cloudflare Worker code itself.
- Replacing or removing any existing third-party integrations (GitHub OAuth, Backstage, Telegram, Resend).
- Enabling SSR at runtime (prerender-only mode is preserved).
