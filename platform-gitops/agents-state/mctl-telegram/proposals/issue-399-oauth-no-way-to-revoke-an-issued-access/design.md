# Design: issue-399-oauth-no-way-to-revoke-an-issued-access

## Current state

`mctl-telegram` is its own OAuth 2.1 authorization server (`internal/oauth/server.go`,
package `oauth`, type `Server`). Routes are registered in `Server.Register`
(`internal/oauth/server.go:720-742`) against a small `Router` interface
(`Get`/`Post`) so handlers can be unit-tested without chi. Currently registered:
`/.well-known/oauth-authorization-server` (GET), `/oauth/authorize` (GET),
`/oauth/telegram/callback` (GET), `/oauth/token` (POST), `/oauth/register` (POST), the
`enable_access` sub-flow (POST x3), and `/oauth/demo/login` (POST). There is no
`/oauth/revoke`.

Metadata is a static `map[string]any` built in `handleAuthorizationServerMetadata`
(`internal/oauth/server.go:753-777`) listing `authorization_endpoint`, `token_endpoint`,
`registration_endpoint`, but no `revocation_endpoint` — RFC 8414 permits the omission,
which is exactly why RFC 7009-aware clients never discover the capability even once it
exists server-side.

Refresh tokens are opaque 256-bit random strings (`randomToken(32)`,
`internal/oauth/server.go:1748` area), stored only as a SHA-256 hash
(`hashRefreshToken`, `internal/db/refresh_tokens.go:64`) in `oauth_refresh_tokens`, keyed
by `family_id` (rotation lineage) and `client_id`. The store already exposes exactly the
primitive this issue needs:

- `Store.LookupRefreshToken(ctx, plaintext) (*RefreshToken, error)` —
  `internal/db/refresh_tokens.go:109`, returns `db.ErrRefreshTokenNotFound` for anything
  that doesn't match.
- `Store.RevokeRefreshTokenFamily(ctx, familyID, reason) (int64, error)` —
  `internal/db/refresh_tokens.go:220`, sets `revoked_at`/`revoked_reason` on every
  still-active row in the family. Currently called only from inside
  `handleTokenRefresh`'s reuse-detection branches (`internal/oauth/server.go:1617`,
  `:1708`) with reason `"reuse_detected"`. The `RevokedReason` doc comment
  (`internal/db/refresh_tokens.go:34-38`) already anticipates a third reason,
  `"explicit_revoke"`, and `internal/db/store_test.go:563` already exercises
  `RevokeRefreshTokenFamily(ctx, "fam4", "explicit_revoke")` from a different test's setup
  code — the reason string is not new, just not yet reachable from an HTTP handler.

Access tokens are self-contained HS256 JWTs (`internal/auth/localjwt`). `Issuer.Mint`
(`issuer.go:66`) signs `Claims{iss, sub, tg_id, tg_username, groups, scopes, iat, exp,
aud}` — no `jti`. `Verify` (`issuer.go:105`) checks only signature, `iss`, and `exp`; it
takes no store and does not consult the database. `Provider.Authenticate`
(`issuer.go:205`) calls `Verify` then resolves the user row — it never looks up token
state. This is the asymmetry the issue describes: refresh-token infrastructure is
first-class, access-token revocation infrastructure does not exist.

`writeTokenError`/`writeTokenJSON` (`internal/oauth/server.go:1763-1786`) are the existing
response helpers for `/oauth/token`; `handleTokenRefresh` (`internal/oauth/server.go:1575`)
is the closest existing handler in shape: parses form values, looks up a refresh token by
plaintext, checks `client_id` match, branches on revoked/expired state.

`SECURITY.md` has a "Refresh tokens" subsection (lines 69-77) describing rotation, reuse
detection, and TTL, but says nothing about revocation reachability or about access-token
revocability at all.

## Proposed solution

1. **`POST /oauth/revoke` handler** (RFC 7009), added to `internal/oauth/server.go` next
   to `handleToken`/`handleTokenRefresh`, registered in `Server.Register`:
   ```go
   mux.Post("/oauth/revoke", s.handleRevoke)
   ```
   Behavior, mirroring `handleTokenRefresh`'s existing structure so reviewers see one
   consistent pattern for "parse form, look up refresh token, check client_id, act":
   - `r.ParseForm()`; on error, `writeTokenError(w, "invalid_request", "could not parse
     form", http.StatusBadRequest)`.
   - Require `token` (RFC 7009 SS2.1 required param) and `client_id` (this deployment's
     public-client convention, same as `handleTokenRefresh`); missing either ->
     `invalid_request`, 400. `token_type_hint` is read but not required or validated —
     any value routes through the same refresh-token lookup, per RFC 7009 SS2.1 ("the
     authorization server MAY ignore this parameter").
   - `rt, err := s.store.LookupRefreshToken(ctx, token)`.
     - `errors.Is(err, db.ErrRefreshTokenNotFound)` -> `200 OK`, empty body. Unknown
       token is success per RFC 7009 SS2.2.
     - other error -> `writeTokenError(..., "server_error", ..., 500)` — a lookup failure
       must not silently report success, or an operator revoking a real leaked token
       could believe it worked when the DB call actually failed.
     - found but `rt.ClientID != clientID` -> `200 OK`, empty body, no revocation. Same
       response as "unknown" so this endpoint cannot be used to fingerprint another
       client's tokens (RFC 7009 SS2.1).
     - found and client matches (regardless of `rt.Revoked()` — revoking an
       already-revoked family is a no-op inside `RevokeRefreshTokenFamily`, which only
       touches rows `WHERE revoked_at IS NULL`) -> `s.store.RevokeRefreshTokenFamily(ctx,
       rt.FamilyID, "explicit_revoke")`. On store error, 500
       (`server_error`) — same "must not falsely claim success" reasoning as lookup.
       On success, `200 OK`, empty body.
   - Response body is empty on success per RFC 7009 SS2.2 ("response with HTTP status
     code 200 ... body empty"); error responses reuse `writeTokenError`'s
     `{error, error_description}` JSON shape for consistency with `/oauth/token`, since
     RFC 7009 SS2.2.1 defines the same `invalid_request`/`unsupported_token_type`/
     `unauthorized_client` vocabulary as RFC 6749 SS5.2.

2. **Advertise `revocation_endpoint`** in `handleAuthorizationServerMetadata`
   (`internal/oauth/server.go:753-777`): add
   `"revocation_endpoint": s.cfg.Issuer + "/oauth/revoke"` next to the other three
   endpoint fields, and (optionally, harmless either way)
   `"revocation_endpoint_auth_methods_supported": []string{"none"}` mirroring the
   existing `token_endpoint_auth_methods_supported` field so RFC 7009-aware clients that
   check the auth-methods array before calling don't skip it.

3. **No change to access-token verification.** `localjwt.Verify` and
   `Provider.Authenticate` are untouched — this is the deliberate, documented half of the
   decision (see Platform impact / SECURITY.md below), not an oversight.

4. **`SECURITY.md` "Refresh tokens" section update**: add a bullet stating revocation is
   now reachable (`POST /oauth/revoke`, RFC 7009, revokes the presented token's whole
   family) and a new bullet or short subsection under "Telegram-native OAuth" stating,
   explicitly: access tokens are bearer-valid JWTs with no per-token revocation
   mechanism; the only way to invalidate an issued-but-unexpired access token early is
   rotating `OAUTH_JWT_SIGNING_KEY` (which invalidates every user's tokens); the accepted
   mitigation is keeping `OAUTH_ACCESS_TOKEN_TTL` short (the `#398` 24h ceiling, current
   production practice trending toward 1h per the issue). This directly satisfies the
   issue's readiness criterion "decision recorded in SECURITY.md ... including explicit
   'not revoked within TTL' if that path is chosen."

## Alternatives

- **Add `jti` + access-token denylist now, not just refresh-token revocation.** Rejected
  for this proposal: it requires a schema change (new table or column, e.g.
  `oauth_revoked_jtis`), a new claim (`jti` in `localjwt.Claims`, threading a random ID
  through `Mint`), and — critically — a DB round-trip added to `Verify`/`Authenticate`
  on the hot path of every single `/mcp` request, for every user, to protect against a
  problem that short TTLs (`#398`) already substantially mitigate. The issue itself
  frames this as an open decision, not a requirement ("Второй вариант вполне может
  оказаться правильным"). Building it speculatively without a proven need (e.g. TTL
  ceiling shipping and still being insufficient) would add a permanent latency/complexity
  cost to every authenticated request. Revisit as a follow-up if #398's TTL reduction
  proves insufficient.
- **Revoke by access-token JTI lookup at `/oauth/revoke` too (accept `token_type_hint=
  access_token` and actually act on it).** Rejected because it presupposes the denylist
  alternative above; without a `jti` claim or denylist table there is nothing to revoke.
  Deferred together with the denylist decision.
- **Make `/oauth/revoke` require the same client validation as `/oauth/authorize`
  (`validateClient`, checking `redirect_uri` too).** Rejected: RFC 7009's client-matching
  requirement is just "the client that owns the token," which for this deployment's
  public clients means `client_id` equality against the stored `RefreshToken.ClientID` —
  the same check `handleTokenRefresh` already applies. Requiring `redirect_uri` as well
  adds a parameter RFC 7009 does not define and that legitimate revoke callers (e.g. a
  client's own "log out" button, which does not have a `redirect_uri` at hand outside the
  authorize flow) would have no reason to send.
- **Silent success without a distinct "wrong client" branch (fold it into the DB lookup
  query itself, i.e. `WHERE token_hash = $1 AND client_id = $2`).** Considered and
  functionally equivalent to the two-branch version described above, since both produce
  the same "200, no-op" outward behavior — noted here because it is a valid
  implementation simplification: a single query
  `SELECT ... FROM oauth_refresh_tokens WHERE token_hash = $1` still needs to run to
  distinguish "genuinely unknown" for lookup-error handling from "known, wrong owner," but
  the client match can be done in Go on the already-fetched row (as described in Proposed
  solution) rather than a second query. Either is acceptable; tasks.md follows the
  single-lookup-then-Go-compare version since `LookupRefreshToken` already exists and
  needs no new query.

## Platform impact

- **Migrations:** none. `oauth_refresh_tokens.revoked_reason` is already a free-text
  column (`internal/db/refresh_tokens.go` schema usage); `"explicit_revoke"` is an
  additional value in an already-unconstrained field, not a new column.
- **Backward compatibility:** additive only. New route, new metadata field. Existing
  clients that don't know about `revocation_endpoint` are unaffected. No change to
  `/oauth/token` or `/mcp` request/response shapes.
- **Resource impact:** negligible. `/oauth/revoke` is a single indexed lookup
  (`token_hash` is already the primary lookup index used by `LookupRefreshToken`) plus, on
  the revoke path only, the same `UPDATE ... WHERE family_id = $1` already used by reuse
  detection. No new background jobs, no new hot-path cost on `/mcp` (access-token
  verification is untouched).
- **Risks + mitigations:**
  - *Risk:* a broken client-match check could let one OAuth client revoke another
    client's refresh tokens (cross-client DoS). *Mitigation:* explicit `client_id`
    equality check before calling `RevokeRefreshTokenFamily`, covered by a dedicated
    "wrong client_id" test (tasks.md T-wrong-client).
  - *Risk:* returning `200` on a lookup or revoke *error* (not just "not found") would
    create the exact false-positive the issue's readiness criteria calls out ("ложный 200
    на неудавшийся отзыв опаснее ошибки"). *Mitigation:* only "not found" and
    "wrong client" map to `200`; genuine store errors map to `500`, distinguished via
    `errors.Is(err, db.ErrRefreshTokenNotFound)` exactly as `handleTokenRefresh` already
    does at `internal/oauth/server.go:1583-1590`.
  - *Risk:* operators or reviewers reading only the issue's "denylist by jti" option
    might expect access tokens to become revocable too, and be surprised when a revoked
    session's still-unexpired access token keeps working. *Mitigation:* the SECURITY.md
    update states this explicitly and the requirements.md acceptance criteria include it
    as a WHILE-clause invariant, not a silent omission.
  - *Risk:* `/oauth/revoke` is unauthenticated (like `/oauth/token` and `/oauth/register`)
    so it is reachable by anyone who has captured a refresh token plaintext — but anyone
    who has captured a refresh token plaintext already has full account access via
    `/oauth/token`, so exposing a revoke path adds no new capability to an attacker who
    already holds the secret; it only adds a capability for the legitimate holder/operator
    to shut that access off, which is the entire point of the feature.
