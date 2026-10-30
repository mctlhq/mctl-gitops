# Tasks: issue-781-account-deletion-leaves-the-user-s-oauth

- [ ] 1. In `internal/db/refresh_tokens.go`, add `const RefreshRevokedAccountDeleted = "account_deleted"` and the unexported `revokeUserRefreshTokens(ctx, tx *sql.Tx, userID int64, reason string, now time.Time) (int64, error)`. The helper runs `UPDATE oauth_refresh_tokens SET revoked_at=$1, revoked_reason=$2 WHERE user_id=$3 AND revoked_at IS NULL`. — DoD: compiles; the doc comment says rows already revoked keep their reason.
- [ ] 2. (depends on 1) In `Store.HardDeleteAccount` (`internal/db/store.go:958`), make these changes:
  - On Postgres (`s.isPostgres(ctx)`), take `SELECT id FROM users WHERE id=$1 FOR UPDATE` as the first statement in the tx.
  - Before `tx.Commit()`, call `revokeUserRefreshTokens(..., RefreshRevokedAccountDeleted, time.Now().UTC())`. On error, return `fmt.Errorf("delete account: revoke oauth refresh tokens: %w", err)`.
  - After commit, log `slog.Info` with `user_id` and the revoked count.
  - Add a comment explaining that `users` survives, so the FK cascade never fires.

  DoD: the signature is unchanged; `go vet` and `golangci-lint` are clean; the existing `HardDeleteAccount` tests pass.
- [ ] 3. (depends on 1) In `Store.RotateRefreshToken`, on Postgres take `SELECT id FROM users WHERE id=$1 FOR SHARE` on `newRT.UserID` as the first statement in the tx. Add a comment explaining the lock order with `HardDeleteAccount` (users row first in both, which prevents a live successor slipping past the delete and prevents deadlock). — DoD: the existing refresh rotation, grace-window and reuse tests pass unchanged.
- [ ] 4. Update the docs:
  - Rewrite the "Revoke access" bullet in `internal/web/privacy.html:54`. Disconnect ends the Telegram session and keeps the OAuth connection. Delete and connector removal revoke the client's refresh tokens. Issued access tokens expire within their TTL.
  - Adjust the endpoint comments at `privacy.html:146-147` to match.
  - Add an "account deletion revokes refresh-token families (`account_deleted`); disconnect does not" bullet under "Refresh tokens" in `SECURITY.md`.

  DoD: neither page says that disconnect revokes client access; any web golden or page tests are updated.
- [ ] 5. (depends on 2, 3) Add the tests below and confirm the regression tests fail when the `revokeUserRefreshTokens` call is removed. — DoD: `go test -race ./...` is green, the CI step "postgres-backed tests must not skip" picks up the new `*Postgres*` tests, and the failure with the call removed is noted in the PR description.

## Tests

- [ ] T1. `internal/oauth`, SQLite: `TestRefreshRefusedAfterAccountDeleted`.
  - Use `newTestServer` / `newTestStore`.
  - Issue a refresh token through the normal `/oauth/token` authorization-code flow.
  - Seed a `telegram_accounts` row for that `users.id`.
  - Call `store.HardDeleteAccount(ctx, uid)`.
  - POST `/oauth/token` with `grant_type=refresh_token`.
  - Assert HTTP 400 `invalid_grant`, no `access_token` in the body, and the row's `revoked_reason == "account_deleted"`. The replay must not have rewritten the reason to `reuse_detected`.
- [ ] T2. `internal/oauth`, Postgres: `TestRefreshRefusedAfterAccountDeleted_Postgres`. Same flow as T1, on `newPostgresOAuthStore` (`internal/oauth/dcr_allowlist_pg_test.go`).
- [ ] T3. `internal/db`, both dialects: `TestHardDeleteAccount_RevokesRefreshTokens` and `..._Postgres`.
  - Seed two families for the user (one with a rotated predecessor) and one family for another user (Bob).
  - Seed a row already revoked with `explicit_revoke`.
  - After the delete, assert:
    - every previously active row of the user has `account_deleted`;
    - the `rotated` and `explicit_revoke` rows keep their reason and `revoked_at`;
    - Bob's family is untouched.
- [ ] T4. `internal/db`, both dialects: `TestHardDeleteAccount_RevocationFailureRollsBack` and `..._Postgres`.
  - Install a trigger that aborts any `UPDATE` of `oauth_refresh_tokens`:
    - SQLite: `CREATE TRIGGER ... BEFORE UPDATE ON oauth_refresh_tokens BEGIN SELECT RAISE(ABORT, 'boom'); END`.
    - Postgres: a plpgsql function that does `RAISE EXCEPTION`, in a per-test schema.
  - Call `HardDeleteAccount` and assert it returns an error.
  - Assert that `telegram_accounts`, a seeded agent row, notification preferences and the `users` identity fields are all unchanged, and that the refresh token is still live.
- [ ] T5. `internal/web` and `internal/mcp`: with a store whose revocation fails (same trigger), assert that `DELETE /api/account` returns 500 and does not return `"deleted": true`, and that `delete_telegram_account` returns a tool error.
- [ ] T6. `internal/db`, Postgres: `TestHardDeleteAccount_ConcurrentRotation_Postgres`.
  - Run `RotateRefreshToken` and `HardDeleteAccount` concurrently in a loop (N iterations).
  - Assert that after both finish, no row with `user_id = uid AND revoked_at IS NULL` remains, and that neither call deadlocks or returns an error other than `ErrRefreshTokenNotFound` from rotation.
- [ ] T7. Disconnect regression: after `RevokeActiveSession` (the disconnect path), the refresh grant still succeeds.

## Rollback

Revert the PR (merge-commit revert). No schema change was made, so nothing needs migrating
back. Rows already revoked with `account_deleted` stay revoked. That is the correct state
for deleted accounts, and the affected clients just re-authorize. If only the rotation lock
causes trouble (lock waits on refresh), revert task 3 alone. The delete-side revocation
still closes the main gap, with only the narrow concurrent-rotation race reopened.
