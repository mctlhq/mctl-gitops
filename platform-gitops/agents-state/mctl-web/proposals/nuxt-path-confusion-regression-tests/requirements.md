# CI smoke tests for path normalization and routing exposure

## Context
This month's Nuxt advisories share a theme: path confusion (`//`, `%2F`, `/%2e/`) bypassing checks keyed to a literal path (CVE-2026-128077, CVE-2026-128071, CVE-2026-119200). These IDs and descriptions come from one source (OpenCVE) and are UNVERIFIED; confirm against official Nuxt GitHub advisories before citing. The site is mostly prerendered and has no `admin.vue`, so exposure is probably low, but a cheap post-build test guards against regressions, including in the Cloudflare Worker routes `mctl.ai/api/*` and their rate limits.

## Items to verify
- V1. CVE details (above) against official advisories.
- V2. Nuxt baseline version (4.3.1 in architecture.md vs 4.6.2 in current-version.md) from `package.json`/lockfile; test expectations depend on whether the upgrade proposal has landed.
- V3. Whether `deploy.yml` has a suitable pre-deploy stage and how to serve the build locally in CI.

## User stories
- AS a maintainer I WANT automated path-variant checks SO THAT routing/normalization regressions are caught before deploy.
- AS a security reviewer I WANT proof that Worker rate limits apply to encoded variants SO THAT they cannot be bypassed.

## Acceptance criteria (EARS)
- WHEN `deploy.yml` runs after build and before deploy THE SYSTEM SHALL execute the path-variant smoke tests against the built site and the Worker (local/staging).
- WHEN a request uses `//`, `%2F`, `/%2e/` or trailing-slash variants of `/`, `/docs`, `/privacy` THE SYSTEM SHALL return the same content as the canonical path, a redirect to it, or a 404, and never a different page or an error with internals.
- WHEN requests use encoded or double-slash variants of `/api/*` THE SYSTEM SHALL route them identically to the canonical path and apply the same rate limits (5/5min `/submit`, 3/5min `/contact`, 10/min `/github/login`).
- WHEN a production error response is produced THE SYSTEM SHALL NOT contain stack traces or internal details.
- IF any variant yields unexpected content or leaks details THEN THE SYSTEM SHALL fail the workflow and block deploy.
- WHILE tests run THE SYSTEM SHALL NOT send real Telegram, Resend or Backstage calls.

## Out of scope
- The Nuxt upgrade itself (see nuxt-4-6-4-security-upgrade).
- Changing Worker routing or rate-limit logic; only observing it.
- Load or fuzz testing.
- Tenant `labs`.
