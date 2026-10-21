# Account deletion revokes the user's OAuth refresh-token families

## Context

`Store.HardDeleteAccount` (`internal/db/store.go:958`) is the single delete path behind
the `delete_telegram_account` MCP tool (`internal/mcp/tools.go:889`) and
`DELETE /api/account` (`internal/web/account.go:126,130`). In one transaction it deletes
the `telegram_accounts` rows, purges agent data and notification/consent state, and clears
identity fields on `users`. The `users` row survives, so the
`oauth_refresh_tokens.user_id REFERENCES users(id) ON DELETE CASCADE` cascade
(`internal/db/db.go` schema) never fires, and nothing in the delete path revokes refresh
tokens. Every OAuth client already connected (ChatGPT, Claude, an agent platform) can
therefore keep rotating its refresh token for up to `OAUTH_REFRESH_TOKEN_TTL` (default 30
days, not overridden in the deployed `labs/mctl-telegram` values). With that token it can
call tools that need no Telegram session, and it gets message access back without new
consent if the user reconnects Telegram.

This proposal makes account deletion revoke every refresh-token family of the user in the
same transaction as the delete, with `revoked_reason = 'account_deleted'`. A failed
revocation fails the whole delete. `privacy.html` and `SECURITY.md` will describe
disconnect and delete accurately: disconnect ends the Telegram session and keeps the OAuth
grant, while removing the connector or deleting the account revokes the client.

## User stories

- AS a user who deletes my account I WANT every connected OAuth client cut off SO THAT no client can act for me after deletion or quietly get access back when I reconnect.
- AS a user I WANT the privacy page to say exactly what disconnect and delete each do SO THAT I can choose the right one.
- AS an operator I WANT revocations from account deletion to carry their own reason SO THAT I can tell them apart from rotation, reuse detection and explicit revocation in the database.

## Acceptance criteria (EARS)

- WHEN `Store.HardDeleteAccount(ctx, userID)` runs THE SYSTEM SHALL, in the same database transaction as the `telegram_accounts` delete, set `revoked_at = now` and `revoked_reason = 'account_deleted'` on every `oauth_refresh_tokens` row with `user_id = userID AND revoked_at IS NULL`.
- WHEN a client presents a refresh token issued before the account was deleted to `POST /oauth/token` with `grant_type=refresh_token` THE SYSTEM SHALL answer HTTP 400 with `error=invalid_grant` and SHALL NOT issue a new access or refresh token.
- WHEN the `delete_telegram_account` tool or `DELETE /api/account` succeeds THE SYSTEM SHALL have revoked the user's refresh-token families. Both entry points get this from the shared `HardDeleteAccount`.
- IF the revocation statement fails THEN THE SYSTEM SHALL roll back the whole delete: the `telegram_accounts` rows, agent data, notification state and `users` identity fields stay as they were. `HardDeleteAccount` SHALL return a wrapped error, and both entry points SHALL report failure (`storeErr` in the MCP tool, HTTP 500 in `DELETE /api/account`), not `deleted: true`.
- WHILE a refresh-token rotation for the same user runs at the same time as the delete THE SYSTEM SHALL NOT leave a live successor token after the delete commits. Either the rotation completes first and the delete revokes its successor, or the delete completes first and the rotation fails with `invalid_grant`.
- WHEN a row was already revoked for another reason (`rotated`, `reuse_detected`, `explicit_revoke`) THE SYSTEM SHALL leave its `revoked_at` and `revoked_reason` unchanged.
- WHEN a deleted account's revoked token is replayed later THE SYSTEM SHALL keep `revoked_reason = 'account_deleted'`. The existing reuse-detection family revoke only touches `revoked_at IS NULL` rows, so it changes nothing.
- WHEN a user deletes their account and later goes through a fresh OAuth authorization THE SYSTEM SHALL issue a new refresh-token family as usual. Only families that existed before the delete are revoked.
- WHILE the user is only disconnected (`disconnect_telegram_account`, `POST /api/account/disconnect`) THE SYSTEM SHALL keep the refresh-token families live, as it does today.
- THE SYSTEM SHALL leave access-token TTL, refresh-token TTL, refresh rotation, the grace window, `/oauth/revoke` and OAuth discovery metadata unchanged. Access tokens already issued expire on their own TTL (1h in production).
- THE SYSTEM SHALL state in `internal/web/privacy.html` and `SECURITY.md` that disconnect ends the Telegram session but keeps the client's OAuth grant, and that deleting the account or removing the connector revokes the client's refresh tokens, with already-issued access tokens living until their TTL ends.

## Out of scope

- Changing `disconnect_telegram_account` / `POST /api/account/disconnect` to revoke OAuth grants.
- Revoking already-issued access tokens (they are stateless JWTs, see SECURITY.md "Access tokens are not individually revocable").
- A new Prometheus counter. No refresh-family revocation counter exists today (`internal/metrics/metrics.go` has `mctl_sessions_revoked_total` for Telegram sessions only), and the issue asks for a reason label only "if a revocation counter exists".
- Deleting the `users` row or the refresh-token rows. Revoked rows stay until the existing expiry sweeper (`SweepExpiredRefreshTokens`) removes them.
- Any change to token TTLs, rotation, reuse detection or `/.well-known/oauth-authorization-server`.

## Open questions

- Should account deletion also revoke rows matched by `telegram_id` that sit under a different `users.id`? Every issuance path today binds `user_id` from `EnsureUserByTelegramID` (`internal/oauth/server.go:2236`) and the local-jwt identity resolves through the same function (`internal/auth/localjwt/issuer.go:330`), so `user_id` is sufficient. This proposal revokes by `user_id` only, as the issue specifies.
- No refresh-family revocation metric exists, so no metric is added. If reviewers want one, it should be a separate small change (for example `mctl_oauth_refresh_families_revoked_total{reason}` covering all four reasons).
