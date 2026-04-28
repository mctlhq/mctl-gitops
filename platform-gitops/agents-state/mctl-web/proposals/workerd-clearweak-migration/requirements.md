# Workerd ClearWeak API Migration

## Context
workerd v1.20260426.1, released 2026-04-26, deprecates the ClearWeak V8 API in favour of an updated replacement. workerd is the runtime engine that powers Cloudflare Workers; mctl-web's Cloudflare Worker (in `cloudflare-worker/`) runs on this runtime and handles all `/api/*` traffic, including GitHub OAuth flows (`/api/github/login`, `/api/github/callback`), tenant provisioning (`/api/submit`), and contact submissions (`/api/contact`).

If the Worker's own code or any of its npm dependencies invoke the deprecated ClearWeak path, Cloudflare will first surface runtime warnings and eventually remove the API in a future workerd release. At removal, the Worker will fail at startup or at the point of the deprecated call, taking down all `/api/*` routes. Migrating now—while the old API is still functional—avoids a forced, time-pressured migration during a future outage. The Worker runs under the `admins` tenant; no `labs` resources are affected.

## User stories
- AS a platform engineer I WANT the Cloudflare Worker to use no deprecated ClearWeak API calls SO THAT it continues to function correctly after Cloudflare removes the deprecated path in a future workerd release.
- AS an on-call engineer I WANT `/api/*` endpoints to remain stable across workerd runtime upgrades SO THAT OAuth, tenant provisioning, and contact flows are not interrupted by runtime deprecation removals.
- AS a developer I WANT a documented audit of `cloudflare-worker/` and its npm dependencies for ClearWeak usage SO THAT I understand the scope of the change and can verify completeness.

## Acceptance criteria (EARS)
- WHEN the Worker is deployed to Cloudflare Pages THE SYSTEM SHALL not emit any ClearWeak deprecation warnings in the workerd runtime log.
- WHEN `wrangler dev` is run locally against `cloudflare-worker/` THE SYSTEM SHALL not emit ClearWeak-related deprecation warnings in the development server output.
- WHILE the Worker is handling requests on `/api/*` THE SYSTEM SHALL not invoke any V8 ClearWeak API path, whether directly or through a transitive npm dependency.
- IF a new npm dependency is added to `cloudflare-worker/package.json` THEN THE SYSTEM SHALL verify (via the audit process defined in this proposal) that the dependency does not reintroduce ClearWeak usage.
- WHEN `wrangler tail` is observed against the production Worker after the migration THEN THE SYSTEM SHALL show zero ClearWeak deprecation entries in the log stream.

## Out of scope
- Changes to the Nuxt frontend build or its SCSS stylesheets.
- Upgrading wrangler — covered by `wrangler-full-upgrade`.
- Changes to the GitHub OAuth App configuration, Backstage API integration, or Telegram/Resend secrets.
- Modifications to Kubernetes manifests for `admins` or `labs` tenants.
- Any workerd API other than the ClearWeak deprecation addressed in v1.20260426.1.
