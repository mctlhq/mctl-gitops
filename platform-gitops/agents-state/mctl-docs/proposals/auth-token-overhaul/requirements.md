# Authentication Page Rewrite — Token TTL, Persistence, Revocation, and Error Shapes

> version-status: unverified, see commit SHAs 60b8034, 2930d1b, 5b166aa, b4d0c29 (mctl-api 4.18.4 confirmed via mctl-gitops a61f047 2026-05-13)

## Context

Between 2026-05-10 and 2026-05-13 the `mctl-api` repository shipped four
authentication-related changes that together materially alter the security model
that developers and platform operators depend on. Access token lifetime was
extended from 1 hour to 7 days (commit `60b8034`). Refresh tokens were moved
from an in-memory store to a durable Postgres backend, meaning tokens now survive
API pod restarts and recycling (commit `2930d1b`). The `/revoke` OAuth endpoint
was extended to accept a `client_id` parameter per RFC 7009 §2.1, enabling
per-client revocation in multi-client setups (commit `5b166aa`). Finally, the
`invalid_grant` error description was sanitised to always return the generic
string `"invalid or expired token"` rather than raw internal error messages
(commit `b4d0c29`).

The current `docs/security/authentication.md` page reflects the old model on all
four points. A developer reading it today will believe tokens expire after 1 hour,
that restarts invalidate refresh tokens, that `/revoke` takes no `client_id`, and
that `invalid_grant` responses expose internal error text. Every one of those
beliefs is now incorrect. The page must be rewritten to reflect the shipped state.

## User stories

- AS a developer integrating with the mctl-api REST API or MCP server I WANT to
  know the correct access token lifetime (7 days) SO THAT I do not build
  unnecessary re-authentication logic into my client.
- AS a developer building an OAuth client I WANT to know that refresh tokens are
  stored in Postgres and survive server restarts SO THAT I can reason correctly
  about token reliability and avoid defensive reconnect loops.
- AS a platform operator running a multi-client OAuth setup I WANT to know the
  `client_id` parameter on `/revoke` and its RFC 7009 semantics SO THAT I can
  revoke tokens for one client without affecting other clients.
- AS an integrator parsing token-refresh error responses I WANT to know that
  `invalid_grant` always returns the stable message `"invalid or expired token"`
  SO THAT I can write robust error-handling code without fear of leaking internal
  details.
- AS a platform admin reviewing the security posture of the platform I WANT the
  authentication documentation to accurately describe token persistence, lifetime,
  revocation scope, and error shapes SO THAT my security review is based on facts.

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/security/authentication.md` THE SYSTEM SHALL display
  the access token TTL as 7 days, not 1 hour.
- WHEN a reader opens `docs/security/authentication.md` THE SYSTEM SHALL state
  that refresh tokens are persisted in Postgres and survive API server restarts.
- WHEN a reader opens `docs/security/authentication.md` THE SYSTEM SHALL document
  the `/revoke` endpoint with its `token` and `client_id` form parameters and
  explain that `client_id` scopes revocation per RFC 7009 §2.1.
- WHEN a reader opens `docs/security/authentication.md` THE SYSTEM SHALL document
  the `invalid_grant` error shape, showing that `error_description` is always
  `"invalid or expired token"` and never exposes internal server state.
- IF a reader wants to call the `/revoke` endpoint THEN THE SYSTEM SHALL provide
  a curl example showing both the `token` and `client_id` parameters.
- IF a reader wants to understand the token rotation retry grace window THEN THE
  SYSTEM SHALL explain that a legitimately rotated token can be re-presented
  within the grace window without being rejected as already-used.
- WHEN a reader opens `docs/mcp/connecting.md` THE SYSTEM SHALL NOT contain any
  language stating that access tokens expire after 1 hour or prompting the user
  to reconnect hourly.

## Out of scope

- A migration guide for users who built re-authentication logic assuming 1-hour
  TTL — that is a support concern, not a documentation page.
- Video tutorial for the OAuth flow.
- Localisation (English only per platform policy).
- Changes to `docs/api/index.md` beyond what is strictly necessary to remove the
  incorrect 1-hour TTL reference if one is present there.
- Documentation of the internal Postgres schema or refreshstore package internals.
- Documenting the mctl-openclaw credential refresh resilience change (`596ae91`)
  — that is a separate implementation concern; link to authentication.md from
  openclaw.md is sufficient.
