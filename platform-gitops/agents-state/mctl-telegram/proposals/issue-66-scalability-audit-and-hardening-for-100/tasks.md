# Tasks: issue-66-scalability-audit-and-hardening-for-100

- [ ] 1. Add `TELEGRAM_MAX_SESSIONS` cap to `ClientPool` and wire config
  - In `internal/telegram/clientpool.go`: add `MaxSessions int` field and
    `ErrPoolFull` sentinel; add `WithMaxSessions(n int) *ClientPool` chaining
    method; in `acquire()`, return `ErrPoolFull` when
    `p.MaxSessions > 0 && len(p.entries) >= p.MaxSessions`.
  - In `internal/config/config.go`: add `TelegramMaxSessions int` field parsed
    from `TELEGRAM_MAX_SESSIONS` env var (default 0, no cap).
  - In `cmd/server/main.go`: pass `cfg.TelegramMaxSessions` to
    `pool.WithMaxSessions()`.
  - In `internal/mcp/tools.go`: add `ErrPoolFull` case to `borrowErrResult()`.
  - DoD: `go test ./internal/telegram/...` passes with a test that hits the cap
    and receives `ErrPoolFull`; `TELEGRAM_MAX_SESSIONS=1` env var is parsed and
    a second `Borrow` returns an error.

- [ ] 2. Add `TelegramPoolCapacity` metric (depends on 1)
  - In `internal/metrics/metrics.go`: add `TelegramPoolCapacity prometheus.Gauge`
    with name `mctl_telegram_pool_capacity` and register it.
  - In `cmd/server/main.go`: after pool construction, call
    `m.TelegramPoolCapacity.Set(float64(cfg.TelegramMaxSessions))` (set -1 when
    0, or leave it at 0 and document that 0 means uncapped in the Help string).
  - DoD: `/metrics` response includes `mctl_telegram_pool_capacity` with the
    configured value.

- [ ] 3. Add `FloodWaitSeconds` helper to `internal/telegram/`
  - Create `internal/telegram/floodwait.go` with `FloodWaitSeconds(err error) int`
    using `errors.As` to unwrap `*tgerr.Error`, check `Code == 420`, strip the
    `FLOOD_WAIT_` prefix, and parse the integer.
  - DoD: unit tests in `floodwait_test.go` cover: nil error, non-FloodWait
    tgerr, `FLOOD_WAIT_30`, `FLOOD_WAIT_0`, wrapped FloodWait.

- [ ] 4. Add `TelegramFloodWaitEventsTotal` metric (depends on 3)
  - In `internal/metrics/metrics.go`: add
    `TelegramFloodWaitEventsTotal *prometheus.CounterVec` labeled by `tool`.
  - DoD: `/metrics` response includes `mctl_telegram_flood_wait_events_total`
    after a flood-wait event is triggered in a test.

- [ ] 5. Implement `borrowWithRetry` in `internal/mcp/tools.go` (depends on 3, 4)
  - Add `borrowWithRetry(ctx, tool, userID, fn)` method on `mcp.Server` as
    described in design.md. Constants: `maxFloodWaitRetries=3`,
    `maxFloodWaitSleep=60s`.
  - Replace all `s.Pool.Borrow(ctx, id.UserID, func(...) {...})` calls in
    `toolListDialogs`, `toolGetUnreadMessages`, `toolGetMessages`,
    `toolSendMessage`, `toolPinMessage` with `s.borrowWithRetry(ctx, "<tool>", ...)`.
  - Extend `borrowErrResult` with a FloodWait case that returns the
    `retry_after_seconds` field.
  - DoD: `go test ./internal/mcp/...` passes; a test that injects a
    FLOOD_WAIT_1 error observes one retry and increments the counter; a
    cancelled context exits without sleeping.

- [ ] 6. Add Postgres schema for OAuth transient state (depends on nothing)
  - In `internal/db/db.go` `pgSchema()`: add `CREATE TABLE IF NOT EXISTS`
    statements for `oauth_pending_auth`, `oauth_auth_codes`,
    `oauth_client_registrations` as specified in design.md.
  - In `internal/db/db.go` `Migrate()`: ensure new tables are created on
    startup (they are part of `pgSchema()` which already runs in `Migrate`).
  - DoD: `go test ./internal/db/...` passes with Postgres DSN; tables appear
    after migrate; re-running migrate is idempotent.

- [ ] 7. Add DB-backed OAuth store methods (depends on 6)
  - In `internal/db/store.go` add:
    `InsertOAuthPending`, `ConsumeOAuthPending`,
    `InsertOAuthCode`, `ConsumeOAuthCode`,
    `InsertClientReg`, `GetClientReg`,
    `DeleteExpiredOAuthCodes`.
  - Each method panics on nil DB, returns `db.ErrNotFound` for missing/expired
    rows (consistent with existing patterns like `ErrRefreshTokenNotFound`).
  - DoD: table-driven unit tests in `internal/db/store_oauth_test.go` cover
    insert, consume, expiry-on-read, and idempotent re-consume.

- [ ] 8. Wire Postgres OAuth persistence into `oauth.Server` (depends on 7)
  - In `internal/oauth/server.go`: add `useDB bool` to `Server` and
    `UseDBForOAuth bool` to `Config`.
  - Gate `handleAuthorize`, `issueAuthCode`, `handleTelegramCallback`
    (pending and code paths), `handleTokenAuthCode`, and `handleClientRegistration`
    to call DB methods when `s.useDB`, in-memory maps otherwise.
  - The `enables` map stays in-memory regardless.
  - The background sweeper calls `store.DeleteExpiredOAuthCodes` when `useDB`
    is true, in addition to the in-memory sweep.
  - In `cmd/server/main.go`: set `UseDBForOAuth: strings.HasPrefix(cfg.DatabaseURL, "postgres://") || strings.HasPrefix(cfg.DatabaseURL, "postgresql://")`.
  - DoD: integration test with a Postgres DSN confirms that a pending-auth
    entry issued by one `oauth.Server` instance can be consumed by a freshly
    constructed instance sharing the same DB; `go test ./internal/oauth/...`
    passes for both SQLite (in-memory path) and Postgres (DB path).

- [ ] 9. Add `OAuthPendingAuthSize` metric and wire into `oauth.Server` (depends on 8)
  - In `internal/metrics/metrics.go`: add `OAuthPendingAuthSize prometheus.Gauge`.
  - Add `WithMetrics(m *metrics.Registry) *Server` to `oauth.Server` (mirror
    `ClientPool.WithMetrics`).
  - In the sweeper goroutine inside `oauth.Server.StartSweeper`, after each sweep
    tick sample: when `useDB`, query `SELECT COUNT(*) FROM oauth_pending_auth`;
    when in-memory, read `len(s.pending)`. Set the gauge.
  - In `cmd/server/main.go`: call `srv.WithMetrics(m)` after `oauth.New()`.
  - DoD: `/metrics` includes `mctl_oauth_pending_auth_size`.

- [ ] 10. Write `docs/hpa.md` (depends on 1, 2)
  - Run a micro-benchmark: start a pool with N sessions against a stubbed
    `SessionStore` (no real Telegram), measure `runtime.ReadMemStats` delta.
  - Document: measured RSS per idle session, recommended
    `TELEGRAM_MAX_SESSIONS` per pod memory tier, HPA YAML example targeting
    `mctl_telegram_client_pool_size / mctl_telegram_pool_capacity >= 0.7`.
  - DoD: file exists at `docs/hpa.md`, reviewed and merged.

---

## Tests

- [ ] T1. `internal/telegram/clientpool_test.go`: add `TestPoolFull` — create a
  pool with `MaxSessions=2`, acquire two entries, verify the third `Borrow`
  returns `ErrPoolFull`, verify the error count is not incremented (it is not
  a client error).

- [ ] T2. `internal/telegram/floodwait_test.go`: unit tests for
  `FloodWaitSeconds` covering nil, wrapped, `FLOOD_WAIT_0`, `FLOOD_WAIT_30`,
  `FLOOD_WAIT_86400`, and a non-flood tgerr (PEER_ID_INVALID).

- [ ] T3. `internal/mcp/tools_test.go`: add a test injecting a stub pool that
  returns `FLOOD_WAIT_1` for the first two calls then succeeds; verify
  `borrowWithRetry` retries correctly and increments the FloodWait counter
  twice; verify total tool latency is >= 2 seconds in the stub.

- [ ] T4. `internal/mcp/tools_test.go`: verify that when a pool returns
  `FLOOD_WAIT_1` and the context is already cancelled, `borrowWithRetry`
  returns `ctx.Err()` immediately without sleeping.

- [ ] T5. `internal/db/store_oauth_test.go`: table-driven tests for
  `InsertOAuthPending` / `ConsumeOAuthPending` with expired TTL (expect
  `ErrNotFound`), `ConsumeOAuthCode` single-use (second consume returns
  `ErrNotFound`), `InsertClientReg` / `GetClientReg`.

- [ ] T6. `internal/oauth/server_chi_test.go` (or a new Postgres integration
  test): end-to-end OAuth flow with `UseDBForOAuth=true`; verify that
  constructing a second `oauth.Server` on the same DB can redeem a code issued
  by the first.

- [ ] T7. Confirm `go vet ./...` and `golangci-lint run` pass on all changed
  packages.

---

## Rollback

**Tasks 1-5 (pool cap + FloodWait):** purely additive to the pool and MCP
layer. Rollback by reverting the three commits (pool change, metrics change,
borrowWithRetry change). No DB migration is involved. Setting
`TELEGRAM_MAX_SESSIONS=0` (default) disables the cap at runtime without a
deploy.

**Tasks 6-9 (OAuth persistence):** the new Postgres tables are created with
`IF NOT EXISTS` and are only written when `UseDBForOAuth=true` (requires
`DATABASE_URL=postgres://...`). Rolling back means:
1. Deploy the previous image (reverts `useDB=true` to in-memory maps).
2. The three new tables can be dropped at operator discretion; they contain
   only transient state (TTL <= 10 min) so no user-visible data is lost.
3. Existing tables (`oauth_refresh_tokens`, `telegram_accounts`, `users`) are
   untouched.

**Task 10 (docs):** documentation-only; no rollback needed.

In all cases, `TELEGRAM_MAX_SESSIONS` can be unset or set to 0 to revert pool
cap behavior immediately without a redeploy.
