# Design: issue-66-scalability-audit-and-hardening-for-100

## Current state

### MTProto client pool (internal/telegram/clientpool.go)

`ClientPool` is a `sync.Mutex`-guarded `map[int64]*entry`. Each user gets one
`entry` on their first `Borrow()` call via `acquire()`. An entry owns:

- a `*telegram.Client` (gotd), which maintains a persistent TCP connection to
  a Telegram data center
- a goroutine running `client.Run(ctx, ...)` (the `run` method)
- a GC goroutine (`gc`) that cancels the entry after `IdleTimeout` of inactivity
  (default: `IDLE_CLIENT_TIMEOUT=10m`)

`acquire()` has no capacity check. At 100 concurrent users the pool holds 100
live entries: 100 TCP connections, 200 goroutines, and however much heap gotd
allocates per client. No `TELEGRAM_MAX_SESSIONS` exists anywhere in
`internal/config/config.go` or `NewClientPool`.

`Pool.Borrow()` already returns raw errors from `fn(ctx, c)`. A
`FLOOD_WAIT_X` error (MTProto code 420) is tested in
`clientpool_test.go` only to confirm it is not a session-auth error; it passes
back to the tool handler unchanged. `tgerr.Is(err, "FLOOD_WAIT_30")` would
match but no retry logic exists.

The `metrics.Registry` is already wired: `TelegramClientPoolSize` (gauge)
increments/decrements in `acquire()` and `run()`. There is no capacity gauge
or FloodWait counter.

### OAuth server (internal/oauth/server.go)

`Server` holds four `sync.Mutex`-guarded maps:

| field     | type                         | max cap default |
|-----------|------------------------------|-----------------|
| `pending` | `map[string]*pendingAuth`    | 5 000           |
| `codes`   | `map[string]*authCode`       | 10 000          |
| `clients` | `map[string]*clientReg`      | 1 000           |
| `enables` | `map[string]*enableSession`  | 256             |

All four are in-process; a pod restart or rolling deploy loses any in-flight
authorization flow. Each map already applies oldest-evict on overflow and TTL
sweeps every minute via `StartSweeper`. The package-level doc comment
explicitly acknowledges this limitation and defers resolution.

Refresh tokens and session blobs are already persisted via
`internal/db/store.go`; only the transient OAuth flow state is in-memory.

### Database (internal/db/db.go)

`db.Open()` selects `modernc/sqlite` for all DSNs except `postgres://`. SQLite
is configured `SetMaxOpenConns(1)` — a single write connection. The WAL journal
mode (`_pragma=journal_mode(WAL)`) and `busy_timeout(5000)` reduce contention
but do not eliminate it under concurrent tool calls. Postgres uses 10 open
connections, 2 idle.

### FloodWait (no mitigation today)

`internal/telegram/send.go` (`SendMessage`), `messages.go`
(`GetUnreadMessages`, `GetMessages`), `dialogs.go` (`ListDialogs`), and
`pin.go` (`PinMessage`) all call MTProto API methods and propagate errors
unchanged. The MCP tool handlers in `internal/mcp/tools.go` pass these to
`borrowErrResult()`, which handles session-auth sentinels but not FloodWait.
An LLM making rapid successive `list_dialogs` or `get_messages` calls will
receive raw `FLOOD_WAIT_X` errors repeatedly.

---

## Proposed solution

### Change 1: TELEGRAM_MAX_SESSIONS cap on ClientPool

**Files:** `internal/telegram/clientpool.go`, `internal/config/config.go`,
`internal/metrics/metrics.go`, `cmd/server/main.go`

Add `MaxSessions int` to `ClientPool`. When non-zero, `acquire()` checks
`len(p.entries) >= p.MaxSessions` before allocating a new entry and returns a
new sentinel `ErrPoolFull` error if at capacity.

```
// internal/telegram/clientpool.go (additions)
var ErrPoolFull = errors.New("telegram: session pool at capacity")

// in acquire(), after the early-return for existing live entry:
if p.MaxSessions > 0 && len(p.entries) >= p.MaxSessions {
    return nil, ErrPoolFull
}
```

`ErrPoolFull` flows up through `Borrow()` to `borrowErrResult()` in
`internal/mcp/tools.go`, which gains a new case:

```
case errors.Is(err, telegram.ErrPoolFull):
    return mcplib.NewToolResultError(
        "server at session capacity — try again later"), nil
```

`internal/config/config.go` adds:

```
TelegramMaxSessions int // TELEGRAM_MAX_SESSIONS, 0 = no cap
```

`cmd/server/main.go` passes the value:

```
pool := telegram.NewClientPool(...).
    WithMaxSessions(cfg.TelegramMaxSessions).
    WithMetrics(m)
```

`internal/metrics/metrics.go` adds:

```
TelegramPoolCapacity prometheus.Gauge  // mctl_telegram_pool_capacity
```

Set once at startup to `cfg.TelegramMaxSessions` (or -1 if uncapped). This
lets a Prometheus expression `pool_size / pool_capacity` drive HPA.

Recommended default for a 512 MiB pod: `TELEGRAM_MAX_SESSIONS=150` (leaves
~30% headroom for HTTP workers and Prometheus). Document measured memory
footprint in `docs/hpa.md` (see Change 5).

### Change 2: FloodWait transparent retry

**Files:** `internal/telegram/floodwait.go` (new), `internal/mcp/tools.go`,
`internal/metrics/metrics.go`

Add a new file `internal/telegram/floodwait.go` with a utility function that
parses the wait duration from a FLOOD_WAIT MTProto error:

```
// floodWaitSeconds returns the seconds encoded in a FLOOD_WAIT_X error,
// or 0 if err is not a FloodWait error. Uses tgerr to unwrap MTProto errors.
func floodWaitSeconds(err error) int {
    var te *tgerr.Error
    if !errors.As(err, &te) || te.Code != 420 {
        return 0
    }
    // Message is "FLOOD_WAIT_X" where X is an integer.
    msg := te.Message
    const prefix = "FLOOD_WAIT_"
    if !strings.HasPrefix(msg, prefix) {
        return 0
    }
    n, err := strconv.Atoi(msg[len(prefix):])
    if err != nil {
        return 0
    }
    return n
}
```

In `internal/mcp/tools.go`, replace the direct `s.Pool.Borrow(ctx, ...)` calls
in every tool handler with a `borrowWithRetry` helper:

```
// borrowWithRetry wraps Pool.Borrow with up to maxFloodWaitRetries transparent
// retries when Telegram returns FLOOD_WAIT_X. The wait is capped at
// maxFloodWaitSleep to avoid holding up request goroutines indefinitely.
const maxFloodWaitRetries = 3
const maxFloodWaitSleep = 60 * time.Second

func (s *Server) borrowWithRetry(
    ctx context.Context,
    tool string,
    userID int64,
    fn func(context.Context, *gotdtelegram.Client) error,
) error {
    var lastErr error
    for attempt := 0; attempt <= maxFloodWaitRetries; attempt++ {
        lastErr = s.Pool.Borrow(ctx, userID, fn)
        wait := telegram.FloodWaitSeconds(lastErr)
        if wait == 0 {
            return lastErr // not a FloodWait error, return immediately
        }
        if s.Metrics != nil {
            s.Metrics.TelegramFloodWaitEventsTotal.WithLabelValues(tool).Inc()
        }
        if attempt == maxFloodWaitRetries {
            break
        }
        sleep := time.Duration(wait) * time.Second
        if sleep > maxFloodWaitSleep {
            sleep = maxFloodWaitSleep
        }
        select {
        case <-ctx.Done():
            return ctx.Err()
        case <-time.After(sleep):
        }
    }
    return lastErr
}
```

`borrowErrResult` gains a FloodWait case that surfaces the retry delay to the
LLM:

```
case telegram.FloodWaitSeconds(err) > 0:
    secs := telegram.FloodWaitSeconds(err)
    return mcplib.NewToolResultError(
        fmt.Sprintf("Telegram rate limit (FLOOD_WAIT_%d): retry after %d seconds", secs, secs)), nil
```

`internal/metrics/metrics.go` adds:

```
TelegramFloodWaitEventsTotal *prometheus.CounterVec
// labeled by tool
```

All tool handlers in `internal/mcp/tools.go` that currently call
`s.Pool.Borrow(...)` switch to `s.borrowWithRetry(ctx, "<tool_name>", ...)`.

### Change 3: Persist OAuth pending-auth and authorization codes to Postgres

**Files:** `internal/db/db.go` (schema), `internal/db/store.go` (new methods),
`internal/oauth/server.go`, `internal/config/config.go`, `cmd/server/main.go`

This change is scoped to `pending` and `codes` maps. The `enables` map (active
goroutine state) is deferred (see Out of scope in requirements).

**Schema additions** (Postgres only; SQLite keeps in-memory maps):

```sql
CREATE TABLE IF NOT EXISTS oauth_pending_auth (
    state         TEXT PRIMARY KEY,
    client_id     TEXT NOT NULL,
    redirect_uri  TEXT NOT NULL,
    client_state  TEXT NOT NULL DEFAULT '',
    code_challenge      TEXT NOT NULL,
    challenge_method    TEXT NOT NULL DEFAULT 'S256',
    scope         TEXT NOT NULL DEFAULT '',
    nonce         TEXT NOT NULL,
    tg_code_verifier    TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS oauth_auth_codes (
    code                TEXT PRIMARY KEY,
    client_id           TEXT NOT NULL,
    redirect_uri        TEXT NOT NULL,
    code_challenge      TEXT NOT NULL,
    challenge_method    TEXT NOT NULL DEFAULT 'S256',
    telegram_id         BIGINT NOT NULL,
    telegram_username   TEXT NOT NULL DEFAULT '',
    scope               TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS oauth_client_registrations (
    client_id     TEXT PRIMARY KEY,
    client_name   TEXT NOT NULL DEFAULT '',
    redirect_uris TEXT NOT NULL,   -- JSON array
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Add corresponding `Store` methods to `internal/db/store.go`:
- `InsertOAuthPending(ctx, state string, p *oauth.PendingAuth) error`
- `ConsumeOAuthPending(ctx, state string) (*oauth.PendingAuth, error)` — deletes and returns
- `InsertOAuthCode(ctx, code string, c *oauth.AuthCode) error`
- `ConsumeOAuthCode(ctx, code string) (*oauth.AuthCode, error)` — deletes and returns
- `InsertClientReg(ctx, reg *oauth.ClientReg) error`
- `GetClientReg(ctx, clientID string) (*oauth.ClientReg, error)`
- `DeleteExpiredOAuthCodes(ctx, ttl time.Duration) error` — for sweeper

`oauth.Server` gains a `useDB bool` field set at construction time. When true,
`handleAuthorize`, `issueAuthCode`, `handleTelegramCallback`, and
`handleTokenAuthCode` route through the DB methods; when false the existing
map logic runs unchanged. The in-memory sweeper still runs (for `enables`
and as a safety net when `useDB` is false).

`cmd/server/main.go` passes `UseDBForOAuth: strings.HasPrefix(cfg.DatabaseURL, "postgres")` to `oauth.New()` (or equivalent `Config` field).

**TTL enforcement on read**: both `ConsumeOAuthPending` and `ConsumeOAuthCode`
compare `created_at + ttl` against `NOW()` and return `db.ErrNotFound` if
expired, mirroring the in-memory defensive TTL check already present in
`handleTelegramCallback` and `handleTokenAuthCode`.

### Change 4: Metrics additions

**File:** `internal/metrics/metrics.go`

New fields:

```
TelegramFloodWaitEventsTotal *prometheus.CounterVec
// Name: mctl_telegram_flood_wait_events_total
// Labels: tool

TelegramPoolCapacity prometheus.Gauge
// Name: mctl_telegram_pool_capacity
// Help: Configured TELEGRAM_MAX_SESSIONS value; -1 when uncapped.

OAuthPendingAuthSize prometheus.Gauge
// Name: mctl_oauth_pending_auth_size
// Help: Current count of pending OAuth authorization flows.
```

`OAuthPendingAuthSize` is sampled by `oauth.Server` from the same goroutine
that already refreshes `mctl_sessions_active` (or an equivalent per-minute
tick injected via `WithMetrics` on the oauth.Server — mirror the pattern in
`ClientPool.WithMetrics`).

### Change 5: HPA documentation

**File:** `docs/hpa.md` (new, committed to the repo)

Content outline:
- Per-session memory estimate: procedure using `runtime.ReadMemStats` before
  and after loading N sessions; target measurement is 3-5 MB per idle client
  (auth key blob + DC connection + two goroutines at default stack size).
- Recommended `TELEGRAM_MAX_SESSIONS` table vs pod memory limit (256 MiB, 512
  MiB, 1 GiB).
- Kubernetes HPA stanza targeting the custom metric
  `mctl_telegram_client_pool_size / mctl_telegram_pool_capacity`, scale at 70%.
- Note: HPA requires the Prometheus Adapter to expose the custom metric; link
  to the mctl-gitops kustomize base.

---

## Alternatives

### A. Redis for OAuth state instead of Postgres

Redis is the conventional choice for transient session state (TTL on keys,
atomic operations). However, mctl-telegram already has a full Postgres schema
with migrations, and adding a second stateful dependency (Redis) to a service
that currently needs zero external dependencies in local-dev is a significant
operational burden. The Postgres option is strictly simpler given the existing
`db.Store` abstraction.

### B. Retry FloodWait inside Pool.Borrow rather than at the tool layer

Embedding retry logic in `Pool.Borrow` would centralize the behavior, but it
couples the MTProto connection pool to tool-call semantics (retry counts,
sleep caps). The pool's current contract is deliberately simple: connect, run,
propagate errors. A caller-level wrapper (`borrowWithRetry`) keeps concerns
separated and makes the retry policy visible to the code reading the tool
handler, which is where operators are most likely to tune it.

### C. Delay the OAuth persistence change until a second replica is actually
needed

The in-memory maps already have hard caps and oldest-evict, so they are safe
for a single replica. However, deferring the change means operators cannot do
a rolling deploy (the pod that comes up fresh cannot redeem codes issued by the
pod that went down). The DB change is low-risk (additive schema, guarded behind
a `useDB` flag) and unblocks zero-downtime deploys even before a second replica
is added.

---

## Platform impact

### Migrations

Three new tables are added to the Postgres schema in `db.go` (`pgSchema()`):
`oauth_pending_auth`, `oauth_auth_codes`, `oauth_client_registrations`. All use
`CREATE TABLE IF NOT EXISTS`, making them idempotent. SQLite schema is unchanged.

Rollback: the new tables can be dropped without touching existing data. The
`useDB` flag means the service falls back to in-memory maps if the DB write
fails at construction time.

### Backward compatibility

- `TELEGRAM_MAX_SESSIONS` defaults to 0 (no cap). Existing deployments are
  unaffected unless they opt in.
- `TelegramFloodWaitEventsTotal` and `TelegramPoolCapacity` are new Prometheus
  series; no existing dashboards break.
- `borrowWithRetry` replaces direct `Pool.Borrow` calls in tool handlers. The
  behavior is identical when no FloodWait occurs; retries are additive.

### Resource impact

- Each FloodWait retry holds an HTTP handler goroutine for up to 60 seconds.
  At 3 retries and a max sleep of 60 s, worst-case latency for one tool call
  is ~180 s. This is bounded by the existing `middleware.Timeout(60 * time.Second)`
  in `cmd/server/main.go` — the request context will be cancelled before the
  third sleep completes unless the timeout is raised. Open question 1 in
  requirements applies here: if the request timeout is shorter than the flood
  wait, context cancellation exits immediately via the `select` branch.

### Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| FloodWait sleep holds goroutine longer than HTTP timeout | Context cancellation path in `borrowWithRetry` exits cleanly; timeout can be tuned via `middleware.Timeout` |
| DB write failures block OAuth flows under Postgres downtime | `useDB=false` fallback to in-memory maps when DB is unavailable at startup; runtime DB errors are logged and returned as 500 so flow fails fast rather than silently |
| Pool cap starves legitimate users when cap is too low | Cap is configurable; metric `mctl_telegram_pool_capacity` lets operators tune it; cap-hit errors are surfaced in `mctl_tool_invocations_total{status="error"}` |
| Rolling deploy drops in-flight SQLite OAuth flows | Not fixed by this proposal (SQLite stays in-memory); only Postgres deployments gain cross-pod continuity |
