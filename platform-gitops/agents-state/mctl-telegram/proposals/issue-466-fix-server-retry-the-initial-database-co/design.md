# Design: issue-466-fix-server-retry-the-initial-database-co

## Current state

`cmd/server/main.go` boots in a straight line with no recovery for early failures:

```go
ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
defer stop()

rawDB, err := db.Open(ctx, cfg.DatabaseURL, cfg.DBMaxOpenConns, cfg.DBMaxIdleConns)
if err != nil {
    slog.Error("db open", "err", err)
    os.Exit(1)
}
defer rawDB.Close()
if err := db.Migrate(ctx, rawDB, cfg.SessionTTLExemptTGIDs...); err != nil {
    slog.Error("db migrate", "err", err)
    os.Exit(1)
}
```
(`cmd/server/main.go:81-90`)

`db.Open` (`internal/db/db.go:26-49`) is dialect-agnostic: it picks `pgx` or `sqlite`
via `driverFor`, calls `sql.Open` (which does not itself dial anything — `database/sql`
opens lazily), then does exactly one `dbConn.PingContext(ctx)`. Any ping error is
wrapped (`fmt.Errorf("ping %s: %w", driver, err)`) and returned; `main` treats any
non-nil error the same way, fatally.

`ctx` is a `signal.NotifyContext`-derived context with no deadline of its own — it is
canceled only by `SIGINT`/`SIGTERM`, never by a timeout. `db.Open` does not set its own
timeout either, so today's single `PingContext` call blocks on `ctx` (i.e. effectively
until the OS-level TCP `connect` times out or a signal arrives), not on any
short-lived deadline.

`internal/db/db_test.go` (`TestOpenPool`) exercises `Open` directly against SQLite
in-memory DSNs and, when `TEST_DATABASE_URL` is set, a real Postgres DSN. It asserts on
`Open`'s success and on `db.Stats()` pool settings; it does not depend on `Open` failing
immediately on a bad DSN, so a retry loop is compatible with the existing tests
class: `Open` keeps its single-attempt contract and the new wrapper is a separate
function, so no existing test changes behavior. Tests of the wrapper itself drive the
injected attempt function rather than a real target, so they neither wait on a
deadline nor depend on timing.

There is repo precedent for a bounded, logged reconnect loop with backoff: the Local
Bridge daemon's `runDaemon` in `cmd/local/daemon.go:103-137` retries a lost websocket
connection with `backoff := reconnectBase` (2s) doubling up to `reconnectMax` (60s),
logs `slog.Warn("bridge connection lost, reconnecting", "err", err, "wait", backoff)`
on every attempt, and selects on `ctx.Done()` inside the wait so shutdown is prompt.
That is a live-connection reconnect loop (unbounded lifetime, resets backoff after a
long healthy session), which differs from what is needed here — a one-shot, bounded
*startup* wait — but its shape (loop + `select` on `time.After(interval)` /
`ctx.Done()` + per-attempt log line) is the right pattern to reuse.

## Proposed solution

Add a new bounded retry wrapper around the existing single-attempt connect-and-ping
logic in `internal/db/db.go`, and call it from `cmd/server/main.go` in place of the
current direct `db.Open` call.

Concretely:

1. Split `Open` into two parts, preserving today's exported signature and behavior
   for any other caller (including `internal/db/db_test.go`'s `TestOpenPool`, which
   expects immediate success/failure against SQLite/Postgres and pool-size
   assertions):
   - `Open(ctx, dsn, maxOpenConns, maxIdleConns) (*sql.DB, error)` stays exactly as it
     is today: one `sql.Open` + one `PingContext`, no retry. Existing callers and
     tests keep their current contract.
   - A new `OpenWithRetry(ctx, dsn, maxOpenConns, maxIdleConns, interval, timeout)
     (*sql.DB, error)` in `internal/db/db.go` (or a new `internal/db/retry.go` file,
     to keep `db.go` focused) polls by calling `Open` in a loop:
     - On success, return the `*sql.DB` immediately, logging
       `slog.Info("db reachable", "attempts", attempts)` (0 on the first successful
       try) so `reachable after 0 retries` / `reachable after N retries` are
       distinguishable per the issue's acceptance criterion.
     - On failure, log `slog.Warn("db not reachable yet, retrying", "err", err,
       "attempt", attempts, "wait", interval)` and wait on
       `select { case <-time.After(interval): case <-ctx.Done(): return nil, ctx.Err() }`
       so `SIGINT`/`SIGTERM` (already wired into `ctx` in `main`) aborts the wait
       immediately instead of finishing out the poll window.
     - Track elapsed time (or use a `context.WithTimeout(ctx, timeout)` derived
       context for the whole loop) so the loop gives up once `timeout` is exceeded,
       returning the last observed error wrapped with context (e.g.
       `fmt.Errorf("db not reachable after %s: %w", timeout, err)`).
   - Use a short fixed interval (2s) rather than exponential backoff: the evidence in
     the issue shows the netpol race resolves in ~600ms, so a fixed short interval
     recovers the common case almost as fast as a tight loop would, without the
     added complexity of backoff state for a wait that is bounded to a few minutes
     total. This deliberately differs from `cmd/local/daemon.go`'s exponential
     backoff, which exists for a long-lived reconnect loop where a persistent outage
     must not be hammered — that risk does not apply to a two-minute, then-fatal
     startup wait.

   - Branch on the DSN before entering the loop: when `driverFor(dsn)` reports a
     non-Postgres driver, call `Open` once and return its result unchanged. A `file:`
     DSN makes no network call, so there is no netpol race to absorb, and looping
     would convert an instant local-dev error into a wait until the deadline. See
     "Decided: SQLite is not retried" in requirements.md.
   - Make the per-attempt call injectable so the loop is testable without a real
     database: keep an unexported package-level `var openOnce = Open` (or an
     unexported `openWithRetry(ctx, ..., open func(...) (*sql.DB, error))` that
     `OpenWithRetry` calls with `Open`). Tests then drive attempt outcomes
     deterministically — fail N times, then succeed — instead of trying to
     manufacture a target that is unreachable and then reachable on a timer. This
     seam is the difference between a test that proves the loop retries and one that
     merely proves a happy path still works.

2. In `cmd/server/main.go`, replace the direct `db.Open` call with
   `db.OpenWithRetry(ctx, cfg.DatabaseURL, cfg.DBMaxOpenConns, cfg.DBMaxIdleConns,
   dbConnectRetryInterval, dbConnectRetryTimeout)`, where the interval/timeout are
   either package-level constants in `cmd/server/main.go` (2s / 2m, matching the
   "short interval" and "on the order of a few minutes" language in the issue) or
   sourced from `cfg` if new config fields are added (see Alternatives). On error
   (deadline reached or context canceled), keep today's exact handling:
   ```go
   if err != nil {
       slog.Error("db open", "err", err)
       os.Exit(1)
   }
   ```
   This preserves the issue's explicit requirement to keep `os.Exit(1)` for the
   terminal failure case — a database unreachable for the full window is still a real
   failure and must still crash the pod for the kubelet/ArgoCD health signal to
   reflect it.

3. No changes to `db.Migrate`, `crypto.New`, or anything after the connection
   succeeds — the issue's proposed fix and acceptance criteria are scoped to the
   connection step only.

4. No changes to `internal/config` are strictly required (constants suffice per the
   issue's own phrasing of "a few minutes" and "a short interval" as fixed
   guidance, not a tunable), but see Open Questions in requirements.md for exposing
   them as env vars later without a default-behavior change.

## Alternatives

1. **Raise the Kubernetes/Argo restart backoff or add a longer `initialDelaySeconds`
   to the readiness/liveness probes.** Rejected: the issue explicitly rules this out
   (see mctl-gitops#866) — a pod restart is faster than NetworkPolicy convergence, so
   retrying at the orchestration layer races and loses against exactly the delay it
   is meant to absorb. This would also do nothing for the `ERROR` log noise and
   `restartCount` metric the issue calls out as the actual cost.

2. **Add a Kubernetes `initContainer` that polls the database (e.g. with
   `pg_isready` or a netcat probe) before the main container starts.** Rejected: this
   moves the wait outside the Go process into a separate container image and
   GitOps-managed manifest, which is heavier than the fix the issue asks for ("the
   wait must happen inside a single attempt" of the existing process) and would not
   help local-dev/SQLite or non-Kubernetes runs. It also duplicates connection logic
   (DSN parsing, credentials) in a second place.

3. **Retry inside `db.Open` itself (mutate its existing signature/behavior) instead
   of adding a separate `OpenWithRetry`.** Rejected: `internal/db/db_test.go`'s
   `TestOpenPool` and any other direct caller currently expect `Open` to attempt
   exactly once and fail fast on a bad DSN (relevant for fast local test runs and any
   future caller that wants synchronous fail-fast semantics, e.g. a CLI tool).
   Changing `Open`'s contract in place would either slow down every existing test
   against an unreachable DSN by the new timeout or require every call site to pass
   through new retry parameters. A new `OpenWithRetry` wrapper keeps `Open` a
   reusable single-attempt primitive and adds the retry behavior only where it is
   needed (server startup).

4. **Exponential backoff (mirroring `cmd/local/daemon.go`'s `reconnectBase`/
   `reconnectMax`) instead of a fixed interval.** Considered and partially adopted
   in spirit (same loop/log/select-on-ctx.Done shape) but not the backoff curve
   itself: exponential backoff is designed for a connection that may stay down
   indefinitely, where hammering it is undesirable. The startup wait here is bounded
   to a few minutes total and the known failure mode resolves in under a second, so
   a fixed short interval reaches the good outcome faster in the common case and is
   simpler to reason about and test than a growing interval capped at a max.

## Platform impact

- **Migrations:** none. No schema change.
- **Backward compatibility:** `db.Open`'s existing signature and behavior are
  unchanged, so no other caller (tests, `cmd/login`, `cmd/local`, if they use it) is
  affected. `cmd/server/main.go` behavior is unchanged in the success-immediately and
  fail-after-deadline cases; the only observable change is that a transient early
  failure now gets a bounded chance to self-heal instead of an immediate exit.
- **Resource impact:** negligible. Worst case adds up to ~2 minutes to a server
  startup that would otherwise have failed and been restarted by Kubernetes anyway —
  net effect is fewer restarts, not slower steady-state operation. No new
  goroutines survive past `main`'s startup sequence; the retry loop runs
  synchronously before the HTTP server starts listening, so it does not change the
  shape of readiness/liveness probes (the pod is not yet marked ready during the
  wait, same as today's pre-listen startup work).
- **Observability:** the new `slog.Info`/`slog.Warn` lines during the wait replace
  what would have been an `ERROR db open` + restart-and-repeat cycle with a bounded
  set of non-`ERROR` log lines, directly addressing the issue's "noise in the logs at
  ERROR level for a condition that is not an error" complaint. The terminal-failure
  `ERROR` log line and `os.Exit(1)` are unchanged, so genuine outages remain visible
  identically to today (just after the bounded wait rather than immediately).
- **Risks + mitigations:**
  - *Risk:* a genuinely down database now takes up to the full timeout (e.g. 2
    minutes) to be reported as `ERROR`/exit, instead of immediately, slightly
    delaying the "the pod is crashlooping" signal during a real outage.
    *Mitigation:* the bound is deliberately kept short ("a few minutes" per the
    issue) and the per-attempt `Warn` logs during the wait already show a database
    that is failing, so on-call visibility via logs is not lost — only the terminal
    `ERROR`/restart is delayed. This trade-off is exactly what the issue asks for.
  - *Risk:* shutdown during the wait (`SIGINT`/`SIGTERM`, e.g. during a rolling
    deploy that immediately supersedes a still-starting pod) must not hang until the
    timeout. *Mitigation:* the wait's `select` includes `ctx.Done()` (the same
    `ctx` `main` already cancels on signal), so shutdown remains prompt.
  - *Risk:* masking a real, non-network failure (e.g. wrong credentials, database
    does not exist) behind up to 2 minutes of retries before it is finally reported.
    *Mitigation:* accepted per the issue's own proposed fix, which explicitly asks
    for "poll ... until it accepts a connection or a bounded deadline expires"
    without carving out an exception for error type; the per-attempt `Warn` log still
    surfaces the underlying error text on every attempt, so the cause is visible in
    logs well before the deadline is reached.
