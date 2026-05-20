# Design: issue-90-beta-capacity-profile-load-test-tuned-co

## Current state

### DB pool sizing (internal/db/db.go:36-41)

`db.Open()` hardcodes Postgres connection pool limits:

```go
if isPg {
    dbConn.SetMaxOpenConns(10)
    dbConn.SetMaxIdleConns(2)
} else {
    dbConn.SetMaxOpenConns(1)
}
```

There is no runtime override. Under Beta load (approaching 470 concurrent
sessions, each triggering at least one DB read per tool call via
`Store.CheckSessionValid` and `Store.MarkLastUsed` in
`internal/telegram/clientpool.go:Borrow`), the 10-open-connection cap can
become the p95/p99 bottleneck before the Telegram pool or network does.

### Configuration (internal/config/config.go)

`config.Config` already exposes the following relevant fields (lines 21-55):
- `TelegramMaxSessions int` — read from `TELEGRAM_MAX_SESSIONS` via
  `envInt` (line 90)
- `IdleClientTimeout time.Duration` — `IDLE_CLIENT_TIMEOUT`, default 10m
  (line 73)
- `RateLimitPerUser int` — `RATE_LIMIT_PER_USER`, default 30 (line 74)
- `AuditRetentionDays int` — `AUDIT_RETENTION_DAYS`, default 90 (line 75)
- `OAUTHAccessTokenTTL time.Duration` — default 1h (line 83)
- `OAUTHRefreshTokenTTL time.Duration` — default 720h = 30 days (line 84)

DB pool fields are absent. The `envInt()` helper at line 175 makes adding
new integer fields a two-line change per field.

### Metrics already in place (internal/metrics/metrics.go)

`metrics.New()` already registers (lines 69-156):
- `mctl_tool_invocation_duration_seconds` histogram with buckets
  `[.05, .1, .25, .5, 1, 2.5, 5, 10]` — sufficient for p50/p95/p99
- `mctl_tool_invocations_total` counter labeled by tool and status
- `mctl_telegram_client_pool_size` gauge
- `mctl_telegram_pool_capacity` gauge (set to -1 when uncapped)
- `mctl_telegram_flood_wait_events_total` counter labeled by tool
- `mctl_sessions_active` gauge (refreshed every minute by main.go)

The prometheus/client_golang process collector auto-exports
`process_resident_memory_bytes` and `go_goroutines`. All load-test
reporting metrics can be derived from scraping the target's /metrics endpoint
plus in-process latency tracking in the test binary.

### Tool call paths

From `internal/mcp/tools.go`, the three tool categories in the mix are:

- `list_dialogs` (line 115): calls `s.borrowWithRetry` ->
  `telegram.ListDialogs()` — exercises Telegram pool + DB.
- `get_messages` (line 386): calls `s.borrowWithRetry` ->
  `telegram.GetMessages()` — exercises Telegram pool + DB; requires a non-
  empty peer argument.
- `prepare_send_message` (line 220): calls `s.Confirms.Issue()` — no
  Telegram pool involvement; exercises in-memory confirmation store and
  per-peer rate limiter.
- `send_message` with mode omitted (defaults to "draft") (line 285):
  `realSend` evaluates false; calls `telegram.SendMessage(ctx, nil, ...)` —
  no Telegram pool involvement. Together with prepare, exercises the
  confirmation token lifecycle and rate limiter only.

### Existing gaps

- `test/load/` does not exist.
- `deploy/profiles/` does not exist.
- `docs/hpa.md` covers 256 MiB, 512 MiB, and 1 GiB tiers but not 2 GiB.
- The HPA scale-out trigger (70% pool utilization) is not tied to a measured
  saturation point.

## Proposed solution

### 1. Config: expose DB pool sizing

Add two fields to `config.Config` in `internal/config/config.go`:

```go
// DBMaxOpenConns caps the Postgres connection pool. 0 means use the
// driver default (10). Set via DB_MAX_OPEN_CONNS.
DBMaxOpenConns int
// DBMaxIdleConns sets the Postgres idle connection count. 0 means use
// the driver default (2). Set via DB_MAX_IDLE_CONNS.
DBMaxIdleConns int
```

Wire them in `Load()` after the existing `TelegramMaxSessions` line (line 90):

```go
c.DBMaxOpenConns = envInt("DB_MAX_OPEN_CONNS", 0)
c.DBMaxIdleConns = envInt("DB_MAX_IDLE_CONNS", 0)
```

Update `db.Open()` to accept the two values as additional parameters:

```go
func Open(ctx context.Context, dsn string, maxOpenConns, maxIdleConns int) (*sql.DB, error)
```

In the Postgres branch, replace the hardcoded values with:

```go
if isPg {
    open := 10
    if maxOpenConns > 0 {
        open = maxOpenConns
    }
    idle := 2
    if maxIdleConns > 0 {
        idle = maxIdleConns
    }
    dbConn.SetMaxOpenConns(open)
    dbConn.SetMaxIdleConns(idle)
} else {
    dbConn.SetMaxOpenConns(1)
}
```

Update the single production call site in `cmd/server/main.go` (line 61):

```go
rawDB, err := db.Open(ctx, cfg.DatabaseURL, cfg.DBMaxOpenConns, cfg.DBMaxIdleConns)
```

No changes to `db.Migrate`, `db.Store`, or any other caller.

### 2. test/load/ package

Create `test/load/main.go` as a standalone binary
(`package main`, build path `github.com/mctlhq/mctl-telegram/test/load`)
so it compiles with `go build ./test/load/` and runs without `go test`
scaffolding.

**Flags:**

| Flag | Type | Description |
|------|------|-------------|
| `-users` | int | Number of concurrent virtual users (default 100) |
| `-ramp` | duration | Linear ramp duration (default 2m) |
| `-hold` | duration | Sustained-load hold duration (default 10m) |
| `-target` | string | Base URL of the staging deployment |
| `-tokens` | string | Path to a newline-delimited file of bearer tokens, one per virtual user |
| `-peer` | string | Telegram peer string for get_messages calls (e.g. "@canary") |
| `-out` | string | Path for JSON results file (default "results.json") |

**Virtual user goroutine:**

Each goroutine: picks the next tool using weighted random (seed from
`crypto/rand` to avoid correlated goroutines); builds the HTTP request
with `Authorization: Bearer <token>`; sends it to `<target>/mcp` as an
MCP JSON-RPC call; records the outcome (latency, error flag) in the shared
result store. Between calls the goroutine sleeps for a configurable inter-
call jitter (0-500 ms, uniform random) to avoid synchronized thundering herds.

The dry-run send sequence:
1. Call `prepare_send_message` with `peer=<peer>` and `text="load test dry run"`.
2. Extract `confirmation_id` from the response JSON.
3. Call `send_message` with `peer=<peer>`, `text="load test dry run"`,
   `confirmation_id=<id>` and no `mode` field (defaults to "draft" on the
   server). This does not invoke the Telegram pool.

**Result store:**

A mutex-protected struct accumulates per-tool: call count, error count, and
a sorted latency slice for percentile computation. At report time, p50, p95,
and p99 are computed from the sorted slice using linear interpolation.

**Metrics poller:**

A separate goroutine issues HTTP GET `<target>/metrics` every 5 seconds,
parses the Prometheus text format using
`github.com/prometheus/client_model/go` (already an indirect dependency in
go.sum), and maintains running maximums for:
- `mctl_telegram_client_pool_size`
- `mctl_sessions_active`
- `process_resident_memory_bytes`
- `go_goroutines`
- `mctl_telegram_flood_wait_events_total{tool="list_dialogs"}` etc.

**Ramp:**

Start one goroutine every `ramp / N` interval. A ticker drives this; the
main goroutine blocks until N goroutines are running, then starts the hold
timer. This is simpler than a token-bucket and sufficient for staging tests.

**Final report:**

Written to stdout as Markdown tables (human-readable for copy-paste into
`docs/load-test-beta.md`) and to `-out` as JSON (machine-readable for
tracking results across runs).

### 3. docs/load-test-beta.md

A new file committed after running the test. Sections:
- **Test environment**: pod memory limit, Postgres version,
  TELEGRAM_MAX_SESSIONS, DB_MAX_OPEN_CONNS, DB_MAX_IDLE_CONNS, token count,
  target peer, test binary version (git SHA).
- **Saturation point table**: sessions at which p99 latency exceeds the
  SLO threshold or error rate exceeds 1%, for each pod size.
- **Memory growth curve**: RSS vs concurrent-session count as a table;
  annotated with the 3 MB/session planning figure from `docs/hpa.md` for
  comparison.
- **DB connection pool pressure**: max in-use and max idle connections
  observed over the hold phase; derived from `pg_stat_activity` or from
  `db.Stats()` if the load test exposes a /debug endpoint.
- **FLOOD_WAIT events**: total count per tool for the hold phase.
- **Recommendations**: confirmed TELEGRAM_MAX_SESSIONS per pod tier,
  DB pool settings, and scale-out threshold for docs/hpa.md.

### 4. deploy/profiles/beta.env

Initial values (annotated; to be updated after load test):

```
# Beta deployment profile for mctl-telegram.
# Values marked "estimate" must be confirmed against docs/load-test-beta.md
# before this profile is referenced in a production deployment.

# 2 GiB pod: ~478 sessions from hpa.md formula (2048*0.7/3); rounded to 470.
# CONFIRM after load test. [estimate]
TELEGRAM_MAX_SESSIONS=470

# Default 10m preserved; shorter values free pool entries faster under
# capacity pressure but increase reconnect overhead.
IDLE_CLIENT_TIMEOUT=10m

# Double the Pilot default (30); adjust down if 429 rate in load test exceeds
# the #88 SLO error budget. [estimate]
RATE_LIMIT_PER_USER=60

# Postgres pool: raised from hardcoded 10/2 to handle concurrent DB ops
# from ~470 sessions. Requires Postgres max_connections >= 50.
DB_MAX_OPEN_CONNS=25
DB_MAX_IDLE_CONNS=5

# Token TTLs: keep defaults for Beta; revisit if refresh-token table growth
# becomes significant at 1K-user scale.
OAUTH_ACCESS_TOKEN_TTL=1h
OAUTH_REFRESH_TOKEN_TTL=720h

# Reduced from 90-day default to bound audit table growth at Beta scale
# (~1K users, multiple tool calls per session per day). Revisit against
# any compliance requirements before GA.
AUDIT_RETENTION_DAYS=30
```

### 5. docs/hpa.md update

Append the 2 GiB row to the capacity table:

| Pod memory limit | Usable for sessions | Recommended TELEGRAM_MAX_SESSIONS |
|-----------------|---------------------|----------------------------------|
| 2 GiB | ~1430 MB | TBD (update after load test) |

Add a "Beta scale-out guidance" section documenting:
- The confirmed saturation point from `docs/load-test-beta.md`
- The 70% pool-utilization HPA trigger from the existing stanza
- The SLO reference from issue #88
- Recommendation: minReplicas=2 for Beta to avoid cold-start latency spikes

## Alternatives

### A. Use an existing HTTP load tool (k6, vegeta, or hey)

k6 supports JavaScript scripting and has native Prometheus output. hey and
vegeta are simpler but stateless.

**Dropped.** The dry-run send sequence requires request chaining: the
`prepare_send_message` response carries a `confirmation_id` that the
subsequent `send_message` call must echo. Stateless tools (vegeta, hey)
cannot express this. k6 can script it in JavaScript, but the MCP JSON-RPC
framing and the per-tool latency split require non-trivial JavaScript that
is harder to review and maintain than idiomatic Go. The Go binary also
compiles with the same `go build` chain as the rest of the repo and can
share the Prometheus text parser already present in go.sum.

### B. Go benchmark functions (BenchmarkXxx in a _test.go file)

`go test -bench` integrates with benchstat for statistical comparison across
runs and produces output parseable without a custom report step.

**Dropped.** The benchmark lifecycle creates a fresh test binary on each run
and the HTTP test server shuts down between sub-benchmarks, making it
impossible to observe pool memory growth over a sustained hold phase. The
ramp-up pattern (start one goroutine every N ms) is also not expressible
in `b.RunParallel`. The hold phase and peak-RSS measurement require a
long-running external server, which is incompatible with standard benchmark
semantics.

### C. In-process load test (call internal functions directly)

Bypass HTTP/auth/rate-limiter and call `mcp.Server.toolListDialogs()` and
similar handlers directly from the test binary using the same process.

**Dropped.** This bypasses the complete production request path: HTTP parse,
auth middleware, rate limiter, MCP JSON-RPC dispatch. Latency numbers would
not reflect production behavior. RSS measurements would include test-binary
heap mixed with server heap, making the memory growth curve unreliable. The
primary value of the load test is measuring the end-to-end production path
including DB and Telegram connection pool behavior under real HTTP load.

## Platform impact

### Migrations

None. The `beta.env` and load test package are additive. The `db.Open`
signature change is internal; `cmd/server/main.go` is the only production
caller, and the change is backward compatible via the 0-as-default sentinel.

### Backward compatibility

All deployments that do not set `DB_MAX_OPEN_CONNS` or `DB_MAX_IDLE_CONNS`
continue to receive the current hardcoded defaults (10/2 for Postgres).
The `config.Load()` change is purely additive.

### Resource impact

The load test binary runs against the staging cluster as an external HTTP
client; it has no runtime impact on production. Raising DB_MAX_OPEN_CONNS
from 10 to 25 in the Beta profile increases Postgres connection overhead
slightly; at 25 connections this is negligible for a Postgres instance with
the default `max_connections=100`.

### Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Load test exhausts canary Telegram rate quota, triggering FLOOD_WAIT backpressure | Cap inter-call jitter so each virtual user issues at most ~6 calls/min, well below the 30/min default RATE_LIMIT_PER_USER |
| Bearer tokens expire before the hold phase ends | Set OAUTH_ACCESS_TOKEN_TTL long enough for the test duration, or pre-generate tokens with longer TTL; document in the test README |
| beta.env committed with estimate values before the load test runs | beta.env comments mark all estimates explicitly; a CI lint check can grep for the string "estimate" and warn on any deployment manifest that references beta.env without a companion docs/load-test-beta.md commit |
| DB_MAX_OPEN_CONNS=25 exceeds Postgres max_connections in staging | Document in beta.env comments that the Postgres instance must have max_connections >= 50; load test operator verifies before the run |
| Pool saturation point at 2 GiB lower than 470 (measured vs. extrapolated) | beta.env placeholder is clearly marked; the gitops promotion pipeline must require a manual sign-off that docs/load-test-beta.md confirms the values |
