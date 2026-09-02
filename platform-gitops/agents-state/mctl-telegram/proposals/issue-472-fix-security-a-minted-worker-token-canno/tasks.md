# Tasks: issue-472-fix-security-a-minted-worker-token-canno

- [ ] 1. Add `Jti string \`json:"jti,omitempty"\`` to `localjwt.Claims` in
      `internal/auth/localjwt/issuer.go` — DoD: field marshals/unmarshals through `Mint`/
      `Verify`, existing tests (`issuer_test.go`) still pass unmodified, a token minted
      without a `jti` round-trips exactly as before (no regression for interactive tokens).

- [ ] 2. Generate and set `jti` at mint in `internal/workertoken/tokenhandler.go`'s
      `NewHandler` (depends on 1) — DoD: each call to `POST /api/mcp/worker-token` produces a
      token with a distinct, sufficiently random `jti` (128-bit+ entropy); the
      `"worker token minted"` log line carries `"jti"`; existing mint tests
      (`tokenhandler_test.go`) still pass.

- [ ] 3. Carry `jti` forward at renewal in `internal/workertoken/renewhandler.go`'s
      `NewRenewHandler` (depends on 1, 2) — DoD: renewing a token whose presented claims carry
      a `jti` produces a renewed token with the identical `jti`; renewing a pre-`jti` token
      (empty `claims.Jti`) mints one fresh `jti` for it; the `"worker token renewed"` log line
      carries `"jti"`; existing renewal tests (`renewhandler_test.go`) still pass.

- [ ] 4. Add `worker_token_revocations` table + indexes to `internal/db/db.go`
      (`sqliteSchema()`, `pgSchema()`, and the additive `db.Open` migration path) — DoD: table
      and both indexes (`idx_worker_token_revocations_jti` unique-where-not-null,
      `idx_worker_token_revocations_tg`) exist after `db.Open` on a fresh DB and after
      re-running `db.Open` against an existing DB (idempotent), on both sqlite and Postgres
      code paths; covered by a migration test in the style of `store_migration_test.go`.

- [ ] 5. Add `Store.RevokeWorkerToken`, `Store.RevokeWorkerTokensForTelegramID`,
      `Store.IsWorkerTokenRevoked`, `Store.ListWorkerTokenRevocations` to
      `internal/db/store.go` (depends on 4) — DoD: unit tests cover: revoking a `jti` makes
      `IsWorkerTokenRevoked` true for that `jti` and false for an unrelated one; revoking a
      `telegram_id` makes `IsWorkerTokenRevoked` true for any `issuedAt` at or before the
      revocation and false for one after; double-revoking the same `jti` does not error.

- [ ] 6. Add `RevocationCache` (TTL-refreshed, mutex-protected, fail-closed on an unpopulated
      cache) modeled on `internal/telegram/peercache.go` — DoD: unit tests cover a cache-hit
      revoked lookup, a cache-hit non-revoked lookup, cache-miss-defers-to-fresh-DB-read
      behavior (or documented eventual-consistency window), and a simulated Store error on
      first refresh causing `IsRevoked` to return an error rather than `false`.

- [ ] 7. Wire the denylist check into `localjwt.Provider.Authenticate`
      (`internal/auth/localjwt/issuer.go`), gated on `c.Jti != ""` (depends on 1, 5, 6) — DoD:
      a request bearing a token with no `jti` performs zero calls into the revocation cache
      (assert via a call-counting test double); a request bearing a revoked `jti` is rejected
      before `EnsureUserByTelegramID` runs; a request bearing a blanket-revoked `telegram_id`
      is rejected using `orig_iat` (falling back to `iat`) compared against the revocation
      timestamp.

- [ ] 8. Wire `RevocationCache` construction into `cmd/server/main.go`'s provider setup
      (`selectProvider`, and `selectBridgeProvider`/`selectAgentProvider` for consistency)
      (depends on 6, 7) — DoD: server starts with `AUTH_MODE=local-jwt` and the cache is
      non-nil on the constructed `localjwt.Provider`; existing `main_test.go`-style wiring
      tests (if any) still pass.

- [ ] 9. Add MCP admin tool `revoke_worker_token` in `internal/mcp/tools.go`, modeled on
      `toolRevokeSession`/`toolSetAccess` (depends on 5) — DoD: requires `admin:users`
      (rejected without it, matching the `tools_test.go` pattern for other admin tools);
      accepts exactly one of `jti` or `telegram_id` (400-equivalent tool error if both or
      neither given); calls the matching `Store` revoke method; emits an audit log entry via
      `s.audit`; registered in the tool list and covered by `output_schema_test.go` /
      `annotations_test.go` the same way `set_telegram_access` is.

- [ ] 10. Update `docs/runbook.md` and `docs/runbooks/canary.md` to document the new
      `revoke_worker_token` tool, the `jti`/blanket revocation semantics, and the note that a
      blanket per-Telegram-id revocation does not block a token minted *after* the revocation
      timestamp (depends on 9) — DoD: docs describe when to use `jti` vs `telegram_id`
      revocation and reference the still-available `OAUTH_JWT_SIGNING_KEY` rotation as the
      remaining full-population lever.

- [ ] E1. After recording a revocation, call `Hub.Unregister(userID)` from the revoke tool so a daemon that is already connected is dropped rather than left serving calls until its socket happens to fail — record first, evict second, or the daemon reconnects with a token that is not yet revoked. Nil-guard the Hub the way tool dispatch already does, since it is nil when Local Bridge is not configured — DoD: revoking an account with a connected daemon closes that connection; revoking one with no daemon is a no-op, not an error.

## Tests

- [ ] TE1. Test that revoking evicts a live connection: register a daemon on the Hub, revoke, assert the connection is gone and a call to it returns `ErrNoDaemonConnected`. **Validate by mutation**: remove the `Hub.Unregister` call and confirm this test fails. A test that only checks the revocation row was written passes without eviction and proves nothing about containment.
- [ ] TE2. Test that a token with no `jti` (an interactive session) triggers no revocation lookup — assert on a counting fake rather than on timing, and confirm by mutation that removing the `jti == ""` short-circuit fails it.
- [ ] T1. `internal/auth/localjwt`: a token with a revoked `jti` is rejected by
      `Provider.Authenticate` — and this test fails if the denylist check is deleted (per the
      issue's explicit acceptance criterion; do not merely assert a valid token still works).
- [ ] T2. `internal/auth/localjwt`: a token with no `jti` performs no revocation-cache lookup
      (interactive-session latency requirement).
- [ ] T3. `internal/workertoken`: mint -> renew -> assert identical `jti` across both tokens.
- [ ] T4. `internal/workertoken` + `internal/auth/localjwt` (integration-style): mint, revoke
      by `jti`, attempt `/api/mcp/worker-token/renew` with the revoked token, assert 401 (not
      merely "renew endpoint logic rejects it" — must go through the actual auth middleware
      chain, since the renew handler itself never re-checks revocation).
- [ ] T5. `internal/db`: `RevokeWorkerTokensForTelegramID` then `IsWorkerTokenRevoked` for a
      token `issuedAt` before/at/after the revocation timestamp returns true/true/false
      respectively.
- [ ] T6. `internal/mcp`: `revoke_worker_token` tool rejects a caller without `admin:users`,
      rejects a call with both `jti` and `telegram_id` set, rejects a call with neither set,
      and succeeds with exactly one set.
- [ ] T7. `internal/auth/localjwt`: revocation-store error on a `jti`-bearing token's check
      results in request rejection (fail-closed), not silent pass-through.

## Rollback

- All changes are additive: a new nullable-safe table, a new optional JWT claim, a new cache
  wired behind a nil-check, and a new MCP tool. Reverting the deploy (previous image tag via
  `mctl_rollback_service` / GitOps revert) drops the code path entirely; the
  `worker_token_revocations` table is simply unused by the prior version and can be left in
  place (no destructive migration to undo) or dropped manually if desired — it has no foreign
  key from any other table and no other code path reads it.
- If only the revocation *enforcement* needs to be disabled without a full rollback (e.g. the
  cache is misbehaving and fail-closed is rejecting legitimate traffic), the fastest mitigation
  is constructing the provider with a `nil` `RevocationCache` (task 8's wiring point), which
  short-circuits the check in task 7 back to today's behavior, at the cost of losing
  revocation coverage until a proper fix ships.
- No changes touch `oauth_refresh_tokens`, `bridge_token_hash`, or the existing
  `mode`/`GetAccessTier` gates, so rollback of this proposal cannot regress any of those
  existing (working) code paths.
