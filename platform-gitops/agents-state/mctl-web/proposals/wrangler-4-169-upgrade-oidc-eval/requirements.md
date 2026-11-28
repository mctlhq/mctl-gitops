# Bump wrangler/workerd and evaluate OIDC tokens binding

## Context
wrangler 4.169.0 (27 Nov) bumps workerd and adds an oidc_tokens binding for short-lived tokens. The Worker currently holds long-lived secrets (Telegram, GitHub, Backstage, Resend).

## User stories
- AS a platform owner I WANT wrangler current and a documented assessment of reducing long-lived secrets SO THAT the public site stays secure and maintainable.

## Acceptance criteria (EARS)
- WHEN the Worker is built in deploy.yml THE SYSTEM SHALL use wrangler >=4.169.0.
- WHEN the upgrade is deployed THE SYSTEM SHALL keep /api/github/*, /api/submit and /api/contact behaviour and rate limits unchanged.
- WHEN the evaluation completes THE SYSTEM SHALL record whether oidc_tokens can replace BACKSTAGE_LANDING_TOKEN (needs Backstage-side verification).

## Out of scope
- Actually migrating secrets to OIDC.
