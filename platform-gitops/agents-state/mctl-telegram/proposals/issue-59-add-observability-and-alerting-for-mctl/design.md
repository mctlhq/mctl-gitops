# Design: issue-59-add-observability-and-alerting-for-mctl

## Current state

mctl-telegram has no /metrics endpoint and no Prometheus or OTel metric SDK
wired into application code. Observability today is limited to:

- **Structured logs**: slog JSON via `audit.NewRedactingHandler` wrapping a
  `slog.JSONHandler` (cmd/server/main.go:35-38). Sensitive fields are redacted
  by the handler defined in internal/audit/redact.go.

- **Audit log table**: `db.Store.LogToolCall` (internal/db/store.go:677-711)
  writes one row per tool call to `audit_logs`, including tool_name, status, and
  an entry_hash for chain verification. Accessible to users via the
  `get_my_audit_log` MCP tool.

- **chi built-in middleware**: `middleware.RequestID`, `middleware.RealIP`,
  `middleware.Recoverer`, `middleware.Timeout` (cmd/server/main.go:92-95). These
  provide request IDs and panic recovery but emit no metrics.

- **Rate limiter**: `audit.RateLimiter.Middleware` (internal/audit/ratelimit.go)
  returns HTTP 429 and logs nothing — there is no counter increment.

- **Auth middleware**: `auth.Middleware` (internal/auth/middleware.go:14-30)
  calls `slog.Warn("auth failed", "err", err)` on failure but records no counter.

- **Telegram client pool**: `telegram.ClientPool` (internal/telegram/clientpool.go)
  logs idle client closure via `slog.Info("idle telegram client, closing")` and
  MTProto client errors via `slog.Warn("telegram client exited", ...)`, but
  records no counters or gauges.

- **OTel indirect dependency**: go.mod includes `go.opentelemetry.io/otel
  v1.43.0`, `go.opentelemetry.io/otel/metric v1.43.0`, and
  `go.opentelemetry.io/otel/trace v1.43.0` as **indirect** dependencies pulled
  in transitively by gotd/td. No application code initialises the OTel SDK or
  registers any instrument.

There is no /metrics route in the chi router (cmd/server/main.go:103-168).

## Proposed solution

### Overview

Add a new `internal/metrics/` package that owns all Prometheus collector
definitions as a single non-global `*Registry`. Inject `*metrics.Registry` into
the components that record observations. Mount a /metrics handler on the chi
router. Write PrometheusRule alert definitions in the gitops repo.

The approach uses `github.com/prometheus/client_golang` directly. Although the
OTel metric API is already an indirect dep, the OTel metric SDK and a Prometheus
exporter would add ~6 further direct dependencies and non-trivial SDK
initialization. An OTel migration is recorded as a follow-on in Open questions.

### New package: internal/metrics/

**internal/metrics/metrics.go** defines `Registry`:

```go
package metrics

import "github.com/prometheus/client_golang/prometheus"

type Registry struct {
    Prometheus *prometheus.Registry

    // HTTP layer
    HTTPRequestsTotal *prometheus.CounterVec // labels: method, route, status_code

    // Auth layer
    AuthFailuresTotal *prometheus.CounterVec // labels: reason, provider

    // Rate limiter
    RateLimitEventsTotal *prometheus.CounterVec // labels: identity_kind

    // MCP tool layer
    ToolInvocationsTotal   *prometheus.CounterVec   // labels: tool, status
    ToolInvocationDuration *prometheus.HistogramVec  // labels: tool

    // Telegram client pool
    TelegramClientPoolSize    prometheus.Gauge
    TelegramClientErrorsTotal prometheus.Counter

    // Session lifecycle
    SessionsConnectedTotal prometheus.Counter
    SessionsRevokedTotal   *prometheus.CounterVec // labels: reason
    SessionsActiveGauge    prometheus.Gauge
}

func New() *Registry { ... } // registers all collectors on a fresh prometheus.Registry
```

All metric names carry the `mctl_` prefix per Prometheus naming conventions.

Buckets for `ToolInvocationDuration`: `{.05, .1, .25, .5, 1, 2.5, 5, 10}`
seconds — covers sub-100ms fast reads through 10-second Telegram round-trips.

**internal/metrics/middleware.go** defines `HTTPMiddleware`:

```go
func (r *Registry) HTTPMiddleware() func(http.Handler) http.Handler
```

It wraps responses using a thin `responseWriter` that captures the status code,
then increments `HTTPRequestsTotal`. The `route` label is extracted via
`chi.RouteContext(req.Context()).RoutePattern()` after the handler returns,
preventing high-cardinality raw-path labels from path parameters such as
user IDs.

### Injection sites

#### cmd/server/main.go

Construct `m := metrics.New()` near the top of `main()`, after config is loaded
and before any component is wired. Inject `m` into each subsystem below and
mount the handler:

```go
mux.Use(m.HTTPMiddleware())
mux.Get("/metrics", metricsHandler(m, cfg.MetricsAllowCIDR))
```

`metricsHandler` wraps `promhttp.HandlerFor(m.Prometheus, promhttp.HandlerOpts{})`
with an optional CIDR allowlist check using `net.ParseCIDR` and
`r.RemoteAddr`. When `MetricsAllowCIDR` is empty the handler is open.

#### internal/auth/middleware.go

`Middleware` gains an optional `*metrics.Registry` parameter (passed as nil from
call sites that have not yet been wired; the helper is nil-safe). When
authentication fails, classify the error string to pick the `reason` label:

| Error substring                      | reason label             |
|--------------------------------------|--------------------------|
| "JWT expired"                        | jwt_expired              |
| "invalid JWT signature"              | jwt_invalid_signature    |
| "unexpected JWT issuer"              | jwt_invalid_issuer       |
| "JWT missing required audience"      | jwt_missing_audience     |
| "JWT audience ... does not match"    | jwt_wrong_audience       |
| "Bearer scheme"                      | bearer_scheme_error      |
| anything else                        | other                    |

The error strings are stable because they are defined as string literals in
`internal/auth/sharedhmac/verifier.go` (verifyJWT, checkAudience) and
`internal/auth/localjwt/issuer.go` (Verify, CheckAudience). The `provider`
label is the auth mode string passed to `Middleware` at construction time.

The middleware signature change from `Middleware(p Provider, required bool)` to
`Middleware(p Provider, required bool, m *metrics.Registry)` is backward-
compatible because call sites in cmd/server/main.go are the only consumers
(confirmed by grep — internal package, no external callers).

#### internal/audit/ratelimit.go

After writing the 429 response, `RateLimiter.Middleware` increments
`RateLimitEventsTotal`. `RateLimiter` gains a `Metrics *metrics.Registry` field
set by a `WithMetrics` chaining method so the limiter can be constructed without
metrics for tests.

#### internal/mcp/tools.go and internal/mcp/server.go

`mcp.Server` gains `Metrics *metrics.Registry` set by a `WithMetrics` chaining
method. The existing `s.audit()` helper (tools.go:772-784) is extended to accept
a `startedAt time.Time` parameter. Every tool handler records `time.Now()` at
entry and passes it to `s.audit()`. Inside `s.audit()`:

```go
if s.Metrics != nil {
    elapsed := time.Since(startedAt).Seconds()
    s.Metrics.ToolInvocationDuration.WithLabelValues(tool).Observe(elapsed)
    s.Metrics.ToolInvocationsTotal.WithLabelValues(tool, status).Inc()
}
```

The `tool` label matches the string passed to `s.audit()` today (e.g.
"list_dialogs", "send_message:sent", "send_message:draft"). Status is "ok" or
"error" exactly as today. There are 12 tools registered in `s.HTTPHandler()`
(server.go:61-72) so cardinality is bounded.

#### internal/telegram/clientpool.go

`ClientPool` gains `Metrics *metrics.Registry` set by a `WithMetrics` chaining
method.

In `acquire()` (clientpool.go:88-112): when a new entry is inserted into
`p.entries`, call `p.Metrics.TelegramClientPoolSize.Inc()`.

In `run()` (clientpool.go:114-133): after the goroutine exits, call
`p.Metrics.TelegramClientPoolSize.Dec()`. When `err != nil && err !=
context.Canceled`, also call `p.Metrics.TelegramClientErrorsTotal.Inc()`.

#### internal/db/store.go

`Store` gains `Metrics *metrics.Registry` set by a `WithMetrics` chaining
method (nil-safe throughout).

- `SaveSession` (store.go:232-259): after `tx.Commit()` succeeds, call
  `s.Metrics.SessionsConnectedTotal.Inc()`.

- `RevokeActiveSession` (store.go:356-367): when `rows > 0`, call
  `s.Metrics.SessionsRevokedTotal.WithLabelValues("disconnect").Inc()`.
  Note: this is used by both self-service disconnect and the session TTL check
  in `CheckSessionValid`. Add a `reason` parameter to `RevokeActiveSession`
  so callers can pass "disconnect", "idle_expiry", or "absolute_expiry" as
  appropriate.

- `HardDeleteAccount` (store.go:369-383): after deletion, call
  `s.Metrics.SessionsRevokedTotal.WithLabelValues("delete").Add(float64(rows))`.

- `SweepExpiredSessions` (store.go:526-544): split into two methods:
  `SweepIdleSessions` and `SweepAbsoluteSessions`. Each runs the corresponding
  single-condition UPDATE and increments
  `SessionsRevokedTotal.WithLabelValues("idle_expiry")` or
  `SessionsRevoke.Total.WithLabelValues("absolute_expiry")` by the rows affected.
  The sweeper goroutine (internal/sweeper/sweeper.go) calls both in sequence.

#### cmd/server/main.go — active session sampler

A new short goroutine started after `pool` is constructed samples the active
session count once per minute and sets `m.SessionsActiveGauge`:

```go
go func() {
    ticker := time.NewTicker(time.Minute)
    defer ticker.Stop()
    for {
        select {
        case <-ctx.Done():
            return
        case <-ticker.C:
            n, err := store.CountActiveSessions(ctx)
            if err == nil {
                m.SessionsActiveGauge.Set(float64(n))
            }
        }
    }
}()
```

`db.Store.CountActiveSessions` runs:

```sql
SELECT COUNT(*) FROM telegram_accounts
WHERE revoked_at IS NULL
  AND (last_used_at IS NULL OR last_used_at > $1)
```

with `$1 = time.Now().UTC().Add(-time.Hour)`.

### Configuration additions (internal/config/config.go)

Two new fields on `Config`:

```go
MetricsAllowCIDR            string // METRICS_ALLOW_CIDR, optional e.g. "10.0.0.0/8"
MetricsTrafficWindowStartUTC int    // METRICS_TRAFFIC_WINDOW_START_UTC, default 0
MetricsTrafficWindowEndUTC   int    // METRICS_TRAFFIC_WINDOW_END_UTC, default 23
```

The traffic window fields are used only in the alert rule YAML (they gate the
ZeroTraffic alert with a time() predicate); they are not used at runtime by the
Go server.

### Alert rules

Delivered as a PrometheusRule YAML (Kubernetes CRD) committed to the gitops
repo. Example rules (threshold values are starting points; operators tune them):

```yaml
groups:
  - name: mctl-telegram
    rules:
      - alert: JWTExpiredSpike
        expr: rate(mctl_auth_failures_total{reason="jwt_expired"}[5m]) > 0.1
        for: 2m
        annotations:
          summary: "JWT expired failures spiking"

      - alert: JWTInvalidSpike
        expr: rate(mctl_auth_failures_total{reason=~"jwt_invalid.*|jwt_wrong.*|jwt_missing.*"}[5m]) > 0.05
        for: 2m
        annotations:
          summary: "JWT invalid/wrong failures spiking"

      - alert: HighToolErrorRate
        expr: |
          rate(mctl_tool_invocations_total{status="error"}[5m])
          /
          rate(mctl_tool_invocations_total[5m]) > 0.1
        for: 5m
        annotations:
          summary: "More than 10% of tool calls are failing"

      - alert: HighToolLatency
        expr: histogram_quantile(0.95, rate(mctl_tool_invocation_duration_seconds_bucket[5m])) > 5
        for: 5m
        annotations:
          summary: "p95 tool invocation latency > 5s"

      - alert: ZeroTraffic
        expr: rate(mctl_tool_invocations_total[15m]) == 0
        for: 15m
        annotations:
          summary: "No tool invocations for 15 minutes"

      - alert: RateLimitSpike
        expr: rate(mctl_rate_limit_events_total[5m]) > 1
        for: 2m
        annotations:
          summary: "Rate limit events spiking"

      - alert: TelegramClientErrors
        expr: increase(mctl_telegram_client_errors_total[10m]) > 0
        for: 0m
        annotations:
          summary: "MTProto client exited with error"

      - alert: ServiceUnavailable
        # Requires a blackbox exporter probe on /healthz
        expr: probe_success{job="mctl-telegram-healthz"} == 0
        for: 1m
        annotations:
          summary: "mctl-telegram /healthz is failing"
```

## Alternatives

### Option A: OpenTelemetry SDK + Prometheus exporter

go.mod already carries `go.opentelemetry.io/otel/metric v1.43.0` as an indirect
dependency from gotd/td. Adding the OTel metric SDK (`go.opentelemetry.io/otel/
sdk/metric`) and the Prometheus exporter (`go.opentelemetry.io/otel/exporters/
prometheus`) would make the instrumentation API portable to OTLP in the future
without changing call sites.

Rejected for this milestone because: (a) it adds roughly 6 new direct
dependencies and non-trivial SDK initialization (MeterProvider, exporter,
resource detection) to cmd/server/main.go; (b) no existing application code uses
OTel APIs — the indirect dep is purely from gotd/td internals; (c)
`prometheus/client_golang` is simpler for a greenfield instrumentation pass and
is sufficient for the stated requirements. An OTel migration is a valid follow-on
once the metric surface is stable.

### Option B: Structured log mining only (no Prometheus endpoint)

Parse slog output in a log aggregator (Loki + LogQL) to derive metrics. This
requires zero code changes to the Go binary. Rejected because: (a) quantile
latency calculations from log lines require approximate algorithms and significant
aggregator resources; (b) the issue explicitly asks for a metrics endpoint and
dashboards, implying a scrape-pull model; (c) Loki is not guaranteed to be
available in all deployment targets; (d) alerting on log-derived metrics has
higher latency than native Prometheus scrape.

### Option C: Global prometheus.DefaultRegisterer

Use the Prometheus default global registry to avoid injecting `*metrics.Registry`
through constructors. Fewer code changes. Rejected because: (a) parallel tests
that spin up multiple server instances would register duplicate metric names and
panic; (b) the project's existing style passes dependencies through constructors
(db.NewStore, telegram.NewClientPool, audit.NewRateLimiter); using a global would
be inconsistent; (c) the non-global approach costs ~10 extra lines of wiring in
cmd/server/main.go but pays off in testability.

## Platform impact

- **New direct dependency**: `github.com/prometheus/client_golang` (no CGo,
  ~1.5 MiB). One new `require` line in go.mod. No breaking changes to any
  existing public API — all changes are additive or extend existing unexported
  function signatures that have only in-package callers.

- **New env vars**: `METRICS_ALLOW_CIDR` (optional), `METRICS_TRAFFIC_WINDOW_
  START_UTC` / `METRICS_TRAFFIC_WINDOW_END_UTC` (optional, inform alert YAML
  only, not used at runtime by Go code).

- **DB**: one additional periodic `SELECT COUNT(*)` query every 60 seconds for
  the active session gauge sampler. Negligible load for expected row counts.
  Splitting `SweepExpiredSessions` into two UPDATE queries adds one extra round-
  trip per hour-long sweep cycle — also negligible.

- **Schema**: no DDL changes required.

- **Label cardinality**:
  - `mctl_tool_invocations_total{tool, status}`: tool has 12 distinct values
    (from server.go:61-72), status has 2 (ok, error). Cardinality = 24.
  - `mctl_http_requests_total{method, route, status_code}`: route is derived
    from chi route patterns (bounded set), not raw paths. Cardinality is bounded.
  - `mctl_auth_failures_total{reason, provider}`: 7 reason values x 3 provider
    modes = 21. Bounded.
  - No per-user labels are exposed in any metric — Telegram user IDs are PII.

- **Backward compatibility**: all existing routes (/healthz, /readyz, /mcp,
  /oauth/*, /bridge, /api/account/*) are unaffected. The /metrics route is new
  and additive.

- **Rollback**: delete `internal/metrics/`, revert the injection sites in
  cmd/server/main.go, auth/middleware.go, audit/ratelimit.go, mcp/server.go,
  mcp/tools.go, telegram/clientpool.go, db/store.go, and sweeper/sweeper.go.
  No DB migrations to undo. The alert YAML can be deleted from gitops
  independently.
