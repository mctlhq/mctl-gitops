# Requirements — nuxt-444-formdata-fix

## Context

mctl-web runs Nuxt 4.3.1. The `/api/submit` Cloudflare Worker endpoint receives
FormData payloads to provision new tenants: it triggers a Backstage workflow,
sends a Telegram notification, and dispatches a Resend welcome email. Nuxt 4.3.x
contains a bug in the `useFetch` deduplication mechanism where FormData body
hashing is broken; on retry the request key is not matched correctly, which can
silently produce duplicate provisioning calls or drop the request entirely.
Nuxt 4.4.4 (released 2026-04-29) is a patch release that fixes FormData body
hashing in deduplication and adds manifest fetch retry logic for more reliable
hydration of prerendered pages.

## User stories

- AS A new user I WANT to submit the sign-up form SO THAT a tenant is
  provisioned exactly once and I receive a welcome email confirming the
  outcome.
- AS A platform operator I WANT FormData deduplication to work correctly in
  `useFetch` SO THAT no duplicate provisioning requests are sent to the
  Backstage API and no phantom tenants are created.
- AS A site visitor I WANT prerendered pages to hydrate reliably on slow or
  intermittent connections SO THAT I do not see flash-of-unhydrated-content
  or broken page state.

## Acceptance criteria (EARS notation)

- WHEN the mctl-web build is produced the package.json SHALL declare
  `nuxt` at version `4.4.4` and `npm ci` SHALL resolve without conflict.
- WHEN a user submits the tenant sign-up form exactly once THE SYSTEM SHALL
  deliver exactly one provisioning request to the Backstage `/api/submit`
  endpoint, one Telegram notification, and one Resend email.
- WHEN `useFetch` retries a FormData request THE SYSTEM SHALL compute the
  same deduplication key as the original request and SHALL NOT issue a
  second in-flight request to `/api/submit`.
- WHEN the Nuxt manifest fetch fails on first attempt during page hydration
  THE SYSTEM SHALL retry the manifest fetch automatically before falling
  back to a full reload.
- WHEN the CI pipeline runs against the `nuxt-444-formdata-fix` branch THE
  SYSTEM SHALL complete `nuxt build` and all unit and end-to-end tests
  without errors.
- IF the upgrade introduces a regression in any existing route (`/`,
  `/docs`, `/privacy`) THEN the CI gate SHALL fail and the release SHALL
  NOT be merged.

## Out of scope

- Upgrading any dependency other than `nuxt` (Vue, vee-validate, yup, etc.).
- Changes to the Cloudflare Worker source code or wrangler configuration.
- Changes to the Backstage API integration logic.
- Adding new pages or features to mctl-web.
