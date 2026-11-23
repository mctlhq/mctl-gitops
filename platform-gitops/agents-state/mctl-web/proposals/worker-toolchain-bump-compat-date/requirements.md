# Bump wrangler/workerd toolchain and review the Worker compatibility_date

## Context
workers-sdk (`@cloudflare/workers-auth@0.18.2`, `workers-utils` 0.54.0) and workerd v1.20261113.1 were released on 13 Nov, and the default compatibility date moved to 2026-11-13. No advisories were found for wrangler or workerd in the inbox search. The Worker handles OAuth, the Backstage token, and Telegram and Resend secrets, so keeping tooling current is cheap hygiene. This is lower priority than the Nuxt items.

## Items to verify
- V1. The inbox saw no wrangler-specific tag; confirm the actual latest `wrangler` version on npm/GitHub releases before pinning.
- V2. Current wrangler version and current `compatibility_date` in `wrangler.toml` (not read in this run).
- V3. The "no advisories" finding is from a search, not an audit; re-check official advisories.
- V4. Nuxt baseline discrepancy (4.3.1 vs 4.6.2) is not relevant to this proposal but is flagged for consistency.

## User stories
- AS a maintainer I WANT a pinned, current Worker toolchain SO THAT deploys are reproducible and supported.
- AS an owner I WANT the compat-date change tested against OAuth, submit and contact flows SO THAT runtime behaviour changes do not break users.

## Acceptance criteria (EARS)
- WHEN the toolchain is updated THE SYSTEM SHALL pin the verified wrangler version exactly in `package.json`/lockfile.
- WHEN the compat-date candidate is evaluated THE SYSTEM SHALL run it in staging through the GitHub OAuth login/callback, `/api/submit` and `/api/contact` flows before production.
- IF any flow regresses under the new date THEN THE SYSTEM SHALL keep the existing `compatibility_date` and record the reason.
- WHILE the autogated MemoryCache (Rust) is behind an autogate THE SYSTEM SHALL NOT enable it.
- WHEN the deploy runs THE SYSTEM SHALL keep existing routes (`mctl.ai/api/*`, redirects for `mctl.me`, `mctl.ru`) and rate limits unchanged.
- WHEN secrets are handled during testing THE SYSTEM SHALL use staging secrets and not log secret values.

## Out of scope
- Nuxt upgrade and path tests (separate proposals).
- Changing Worker business logic or secrets.
- Adopting new workerd features (URLPattern, util.diff, mock.property).
- Tenant `labs`.
