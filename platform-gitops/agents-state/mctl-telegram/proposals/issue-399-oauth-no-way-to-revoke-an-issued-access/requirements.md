# OAuth: add POST /oauth/revoke (RFC 7009) and record the access-token revocation decision

## Context

`mctl-telegram` runs its own OAuth 2.1 authorization server (`internal/oauth/server.go`,
`AUTH_MODE=local-jwt`). Refresh tokens are already handled properly: opaque, stored only
as a SHA-256 hash (`internal/db/refresh_tokens.go`), rotated on every use, with reuse
detection that revokes the whole token family (`Store.RevokeRefreshTokenFamily`,
`internal/db/refresh_tokens.go:220`, called internally from `handleTokenRefresh` at
`internal/oauth/server.go:1617` and `:1708`). But that revocation path is never exposed to
callers: there is no `POST /oauth/revoke` endpoint, no `revocation_endpoint` in
`/.well-known/oauth-authorization-server` (`internal/oauth/server.go:753`), and access
tokens (`internal/auth/localjwt/issuer.go` `Verify()`) are validated purely from the JWT
itself (signature, issuer, `exp`) with no denylist or storage lookup of any kind.

The result, confirmed in the issue: the only way to kill one leaked token today is to
rotate `OAUTH_JWT_SIGNING_KEY`, which invalidates every access token for every user. That
is what happened on 2026-08-16 after a token with `admin:users` scope leaked into logs and
on-disk MCP client configs — a single-token leak turned into an all-users outage. This
proposal closes the cheap, high-value half of the gap (refresh-token revocation, RFC 7009)
and forces an explicit, documented decision on the harder half (access-token revocation)
instead of leaving it as an unexamined gap.

## User stories

- AS an operator who discovers a leaked OAuth token I WANT to revoke just that token's
  refresh-token family SO THAT I can cut off future access without rotating the signing
  key and logging out every other user.
- AS an MCP client (Claude, ChatGPT, or any RFC 7009-aware client) I WANT the
  authorization server to advertise a `revocation_endpoint` SO THAT I can revoke tokens
  I no longer need (e.g. on user-initiated "disconnect") through a standard mechanism.
- AS a security reviewer I WANT the access-token revocation trade-off written down in
  `SECURITY.md` SO THAT "access tokens are not individually revocable within their TTL"
  is a stated, reviewed decision rather than an accidental gap discovered during an
  incident.

## Acceptance criteria (EARS)

- WHEN a client sends `POST /oauth/revoke` with a `token` parameter that matches a live
  refresh token THE SYSTEM SHALL revoke that token's entire family via
  `Store.RevokeRefreshTokenFamily` (reason `"explicit_revoke"`) and respond `200 OK` with
  an empty body, per RFC 7009 SS2.2.
- WHEN a client sends `POST /oauth/revoke` with a `token` value that does not match any
  known refresh token THE SYSTEM SHALL respond `200 OK` (RFC 7009 SS2.2: unknown tokens are
  not an error) without revoking anything.
- IF the `POST /oauth/revoke` request is malformed (unparseable body, missing `token`,
  missing `client_id`) THEN THE SYSTEM SHALL respond `400` with an
  `invalid_request`/`error_description` body in the same shape `writeTokenError` already
  produces for `/oauth/token`.
- IF the presented token's stored `client_id` does not match the `client_id` supplied in
  the revoke request THEN THE SYSTEM SHALL NOT revoke the token and SHALL still respond
  `200 OK` (RFC 7009 SS2.1: the endpoint must not leak whether the token exists to a party
  that cannot prove it is the token's owner; the response is indistinguishable from the
  "unknown token" case so the caller cannot use this endpoint to probe other clients'
  tokens).
- WHEN `POST /oauth/revoke` successfully revokes a token family THE SYSTEM SHALL make the
  presented refresh token, and every other still-active token in the same family,
  rejected by a subsequent `grant_type=refresh_token` call at `/oauth/token`.
- WHEN `POST /oauth/revoke` is called a second time with the same already-revoked token
  THE SYSTEM SHALL respond `200 OK` (idempotent; RFC 7009 does not distinguish
  "already revoked" from "never existed").
- WHEN a client fetches `/.well-known/oauth-authorization-server` THE SYSTEM SHALL include
  `revocation_endpoint` (`{issuer}/oauth/revoke`) alongside the existing
  `authorization_endpoint`, `token_endpoint`, and `registration_endpoint` fields.
- WHILE an access token (JWT) is unexpired THE SYSTEM SHALL continue to accept it at
  `/mcp` even after its associated refresh token has been revoked via `/oauth/revoke` —
  this proposal does not add access-token revocation; see the decision recorded below and
  in `SECURITY.md`.
- WHERE the `SECURITY.md` "Refresh tokens" section documents the OAuth token model THE
  SYSTEM's documentation SHALL additionally state, explicitly, that access tokens are
  bearer-valid for their full TTL and are not individually revocable, and SHALL name the
  short TTL (`OAUTH_ACCESS_TOKEN_TTL`, and the `#398` 24h ceiling) as the mitigation for
  that gap.

## Out of scope

- Access-token denylist-by-`jti` (option 1 in the issue). The issue itself frames this as
  a decision to record, not a requirement to build; this proposal records the decision
  (short-TTL bearer tokens, no per-token revocation) rather than implementing a denylist.
  Revisit if `#398`'s TTL ceiling turns out insufficient in practice.
- `POST /oauth/revoke` support for revoking by presenting an *access* token as the
  `token` parameter with a hint that it is an access token
  (`token_type_hint=access_token`). Only refresh tokens are revocable in this proposal;
  an access-token hint is accepted per RFC 7009 SS2.1 ("the authorization server MAY ignore
  this parameter") but treated as opaque input to the same refresh-token lookup, so it
  correctly falls into the "unknown token, 200 OK, no-op" branch.
- A user-facing "revoke my sessions" UI. This proposal only adds the protocol-level
  endpoint; any dashboard/UI work is separate.
- Rate limiting specific to `/oauth/revoke` beyond whatever ingress-level or per-identity
  limiting already applies to public OAuth endpoints (`SECURITY.md` "Rate limiting"
  section) — `/oauth/revoke` is unauthenticated like `/oauth/token`, so it inherits the
  same anonymous-endpoint treatment; no new limiter is introduced here.
- Changing `OAUTH_ACCESS_TOKEN_TTL` defaults or the `#398` 24h ceiling — tracked separately.

## Open questions

- RFC 7009 SS2.1 says the revocation endpoint SHOULD support both `client_secret_basic`
  and allow public clients to authenticate "if possible." This deployment's clients use
  `token_endpoint_auth_methods_supported: ["none"]` (`internal/oauth/server.go:762`) — no
  client secret exists to check. Interpretation used here: `/oauth/revoke` requires
  `client_id` (matched against the stored token's `client_id`, mirroring the existing
  `handleTokenRefresh` `client_id` check at `internal/oauth/server.go:1630`) but no
  secret, consistent with how `/oauth/token` already treats these clients as public.
- Whether unknown/mismatched-client revoke attempts should be logged (without leaking
  token material) for abuse monitoring. Recommended yes, at `slog.Info` with a hashed
  token prefix only, no plaintext — left as an implementation detail for tasks.md rather
  than a hard requirement, since the issue does not ask for it.
- Whether to also revoke by `token_type_hint=refresh_token` explicitly vs. the current
  "we only understand refresh tokens" approach. Resolved as: `token_type_hint` is read but
  not required, and any hint value still routes through the refresh-token lookup (see Out
  of scope) — simplest RFC-compliant behavior given only one token type is revocable.
