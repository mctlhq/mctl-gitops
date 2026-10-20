# Design: issue-781-account-deletion-leaves-the-user-s-oauth

## Current state

**Delete path.** `Store.HardDeleteAccount(ctx, userID)` (`internal/db/store.go:958-1028`)
opens one transaction and runs these steps in order:
1. Counts the active `telegram_accounts` rows, for the `mctl_sessions_revoked_total{reason="delete"}` metric.
2. Runs `DELETE FROM telegram_accounts WHERE user_id = $1`.
3. Calls `purgeAgentData` (`internal/db/agent_domain.go`).
4. Calls `purgeNotificationState`.
5. Runs `UPDATE users SET telegram_first_name = NULL, ...`.
6. Commits.

The metric is incremented only after the commit. The `users` row is deliberately kept,
and comments in the function already explain why other user-scoped data must be purged
explicitly. Nothing touches `oauth_refresh_tokens`.

**Callers.** Both callers run the delete inside `Pool.RemoveAtomic`:
- `delete_telegram_account` (`internal/mcp/tools.go:886-899`). On error it returns `s.storeErr(ctx, "delete", err)`.
- `AccountHandlers.delete` (`internal/web/account.go:115-145`). On error it returns HTTP 500 `"delete failed"`, and calls the store directly when `Pool == nil`.

Both already treat a `HardDeleteAccount` error as a failed delete. Neither caller needs to
change.

**Refresh tokens.**
- Schema (`internal/db/db.go`, `CREATE TABLE IF NOT EXISTS oauth_refresh_tokens`): `user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE`, `family_id`, `revoked_at`, `revoked_reason`. It is indexed on `token_hash` (unique) and `family_id`, and has no index on `user_id`.
- `internal/db/refresh_tokens.go` has `SaveRefreshToken` and `LookupRefreshToken`, plus `RotateRefreshToken`, which in one tx sets the old row to `revoked_reason='rotated' WHERE revoked_at IS NULL` and inserts the successor with the same `family_id` and `user_id`.
- `RevokeRefreshTokenFamily(ctx, familyID, reason)` runs on `s.DB`, not a tx, and only touches `revoked_at IS NULL` rows. The reasons in use are `rotated`, `reuse_detected` and `explicit_revoke` (`internal/oauth/server.go:2439,2541,2678`).

**Refresh grant.** `Server.handleTokenRefresh` (`internal/oauth/server.go:~2370`):
- For a revoked token, `attemptGraceRecovery` returns `graceNotEligible` unless `revokedReason == "rotated"` and the token is inside the grace window. The handler then calls `RevokeRefreshTokenFamily(..., "reuse_detected")`, which matches 0 rows because everything is already revoked, and answers `invalid_grant` ("refresh token already used").
- A row revoked with `account_deleted` is therefore refused with `invalid_grant`. Its reason is not overwritten and the handler needs no change.
- When the old token is revoked concurrently, `RotateRefreshToken` returns `ErrRefreshTokenNotFound` and the handler answers `invalid_grant` (around line 2538).

**User id binding.** Refresh tokens are issued with
`uid := EnsureUserByTelegramID(entry.TelegramID, ...)` (`internal/oauth/server.go:2236`).
The local-jwt `/mcp` identity resolves `UserID` with the same function
(`internal/auth/localjwt/issuer.go:330`), so `id.UserID` passed to `HardDeleteAccount` is
the `user_id` on the user's refresh tokens.

**Dialect helper.** `s.isPostgres(ctx)` (`internal/db/agent_jobs.go:85`) is already used to
add `FOR SHARE` / `FOR UPDATE` only on Postgres (`internal/db/agent_actions.go:187-195`),
for a similar race against the account-delete purge.

**Metrics.** `internal/metrics/metrics.go` has `SessionsRevokedTotal`
(`mctl_sessions_revoked_total{reason}`, Telegram sessions). There is no counter for
refresh-token family revocations.

**Docs.**
- `internal/web/privacy.html:54` says "Revoke access: call `disconnect_telegram_account` or `delete_telegram_account` ...". That is wrong for disconnect.
- `privacy.html:146-147` describes the HTTP endpoints without the OAuth effect.
- `SECURITY.md` "Refresh tokens" (around lines 74-83) lists rotation, reuse detection, lifetime and `/oauth/revoke`, but not account deletion.

**Tests.**
- SQLite store tests use `newTestStore` (`internal/db/store_test.go:198`). OAuth server tests use `newTestStore` / `newTestServer` (`internal/oauth/server_test.go:76`).
- Postgres tests gate on `TEST_DATABASE_URL`. `internal/oauth/dcr_allowlist_pg_test.go` has `newPostgresOAuthStore`, which uses a schema per test.
- The CI step "postgres-backed tests must not skip" (`.github/workflows/build.yml`) runs `go test ./internal/db/ ./internal/oauth/ -run 'Postgres|TestOpenPool'`. New Postgres tests must have `Postgres` in their name to be gated.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: tenant `labs`, `AUTH_MODE: local-jwt` (so the OAuth refresh grant is live in production), `OAUTH_ACCESS_TOKEN_TTL: "1h"`. There is no `OAUTH_REFRESH_TOKEN_TTL` override, so the 30-day default applies. The database is Postgres (`database: "labs-mctl-telegram"`), at replicaCount 1 per the values comments.
- The mctl MCP tools (`mctl_get_service_config` etc.) were not called. The gitops values file was enough for the facts used here, and no runtime behaviour is asserted beyond it.

## Proposed solution

### 1. Revocation helper inside the delete transaction (`internal/db/refresh_tokens.go`)

Add an exported reason constant and an unexported tx-scoped helper:

```go
// RefreshRevokedAccountDeleted is the revoked_reason HardDeleteAccount writes.
const RefreshRevokedAccountDeleted = "account_deleted"

// revokeUserRefreshTokens revokes every still-active refresh token of userID
// inside tx. Rows already revoked keep their original reason.
func revokeUserRefreshTokens(ctx context.Context, tx *sql.Tx, userID int64, reason string, now time.Time) (int64, error) {
    res, err := tx.ExecContext(ctx,
        `UPDATE oauth_refresh_tokens SET revoked_at = $1, revoked_reason = $2
          WHERE user_id = $3 AND revoked_at IS NULL`,
        now, reason, userID)
    if err != nil { return 0, fmt.Errorf("revoke user refresh tokens: %w", err) }
    n, _ := res.RowsAffected()
    return n, nil
}
```

Rows in a family share `user_id`, because `RotateRefreshToken` copies it, so revoking by
`user_id` revokes every family of the user. `RevokeRefreshTokenFamily` is not reused because
it runs outside a tx and is keyed on one family. A tx-scoped statement is what makes "same
transaction, fail together" true.

### 2. Call it from `HardDeleteAccount` (`internal/db/store.go`)

- **Lock first.** On Postgres, first `SELECT id FROM users WHERE id = $1 FOR UPDATE` as the first statement after `BeginTx`. The reason is in "Race with rotation" below.
- **Revoke before commit.** After the identity-field `UPDATE users` and before `tx.Commit()`, call `revokeUserRefreshTokens(ctx, tx, userID, RefreshRevokedAccountDeleted, time.Now().UTC())`, and on error return `fmt.Errorf("delete account: revoke oauth refresh tokens: %w", err)`. The deferred `tx.Rollback()` then undoes everything, which satisfies "a failure to revoke must fail the delete". Add a comment explaining the reason, matching the existing purge comments: `users` survives, so the `ON DELETE CASCADE` never fires.
- **Log after commit.** After a successful commit, log `slog.Info("account deleted: oauth refresh tokens revoked", "user_id", userID, "tokens", n)`. Only the count and the internal id are logged, which is consistent with `internal/audit/redact.go` (no phone, name or token).
- **No new metric.** None exists for refresh families (see Out of scope).
- **Signature unchanged.** The return signature `(int64, error)` stays the same, so the callers and `internal/broadcast/service_test.go` need no change.

**Race with rotation.** Under Postgres READ COMMITTED, a `RotateRefreshToken` that is in
flight when the delete's `UPDATE` starts can insert a successor row that the `UPDATE`'s
snapshot does not see, leaving one live token. Fix it with one lock order, `users` row
first, in both transactions:
- **Delete side.** `HardDeleteAccount` takes `FOR UPDATE` on the `users` row, Postgres only, via `s.isPostgres(ctx)`.
- **Rotation side.** `RotateRefreshToken` gains, as its first statement in the tx, `SELECT id FROM users WHERE id = $1 FOR SHARE` on `newRT.UserID` (Postgres only). It is taken before it revokes the old row.

The two orderings then play out like this:
- **Delete first.** Rotation blocks on the users row. When it proceeds, its `UPDATE ... WHERE token_hash = $2 AND revoked_at IS NULL` matches 0 rows, so it returns `ErrRefreshTokenNotFound`, and the handler answers `invalid_grant`.
- **Rotation first.** The delete blocks until the rotation commits. Its later `UPDATE` statement takes a fresh snapshot and revokes the successor.

Taking the users lock first in both transactions avoids the deadlock that the
FK-implied `FOR KEY SHARE` from the successor insert would otherwise cause.

On SQLite, writers are serialised by the database lock. A delete that loses a write race
gets `SQLITE_BUSY` and fails closed, so the user retries and the account is not reported
deleted.

Fresh authorization-code issuance (`EnsureUserByTelegramID` followed by `SaveRefreshToken`)
is not locked. A new grant completed by the user in a browser after the delete commits is
a new consent and is legitimate.

### 3. Documentation

- **`internal/web/privacy.html:54`.** Replace the "Revoke access" bullet with: `disconnect_telegram_account` (or `POST /api/account/disconnect`) ends the Telegram session but keeps the client's OAuth connection, so reconnecting Telegram does not require re-adding the connector. `delete_telegram_account` (or `DELETE /api/account`) also revokes every OAuth client's refresh tokens, and so does removing the connector from the client. Already-issued access tokens expire within their lifetime (at most 1 hour in production).
- **`privacy.html:146-147`.** Adjust the endpoint comments the same way.
- **`SECURITY.md` "Refresh tokens".** Add a bullet: "Revoked on account deletion." `delete_telegram_account` and `DELETE /api/account` revoke every refresh-token family of the user in the delete transaction (`revoked_reason = account_deleted`). A failed revocation fails the delete. Disconnect does not revoke, by design. Access tokens already issued live until their TTL, as for every revocation.

## Alternatives

1. **Delete the `users` row so the FK cascade revokes the tokens.** Dropped. The `users` row is deliberately kept: it anchors the audit chain (`tool_audit.user_id REFERENCES users(id)` has no cascade) and other identity state. Deleting it means a much larger change, and rows that are deleted rather than revoked lose the reuse-detection history.
2. **Call `RevokeRefreshTokenFamily` per family from the callers after `HardDeleteAccount`.** Dropped. It is not atomic with the delete, which allows the forbidden partial success (account deleted, clients live). It would also have to be added to two entry points and enumerate families.
3. **Make the refresh grant check that the user still has an account, instead of revoking.** Dropped. It does not survive reconnection, which is the exact case where the old client would regain message access. It also changes refresh semantics, which the issue rules out, and leaves rows that look live in the table.

## Platform impact

- **Migrations.** None. `revoked_reason` is free-text, and no index is added. The `UPDATE` scans `oauth_refresh_tokens` by `user_id` with no index. That is acceptable at current table size (bounded by the TTL sweeper), and deletes are rare. An index on `user_id` can follow separately if needed.
- **Backward compatibility.** API responses are unchanged. Clients of a deleted account get `invalid_grant` on refresh and must re-authorize, which is the intended effect. Disconnect is unchanged.
- **Risk: deletes fail more often.** The users-row lock adds a short wait when a refresh for the same user is in flight. That is milliseconds, and it only touches the deleting user's rows. A revocation DB error now fails the delete, as the issue requires. Both callers already surface errors.
- **Risk: `RotateRefreshToken` gets one extra lock statement on Postgres.** It is a cheap point lock on a primary key, taken in shared mode, so concurrent refreshes do not block each other.
- **Resources.** One extra statement per delete and one per refresh rotation. Negligible.
- **Observability.** One `slog.Info` per delete, with a count. No new metric.
