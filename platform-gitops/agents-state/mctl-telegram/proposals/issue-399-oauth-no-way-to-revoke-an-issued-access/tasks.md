# Tasks: issue-399-oauth-no-way-to-revoke-an-issued-access

- [ ] 1. Add `handleRevoke` to `internal/oauth/server.go` implementing RFC 7009: parse
      form (400 `invalid_request` on parse failure or missing `token`/`client_id`), look
      up the refresh token via `s.store.LookupRefreshToken`, and respond `200` empty body
      for not-found or client-mismatch, `500` `server_error` for genuine store errors, and
      `200` empty body after a successful `s.store.RevokeRefreshTokenFamily(ctx,
      rt.FamilyID, "explicit_revoke")` call (`500` `server_error` if that call itself
      errors). Read `token_type_hint` but do not require or branch on it. — DoD: handler
      compiles, matches the response-shape rules in design.md exactly (no case returns a
      non-200 for "unknown"/"wrong client"), and reuses `writeTokenError` for all error
      paths so the JSON error shape matches `/oauth/token`.
- [ ] 2. Register the route: `mux.Post("/oauth/revoke", s.handleRevoke)` in
      `Server.Register` (`internal/oauth/server.go:720-742`) (depends on 1) — DoD: route
      appears in the same block as the other `/oauth/*` registrations, in a position that
      keeps related endpoints grouped (next to `/oauth/token`).
- [ ] 3. Add `"revocation_endpoint": s.cfg.Issuer + "/oauth/revoke"` (and, optionally,
      `"revocation_endpoint_auth_methods_supported": []string{"none"}`) to the metadata
      map in `handleAuthorizationServerMetadata` (`internal/oauth/server.go:753-777`)
      (depends on 1, so the advertised endpoint actually exists by the time this ships) —
      DoD: `GET /.well-known/oauth-authorization-server` response includes
      `revocation_endpoint` alongside the existing three endpoint fields.
- [ ] 4. Update `SECURITY.md`: extend the "Refresh tokens" bullet list (lines ~69-77)
      with a line noting `POST /oauth/revoke` (RFC 7009) is now the reachable revocation
      path for the family-revoke mechanism already described there; add an explicit
      statement (new bullet under "Telegram-native OAuth" or its own short subsection)
      that access tokens are not individually revocable within their TTL, that the only
      full invalidation path is rotating `OAUTH_JWT_SIGNING_KEY` (which affects all
      users), and that the accepted mitigation is keeping `OAUTH_ACCESS_TOKEN_TTL` short
      (referencing `#398`'s 24h ceiling) — DoD: the readiness criterion "decision on
      access tokens is recorded in SECURITY.md, including explicit non-revocation within
      TTL" is satisfied by a reviewer reading the file, no code changes required for this
      task.
- [ ] 5. (Optional, do only if trivial) Add a one-line mention of `/oauth/revoke` to any
      developer-facing OAuth flow docs outside `SECURITY.md` if one exists describing the
      full endpoint list (check for a docs page under `internal/web/` or similar before
      doing this; skip if none exists — do not create new docs infrastructure for this).
      — DoD: either updated consistently with `SECURITY.md`, or explicitly skipped
      because no such doc exists.

## Tests

All new tests belong in `internal/oauth/server_test.go` (or a new
`internal/oauth/revoke_test.go` if the existing file's helpers are more easily reused from
a separate file — follow whichever `refresh_test.go` already does, since revoke is a
sibling of refresh) and `internal/db/refresh_tokens_test.go` style store-level coverage
where relevant.

- [ ] T1. Revoke a live refresh token: `POST /oauth/revoke` with a valid `token` +
      matching `client_id` for a token saved via `Store.SaveRefreshToken` returns `200`
      with an empty body, and a subsequent `grant_type=refresh_token` call with the same
      token at `/oauth/token` returns `invalid_grant` (token no longer usable).
- [ ] T2. Revoke also kills siblings in the family: save two tokens sharing a
      `FamilyID` (simulating a rotated lineage, e.g. via `RotateRefreshToken` or two
      `SaveRefreshToken` calls with the same `FamilyID`), revoke one, assert
      `LookupRefreshToken` on the other now reports `Revoked() == true`.
- [ ] T3. Repeat revoke (idempotency): revoke the same token twice; both calls return
      `200`.
- [ ] T4. Unknown token: `POST /oauth/revoke` with a `token` value that matches nothing
      returns `200` with an empty body (not `400`, not `404`).
- [ ] T5. Wrong `client_id`: revoke a token that belongs to `client_id=A` while passing
      `client_id=B` in the request; assert `200` is returned but the token is still live
      afterward (`LookupRefreshToken` shows `Revoked() == false`) — this is the "chief
      security property" test per the issue's readiness criteria and design.md's listed
      risk.
- [ ] T6. Malformed request: missing `token` param -> `400` `invalid_request`; missing
      `client_id` param -> `400` `invalid_request`; unparseable form body (e.g. bad
      Content-Type or a body that fails `ParseForm`) -> `400` `invalid_request`.
- [ ] T7. Metadata includes the new field:
      `GET /.well-known/oauth-authorization-server` response JSON has
      `revocation_endpoint == "<issuer>/oauth/revoke"`.
- [ ] T8. Store-level: `Store.RevokeRefreshTokenFamily(ctx, familyID, "explicit_revoke")`
      sets `revoked_reason = "explicit_revoke"` on the affected row(s) and leaves
      unrelated families untouched (extends the existing pattern already exercised
      indirectly in `internal/db/store_test.go:563`; add a direct, dedicated test in
      `internal/db/refresh_tokens_test.go` alongside `TestRefreshToken_RevokeFamily` if
      that test doesn't already cover the `explicit_revoke` reason string explicitly).

## Rollback

- The change is additive (new route, new handler, new metadata field, docs update) with
  no schema migration and no change to existing endpoints' behavior or response shapes.
  Rollback is a plain revert of the commit/PR — redeploy the previous image tag via
  `mctl_rollback_service` (or the team's standard rollback path). No data cleanup is
  needed: any `revoked_reason = 'explicit_revoke'` rows written before rollback remain
  valid, harmless history (the column already tolerated a free-text reason and other code
  paths only ever check `revoked_at IS NULL` / `IS NOT NULL`, never the specific reason
  string, so old rows don't confuse a rolled-back binary).
- If `/oauth/revoke` needs to be pulled without a full redeploy, it can also be disabled
  at the ingress/routing layer, but a redeploy to the prior tag is the standard and
  preferred path per this repo's existing rollback tooling.
