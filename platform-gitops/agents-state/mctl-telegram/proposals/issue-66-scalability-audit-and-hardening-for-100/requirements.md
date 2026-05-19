# Scalability audit and hardening for 100+ concurrent users

## Context

mctl-telegram is currently deployed as a single replica. Four independent
components block horizontal scaling or degrade under load when concurrent user
counts grow beyond a handful:

1. The OAuth authorization server (`internal/oauth/server.go`) stores all
   transient state (pending PKCE flows, issued authorization codes, dynamic
   client registrations, in-progress enable-access sessions) in process-local
   `sync.Mutex`-guarded maps. The package-level doc comment explicitly notes
   that scale-out "would need to externalise the code store to Redis or
   Postgres." A pod restart loses all in-flight authorization flows.

2. The MTProto client pool (`internal/telegram/clientpool.go`) allocates one
   goroutine-backed `gotd/td` client per user with no ceiling. At 100 users,
   each holding a persistent DC TCP connection and in-memory auth-key material,
   this is an unbounded resource. No `TELEGRAM_MAX_SESSIONS` knob exists in
   `internal/config/config.go`.

3. Telegram's server-side rate limiter returns `FLOOD_WAIT_X` (HTTP 420, MTProto
   error code) when calls arrive too fast. Every MCP tool handler calls
   `Pool.Borrow()` and returns the raw error to the caller. An LLM in a tight
   loop will hit this repeatedly, risking a temporary user ban. No retry or
   back-off exists in any of `internal/telegram/send.go`,
   `internal/telegram/messages.go`, or `internal/telegram/dialogs.go`.

4. The default `DATABASE_URL` in `internal/config/config.go` points at SQLite
   with `MaxOpenConns(1)` (a single writer). Concurrent audit writes, session
   updates, and tool-call logging all contend on this one connection.

This proposal addresses all four failure modes plus adds the metrics and HPA
documentation asked for in the issue.

## User stories

- AS an operator I WANT a `TELEGRAM_MAX_SESSIONS` environment variable SO THAT
  I can cap per-replica MTProto connection count and right-size my Kubernetes
  resource requests before sessions exhaust file descriptors or RAM.

- AS an MCP client (LLM agent) I WANT FloodWait errors to be retried
  transparently SO THAT rapid tool calls do not result in raw 420 errors that
  produce unhelpful LLM outputs or trigger Telegram bans.

- AS an operator running multiple replicas I WANT OAuth pending-auth and
  authorization-code state persisted to Postgres SO THAT a pod restart or
  rolling deploy does not strand users mid-authorization-flow.

- AS an operator I WANT `/metrics` to include `mctl_telegram_flood_wait_events_total`
  and `mctl_oauth_pending_auth_size` SO THAT I can alert on flood-wait pressure
  and OAuth state growth without log-scraping.

- AS an operator planning Kubernetes HPA I WANT documented per-replica session
  capacity numbers and recommended HPA target metrics SO THAT I can configure
  autoscaling with a safety margin.

## Acceptance criteria (EARS)

### Session cap

- WHEN `TELEGRAM_MAX_SESSIONS` is set and the MTProto pool already holds that
  many live entries, THE SYSTEM SHALL return a tool error with the text
  "server at session capacity — try again later" rather than allocating a new
  client.

- WHILE `TELEGRAM_MAX_SESSIONS` is set, THE SYSTEM SHALL expose
  `mctl_telegram_pool_capacity` as a Prometheus gauge equal to the configured
  value, allowing HPA to track `pool_size / pool_capacity`.

- IF `TELEGRAM_MAX_SESSIONS` is not set or is set to 0 THE SYSTEM SHALL impose
  no additional cap (preserving current behavior).

### FloodWait backoff

- WHEN a `Pool.Borrow()` call returns a `FLOOD_WAIT_X` MTProto error THE SYSTEM
  SHALL wait X seconds (capped at 60 seconds) and retry the same call up to
  three times before returning the error to the tool handler.

- WHEN all retries are exhausted due to FloodWait THE SYSTEM SHALL return a tool
  error result that includes a `retry_after_seconds` field equal to the most
  recent wait duration, and SHALL increment
  `mctl_telegram_flood_wait_events_total{tool="<name>"}`.

- WHILE a FloodWait sleep is in progress THE SYSTEM SHALL respect context
  cancellation (i.e., return `ctx.Err()` immediately if the request context is
  done).

- WHEN a FloodWait retry succeeds THE SYSTEM SHALL increment
  `mctl_telegram_flood_wait_events_total` regardless, so operators can observe
  total flood-wait pressure.

### OAuth state persistence

- WHEN a Postgres `DATABASE_URL` is configured and a user begins an OAuth
  authorization flow, THE SYSTEM SHALL persist the pending-auth entry to the
  `oauth_pending_auth` table rather than to the in-memory map.

- WHEN the `/oauth/telegram/callback` handler issues an authorization code,
  THE SYSTEM SHALL persist it to the `oauth_auth_codes` table.

- WHEN `/oauth/token` redeems an authorization code, THE SYSTEM SHALL delete the
  row from `oauth_auth_codes` atomically within the same DB transaction.

- WHEN an authorization code or pending-auth entry exceeds `CodeTTL`, THE SYSTEM
  SHALL consider it expired on read, regardless of whether the background
  sweeper has deleted the row yet.

- IF the database driver is SQLite THE SYSTEM SHALL continue to use the
  in-memory maps for pending-auth and codes (SQLite single-writer contention
  makes DB-backed OAuth worse there, not better).

- WHEN any replica reads or writes OAuth state, THE SYSTEM SHALL produce
  identical results to the current single-replica behavior with respect to
  PKCE verification, nonce binding, and code expiry.

### Dynamic client registrations

- WHEN Postgres is configured, THE SYSTEM SHALL store dynamic client
  registrations in a new `oauth_client_registrations` table, keyed by
  `client_id`, with `created_at` and `redirect_uris`.

- WHILE Postgres is configured, THE SYSTEM SHALL not use the in-memory
  `clients` map for validation (reads and writes go to the DB).

### Metrics additions

- WHEN the metrics registry is constructed, THE SYSTEM SHALL register
  `mctl_telegram_flood_wait_events_total` (counter, labeled by `tool`) and
  `mctl_telegram_pool_capacity` (gauge).

- WHEN the OAuth server is running, THE SYSTEM SHALL periodically (every minute)
  sample and expose `mctl_oauth_pending_auth_size` (gauge) reflecting the current
  count of pending-auth entries (DB row count when Postgres, map length when SQLite).

### HPA documentation

- WHEN `TELEGRAM_MAX_SESSIONS` is set to 200 (recommended default), THE SYSTEM
  SHALL log a startup INFO line with `max_sessions` so operators can confirm
  the value is wired.

- The `CONTRIBUTING.md` or a new `docs/hpa.md` SHALL document: estimated RAM
  per session (measured from a benchmark), recommended `TELEGRAM_MAX_SESSIONS`
  for a 512 MiB / 1 GiB pod, and a Kubernetes HPA stanza targeting
  `mctl_telegram_client_pool_size / mctl_telegram_pool_capacity >= 0.7`.

## Out of scope

- Externalizing the in-progress `enables` map (stateful goroutines driving the
  phone-to-2FA login flow). These sessions are short-lived (bounded by
  `CodeTTL`, default 10 minutes) and contain live channels that cannot be
  serialized. Cross-replica continuity of an in-progress enable-access flow
  is explicitly deferred.

- Redis as a state backend. Postgres is already supported and is the production
  database. Adding a Redis dependency is not justified at this scale.

- Telegram DC selection or DC proxy configuration for geographic distribution.

- Replacing SQLite with Postgres in non-production (local-dev) deployments.

- Automatic account banning detection or adaptive back-off beyond the per-call
  FloodWait retry.

## Open questions

1. **FloodWait retry placement**: retrying inside `Pool.Borrow()` vs. in a thin
   wrapper around `Borrow()` at the MCP tool layer. The pool is currently a
   pass-through for errors; adding retry logic there couples transport and
   business-logic concerns. The preferred interpretation here is a `borrowWithRetry`
   helper in `internal/mcp/tools.go` that wraps `Pool.Borrow()`, keeping the
   pool itself simple.

2. **SQLite toggle for OAuth persistence**: the spec says "if SQLite, use
   in-memory maps." This requires the `oauth.Server` to know which driver is
   active. The current `Config` struct has a `TGAPIID / TGAPIHash` but nothing
   about DB dialect. The simplest detection is to pass a `bool UseDBForOAuth`
   flag at construction time, set by `cmd/server/main.go` based on whether the
   DSN starts with `postgres://`.

3. **`mctl_oauth_pending_auth_size` gauge ownership**: the oauth.Server currently
   samples its map sizes. Wiring Prometheus into `oauth.Server` would mirror the
   pattern used in `ClientPool.WithMetrics()`. This is the recommended approach.

4. **`MaxSessions` enforcement behavior**: should a pool-full condition queue
   the request with a timeout, or fail immediately with a 503-class error? The
   proposal takes the fail-immediately approach (consistent with the existing
   idle-client eviction model), but a bounded queue with a short timeout could
   give better UX under brief bursts.
