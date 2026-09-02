# Revocable worker tokens: jti, denylist, and an admin revoke operation

## Context

`POST /api/mcp/worker-token` (`internal/workertoken/tokenhandler.go`) mints a full MCP
credential — verified by the same `selectProvider` provider mounted at `/mcp`
(`internal/workertoken/tokenhandler.go:108-125`) — for headless workers and Local Bridge
daemons. Once minted, nothing in the codebase can invalidate a single token before its TTL
expires (30 days default, 90 days max). `internal/auth/localjwt.Verify` checks signature,
issuer, and expiry only; there is no `jti`, no denylist, no lookup of any kind
(`internal/auth/localjwt/issuer.go:113-145`). The two levers that look like they should stop
a token do not: flipping `telegram_accounts.mode` to hosted only gates `/bridge`
(`internal/bridge.NewBridgeHandler`) and, for an account migrated from hosted, actually keeps
the token working through the server's own hosted dispatch; and `set_telegram_access` /
`GetAccessTier` (`internal/db/store.go:320`) is consulted only at token *issuance*
(`internal/oauth/server.go:698,1097`) and by the agent-send gate
(`cmd/server/agentsendgate.go:73`), never on the `/mcp` request path for an already-issued
JWT. The only working containment lever today is rotating `OAUTH_JWT_SIGNING_KEY`, which
invalidates every token of every user, not just the compromised one.

This matters because a worker token is a full send-capable credential (purpose
`local-bridge` carries `telegram:messages:send` and `telegram:messages:pin`) whose normal
resting place is a plaintext file on a user's machine (`bridge_token.json`, mode `0600` — a
POSIX permission NTFS ignores on Windows). A leaked token is valid and unstoppable for up to
90 days (or effectively longer once renewal, `internal/workertoken/renewhandler.go`, is
taken into account up to the 1-year `maxRenewalChain`) with no operator response between
"do nothing" and "rotate the signing key for everyone."

## User stories

- AS an operator I WANT to revoke a single worker token by its `jti` SO THAT I can contain a
  suspected leak without invalidating every other user's credential.
- AS an operator who does not have the leaked token in hand I WANT to revoke every worker
  token minted for a given Telegram id SO THAT I can respond even when I only know which
  account is affected, not which specific token leaked.
- AS an operator reading an old audit line I WANT the `jti` logged at mint and renewal time
  SO THAT I can revoke a token identified only through the audit trail.
- AS the operator of a normal interactive session I WANT my requests to take no extra
  database round trip SO THAT revocation support for worker tokens does not add latency to
  the common case.
- AS an operator I WANT a revoked token to stay revoked across renewal SO THAT the worker
  cannot simply call `/api/mcp/worker-token/renew` to launder a revoked credential into a
  fresh one.

## Acceptance criteria (EARS)

- WHEN `POST /api/mcp/worker-token` mints a token THE SYSTEM SHALL embed a unique `jti`
  claim in it, for both the read-only and `local-bridge` purposes.
- WHEN `POST /api/mcp/worker-token/renew` renews a token THE SYSTEM SHALL carry forward the
  presented token's `jti` unchanged into the renewed token, so a token and all of its
  renewals share one identifier.
- WHEN a request presents a Bearer JWT that carries a `jti` claim THE SYSTEM SHALL check that
  `jti` (and the token's Telegram id) against a revocation store before treating the
  request as authenticated.
- IF a token's `jti` is denylisted, OR the token's Telegram id carries a blanket revocation
  issued at or after the token's `orig_iat` (falling back to `iat` for pre-`jti` tokens),
  THEN THE SYSTEM SHALL reject the request the same way it rejects an invalid signature
  (401, no distinguishing detail beyond what other verification failures already return).
- WHEN a request presents a Bearer JWT with no `jti` claim (an interactive user session)
  THE SYSTEM SHALL NOT perform any denylist lookup for that request.
- WHEN an admin with the `admin:users` scope revokes a token by `jti` THE SYSTEM SHALL
  record that `jti` as revoked such that any future or already-cached-stale verification of
  a token carrying it fails within the cache's refresh interval.
- WHEN an admin with the `admin:users` scope revokes all worker tokens for a Telegram id
  THE SYSTEM SHALL record a blanket revocation for that id such that any worker token for
  that id — including ones whose `jti` the operator never learned — is rejected at `/mcp`
  and at `/api/bridge/token`, without requiring the operator to enumerate individual `jti`s.
- WHEN a worker token is minted or renewed THE SYSTEM SHALL log its `jti` alongside the
  existing mint/renew log line (`internal/workertoken/tokenhandler.go:219`,
  `internal/workertoken/renewhandler.go:209`).
- WHILE a token is revoked THE SYSTEM SHALL reject an `/api/mcp/worker-token/renew` request
  presenting that token, because the auth middleware in front of the renew handler already
  denies it before the handler runs.
- IF the revocation table cannot be reached during a `jti`-bearing token's verification THEN
  THE SYSTEM SHALL fail closed (reject the request) rather than silently skip the check,
  consistent with the codebase's existing "no panics, wrap and return" error posture.

## Out of scope

- Wiring up `bridge_token_hash`. The issue explicitly calls this out as not the fix: it
  would cover only the one-hour bridge JWT, which the daemon re-mints from the still-valid
  long-lived MCP JWT every hour, so revoking it stops nothing. This proposal neither wires it
  up nor removes the column.
- Revoking interactive user OAuth sessions/refresh tokens. `oauth_refresh_tokens` already has
  its own `revoked_at`/`revoked_reason` revocation mechanism (`internal/db/store.go`); this
  proposal only extends coverage to the workertoken-minted JWT class, which had none.
- Changing `defaultWorkerTokenTTL`/`maxWorkerTokenTTL` (30/90 days). The issue's "interim
  mitigation, no code" (mint at 30 days rather than 90) is an operator practice, not a code
  change, and is not part of this proposal.
- A UI for revocation. The admin surface is an MCP tool (matching `set_telegram_access`,
  `revoke_telegram_session`), not a web dashboard.
- Un-revoking a token. Revocation in this proposal is one-directional; if a blanket
  revocation was a mistake, the operator mints a fresh token for the account.

## Open questions

- The issue says "revoking every worker token for a user is the more likely operator
  intent... the one that works when the operator does not have the token in hand." Since no
  registry of issued `jti`s exists, a by-Telegram-id revoke cannot enumerate specific tokens
  to denylist. Resolution used in this design: a blanket per-Telegram-id revocation record
  with a timestamp, checked against the token's `orig_iat`/`iat` at verification time — this
  covers every worker token for that id issued up to the moment of revocation, known `jti` or
  not, without needing a token registry. Proceeding on this interpretation.
- The issue does not specify whether the admin revoke operation should be an MCP tool or an
  HTTP endpoint. Resolution: an MCP tool (`revoke_worker_token`), matching the existing
  `set_telegram_access` / `revoke_telegram_session` pattern in `internal/mcp/tools.go`, is
  the interpretation used here, since every other `admin:users`-gated write in this codebase
  is an MCP tool rather than a bare HTTP route.
- The issue does not say whether revoking should also affect a token's already-issued
  1-hour bridge JWT (minted via `/api/bridge/token`) if one was derived from the worker
  token before revocation. Resolution: out of scope for this proposal — the bridge JWT is
  short-lived (1 hour) and expires on its own; only the `/api/mcp/worker-token` and
  `/api/bridge/token` mint paths (which both run under `provider`, the same
  `localjwt.Provider` gaining the denylist check) are required to reject a revoked worker
  token going forward.
- No specific cache refresh interval is mandated by the issue. Resolution: default to a
  short in-process TTL cache (see design.md) in the 5-15 second range, documented as
  configurable, trading a small worst-case revocation-propagation delay for avoiding a
  per-request DB round trip.
