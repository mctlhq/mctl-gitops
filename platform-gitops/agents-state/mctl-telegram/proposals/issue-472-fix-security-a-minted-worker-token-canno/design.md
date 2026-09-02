# Design: issue-472-fix-security-a-minted-worker-token-canno

## Current state

- `internal/workertoken/tokenhandler.go` (`NewHandler`) mints a worker token via
  `localjwt.Issuer.Mint` with `Claims{Subject, TelegramID, Scopes, Audience, OriginalIssuedAt}`.
  There is no `jti` field on `localjwt.Claims` (`internal/auth/localjwt/issuer.go:31-50`) and
  none is generated at mint.
- `internal/workertoken/renewhandler.go` (`NewRenewHandler`) re-verifies the presented token,
  checks its audience marker (`workerAudience`/`workerBridgeAudience`), enforces the
  `maxRenewalChain` ceiling anchored on `OriginalIssuedAt`, and mints a new token carrying the
  same `Subject`/`TelegramID`/`Scopes`/`Audience`/`OriginalIssuedAt`. It has no way to signal
  "this credential's identity persists across renewal" beyond the fields already there, so a
  `jti` would need to be added here too, and carried forward unchanged (not regenerated) so
  that revoking the original `jti` also blocks every renewal.
- `internal/auth/localjwt.Verify` checks signature, issuer, and expiry
  (`internal/auth/localjwt/issuer.go:113-145`). `localjwt.Provider.Authenticate`
  (`internal/auth/localjwt/issuer.go:213-253`) calls `Verify`, then `CheckAudience`, then
  `p.Store.EnsureUserByTelegramID`, then returns an `auth.Identity`. This is the single choke
  point every `/mcp`, `/api/bridge/token`, `/api/mcp/worker-token`, and
  `/api/mcp/worker-token/renew` request passes through (`cmd/server/main.go:410-479`, all
  wired with `auth.Middleware(provider, true, m, resourceMeta)` where `provider` is the
  `localjwt.Provider` returned by `selectProvider`). It already holds `Store *db.Store`, so it
  is the natural place to add a denylist lookup — no new provider or routing change needed.
- `internal/db/store.go` has an established revocation shape to imitate:
  `oauth_refresh_tokens` carries `revoked_at`/`revoked_reason`
  (`internal/db/db.go:335-350` sqlite, mirrored in `pgSchema()`), and `RevokeActiveSession`
  (`internal/db/store.go:615`) / `RevokeSessionByID` (`internal/db/store.go:635`) follow the
  `UPDATE ... SET revoked_at = CURRENT_TIMESTAMP WHERE ... revoked_at IS NULL` pattern. New
  columns are added additively and idempotently via `addColumnIfMissing` in `db.Open`
  (`internal/db/db.go:100-133`), which is how `mode`/`bridge_token_hash` were introduced for
  M4 — the established migration mechanism for this repo (there is no separate migrations
  directory; `db.Open` is the migration path).
- Admin-gated write operations in this codebase are MCP tools, not bare HTTP routes:
  `set_telegram_access` and `revoke_telegram_session` (`internal/mcp/tools.go:903-,1230-`)
  both call `requireScope(id, "admin:users")`, resolve the target via
  `s.Store.UserIDByTelegramID`, perform the write, and call `s.audit(...)`. This is the
  pattern the new revoke operation should follow rather than inventing a new HTTP endpoint
  and a new `auth.Provider` wiring.
- `internal/telegram/peercache.go` (`PeerCache`) is the codebase's existing precedent for an
  in-process, mutex-protected, TTL-based cache wired in at `cmd/server/main.go` and passed
  into the component that needs it (`mcpSrv.WithPeerCache(peerCache)`) — the shape to copy
  for the revocation cache.
- `internal/audit/redact.go` redacts by key name against `sensitiveKeys`; `jti` is an opaque
  random identifier carrying no user data, so logging it needs no new redaction entry (unlike
  message bodies, phone numbers, session strings).

## Proposed solution

1. **Add `Jti string \`json:"jti,omitempty"\`` to `localjwt.Claims`.** No signing-format
   change: the field is just marshaled into the existing JWT body alongside `orig_iat`.
   Tokens minted before this change simply omit it, and `Verify` already tolerates unknown
   absent fields.

2. **Generate a `jti` at mint, carry it forward at renewal.**
   - `internal/workertoken/tokenhandler.go`'s `NewHandler`: generate a random `jti` (128-bit,
     base64url — matching the entropy style already used for signing, no new dependency
     needed beyond `crypto/rand`) once per mint call and set it on the `localjwt.Claims`
     passed to `signer.Mint`. Add it to the existing `slog.Info("worker token minted", ...)`
     call (`tokenhandler.go:219`) as `"jti"`.
   - `internal/workertoken/renewhandler.go`'s `NewRenewHandler`: read `claims.Jti` off the
     presented (already-verified) token and set the same value on the renewed token's
     `localjwt.Claims`. If `claims.Jti == ""` (a token minted before this change), mint the
     renewed token with a freshly generated `jti` — this is the one point where a pre-`jti`
     token gains one, after which every subsequent renewal carries it forward. Add `jti` to
     the existing `slog.Info("worker token renewed", ...)` call (`renewhandler.go:209`).

3. **New table `worker_token_revocations`**, added via `addColumnIfMissing`-style additive
   migration in `db.Open` (new `CREATE TABLE IF NOT EXISTS` alongside `sqliteSchema()` /
   `pgSchema()`, following the `oauth_refresh_tokens` precedent exactly):
   ```sql
   CREATE TABLE IF NOT EXISTS worker_token_revocations (
       id INTEGER PRIMARY KEY AUTOINCREMENT,   -- BIGSERIAL in pg
       jti TEXT,                               -- NULL for a blanket revocation
       telegram_id BIGINT NOT NULL,
       revoked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,  -- TIMESTAMPTZ in pg
       reason TEXT,
       revoked_by BIGINT                       -- admin user_id, for audit
   )
   CREATE UNIQUE INDEX IF NOT EXISTS idx_worker_token_revocations_jti
       ON worker_token_revocations(jti) WHERE jti IS NOT NULL
   CREATE INDEX IF NOT EXISTS idx_worker_token_revocations_tg
       ON worker_token_revocations(telegram_id)
   ```
   A row with `jti` set is a single-token revocation. A row with `jti IS NULL` is a blanket
   revocation for `telegram_id`: any worker token for that id with `orig_iat` (falling back
   to `iat`) at or before `revoked_at` is rejected — this is what makes "revoke every worker
   token for a user" work without a token registry, per the issue's stated intent.

4. **`Store` methods**, next to the existing `RevokeActiveSession`/`GetAccessTier` style:
   - `RevokeWorkerToken(ctx, jti, reason string, revokedBy int64) error` — inserts a
     `jti`-scoped row. `ON CONFLICT (jti) DO NOTHING` (pg) / `INSERT OR IGNORE` (sqlite) so
     re-revoking the same `jti` is a no-op, not an error.
   - `RevokeWorkerTokensForTelegramID(ctx, tgID int64, reason string, revokedBy int64) error`
     — inserts a blanket row (`jti = NULL`).
   - `IsWorkerTokenRevoked(ctx, jti string, telegramID int64, issuedAt time.Time) (bool, error)`
     — `SELECT EXISTS(... WHERE jti = ? OR (jti IS NULL AND telegram_id = ? AND revoked_at >= ?))`.
     This is the method the denylist cache refreshes from, and also what the cache's
     cache-miss / cold-start path calls directly.

5. **Denylist check in `localjwt.Provider.Authenticate`**, gated on `c.Jti != ""` so an
   interactive session (no `jti`) takes the existing code path unchanged — zero extra DB
   round trips for the common case, satisfying the issue's explicit acceptance criterion.
   When `c.Jti != ""`:
   ```go
   if p.RevocationCache != nil {
       revoked, err := p.RevocationCache.IsRevoked(r.Context(), c.Jti, c.TelegramID, originAnchor(c))
       if err != nil {
           return nil, fmt.Errorf("check worker token revocation: %w", err)
       }
       if revoked {
           return nil, errors.New("worker token revoked")
       }
   }
   ```
   placed right after `CheckAudience` and before `EnsureUserByTelegramID`, so a revoked
   token never touches the user-provisioning path. `originAnchor`-equivalent logic (prefer
   `orig_iat`, fall back to `iat`) is duplicated here as a small unexported helper in
   `localjwt` rather than importing `internal/workertoken` (which would invert the existing
   dependency direction — `workertoken` imports `localjwt`, not the reverse).

6. **`RevocationCache`**, new type in `internal/auth/localjwt` (or a small new
   `internal/workertoken/revocation` package if `localjwt` should stay free of caching
   concerns — see Alternatives), modeled on `PeerCache`: a mutex-protected map keyed by
   `jti`, plus a separately-cached slice/set of blanket-revoked `telegram_id`s, refreshed
   from `Store.ListWorkerTokenRevocations(ctx)` (a full-table read — "expected to hold
   single-digit rows" per the issue) on a short TTL (default 10s, configurable, hard upper bound 15s). A cache
   miss (unknown `jti`, not in the blanket set) is a fast in-memory `false` with no DB call;
   the DB is only hit on periodic refresh, not per-request. This is what keeps a revocation
   check cheap even though every `jti`-bearing request pays it. Fail-closed: if the refresh
   goroutine's most recent attempt errored and the cache has never successfully populated,
   `IsRevoked` returns an error (reject) rather than silently reporting "not revoked" —
   consistent with the codebase's "no panics, wrap and return" posture and the acceptance
   criterion that a revocation-store outage must not fail open.

7. **New MCP admin tool `revoke_worker_token`** in `internal/mcp/tools.go`, following
   `toolRevokeSession`'s shape exactly: `requireScope(id, "admin:users")`, one required input
   that is either `jti` (string) or `telegram_id` (int) — reject if both or neither are
   supplied — call the matching `Store` method, `s.audit(ctx, id, "revoke_worker_token", ...)`,
   return `{revoked: bool}`. Registered alongside the other admin tools the same way
   `set_telegram_access`/`revoke_telegram_session` are.

8. **Wiring**: `cmd/server/main.go`'s `selectProvider` (or its caller) constructs the
   `RevocationCache` once (bound to `store`) and passes it into `localjwt.NewProvider` via a
   new `ProviderConfig.RevocationCache` field, mirroring how `store` itself is already
   threaded through. `selectBridgeProvider`/`selectAgentProvider` build their own
   `localjwt.Provider` instances (`internal/auth/localjwt/issuer.go:191-205`) for `/bridge`
   and `/api/agent/v1`; worker tokens are never valid there today (different audience), so
   those providers do not strictly need the cache, but wiring it into all three is simpler
   than special-casing one provider and matches "reject at `/mcp` and at
   `/api/bridge/token`" from the issue's acceptance criteria — `/api/bridge/token` is minted
   under `provider` (the plain `/mcp` provider, see `cmd/server/main.go:445-453`), so a
   revoked worker token is already rejected there once `provider` itself carries the check;
   no separate change to `bridge.NewBridgeTokenHandler` is needed.

### Evicting a live bridge connection

Revocation has to reach a daemon that is already connected, not only the next one that
tries to connect. `NewBridgeHandler` (`internal/bridge/server.go`) authenticates once,
before the websocket upgrade; the reader and writer goroutines never re-check the token,
so an open connection is never re-authenticated. Without eviction a revoked credential
keeps serving calls until the socket drops on its own, which for a long-lived daemon may
be days -- and this is the exact scenario the feature exists to stop.

The revoke tool therefore calls `Hub.Unregister(userID)` after recording the revocation.
The Hub is already on the MCP server (`internal/mcp/server.go:28`, wired by `WithHub`,
nil when Local Bridge is not configured -- so the call must be nil-guarded the way tool
dispatch already guards it). `Unregister` closes the connection's send channel, which
ends the writer goroutine and tears the connection down; it is idempotent, so revoking an
account with no daemon connected is a no-op rather than an error.

Order matters: record the revocation first, then evict. Evicting first leaves a window in
which the daemon reconnects, presents its not-yet-revoked token, and is accepted.

Re-authenticating mid-connection (re-checking the token on a periodic ping, say) was
considered and not proposed: it is a larger change to the connection lifecycle for a
strictly slower cut-off than closing the socket outright.

## Alternatives

- **Store the denylist check inside `internal/workertoken` instead of `localjwt`.** Rejected:
  `localjwt.Provider.Authenticate` is the only choke point every request (including
  `/api/bridge/token` mint and `/mcp` tool calls) passes through. Putting the check in
  `workertoken` would require every call site to remember to invoke it separately, which is
  exactly the kind of "the lever looks like it should work but doesn't" bug this issue is
  about (see how `mode` and `GetAccessTier` are each checked in only one of several places
  that needed them).
- **No cache — query `worker_token_revocations` on every `jti`-bearing request.** Rejected as
  the primary design because the issue's "single-digit rows... cache it" language is a direct
  instruction, and because worker tokens are exactly the long-lived, repeatedly-used
  credential (a Local Bridge daemon calling `/mcp` continuously) where a per-request DB
  round trip is most costly. Kept as the fallback behavior on a cache miss / cold start.
- **Wire up `bridge_token_hash` instead of adding a `jti` denylist.** Explicitly rejected by
  the issue itself: it only ever covers the 1-hour bridge JWT, which is re-mintable from the
  still-valid long-lived MCP JWT, so revoking the bridge-scoped hash would not stop the
  worker token that produces it.
- **Revoke by blacklisting the token's raw JWT string (hash) instead of a `jti` claim.**
  Rejected: it would require the caller to have the full token to revoke it, which directly
  contradicts the issue's "revoking every worker token for a user" and "a token found in an
  old audit line" requirements — the point of a `jti` is that it is a short opaque value that
  can be logged and referenced without ever storing or re-presenting the sensitive token
  itself.

## Platform impact

- **Migrations**: one new table (`worker_token_revocations`) plus two indexes, added the same
  additive way `oauth_refresh_tokens` was — safe on both sqlite and Postgres, no backfill,
  no lock contention (empty table at deploy time). `localjwt.Claims.Jti` is a new optional
  JSON field; JWTs are not a fixed schema, so this is fully backward compatible with
  already-issued tokens (they verify identically, just without denylist coverage until their
  next renewal mints a `jti` for them).
- **Backward compatibility**: tokens minted before this change carry no `jti` and are
  therefore never denylist-checked (by design — matches "interactive sessions... take no
  extra database round trip", and pre-existing worker tokens are a small, known population
  per `docs/runbooks/canary.md`). They gain a `jti` at their next renewal. Operators who want
  immediate coverage for an already-leaked pre-`jti` token still have the existing lever
  (rotate `OAUTH_JWT_SIGNING_KEY`) as a bridge until this ships and tokens have renewed once,
  or can wait out the token's TTL.
- **Resource impact**: one extra in-memory cache (bounded, single-digit-row backing table) and
  a periodic background refresh query at a period on the order of 10 seconds — negligible.
  Zero added latency for interactive sessions (no `jti`, no check). `jti`-bearing requests pay
  one mutex-protected map lookup, no DB round trip in the common (cache warm) case.
- **Risks + mitigations**:
  - *Fail-open bug in the cache (returns "not revoked" during an outage)* would silently
    defeat the whole feature. Mitigated by the explicit fail-closed requirement in this
    design and in requirements.md's acceptance criteria, and by a unit test that asserts a
    revoked `jti` is rejected specifically when the check is present, per the issue's
    "test that fails when the denylist check is removed" acceptance criterion.
  - *Renewal regenerating a fresh `jti` instead of carrying the old one forward* would let a
    compromised worker escape a revocation by renewing before the operator notices. Mitigated
    by making `renewhandler.go` copy `claims.Jti` explicitly (covered by a dedicated test:
    mint, renew, assert same `jti`; revoke, attempt renew, assert 401).
  - *Blanket per-Telegram-id revocation also blocking a legitimate future token for that id*
    if the operator forgets it is still in effect. This is intentional (matches "revoking
    every worker token for a user" as the stated operator intent) but should be called out in
    `docs/runbook.md` so an operator knows a fresh mint for a previously-blanket-revoked id
    works (mint sets a new `orig_iat` after the revocation timestamp) while old tokens for
    that id stay dead.
