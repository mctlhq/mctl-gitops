# Tasks: issue-59-add-observability-and-alerting-for-mctl

- [ ] 1. Add `github.com/prometheus/client_golang` to go.mod — DoD: `go get
  github.com/prometheus/client_golang/prometheus` runs without error; go.mod and
  go.sum are updated; `go build ./...` passes.

- [ ] 2. Create `internal/metrics/metrics.go` with the `Registry` struct and a
  `New()` constructor (depends on 1) — DoD: `Registry` declares all collectors
  listed in the design (mctl_http_requests_total, mctl_auth_failures_total,
  mctl_rate_limit_events_total, mctl_tool_invocations_total,
  mctl_tool_invocation_duration_seconds, mctl_telegram_client_pool_size,
  mctl_telegram_client_errors_total, mctl_sessions_connected_total,
  mctl_sessions_revoked_total, mctl_sessions_active); `New()` registers them on
  a fresh `*prometheus.Registry` (not the global default); `go vet ./...` passes.

- [ ] 3. Create `internal/metrics/middleware.go` with `(*Registry).HTTPMiddleware()`
  (depends on 2) — DoD: middleware captures response status code via a wrapped
  `responseWriter`; uses `chi.RouteContext(req.Context()).RoutePattern()` as the
  route label (not raw path); increments `mctl_http_requests_total{method, route,
  status_code}`; unit test verifies a known route pattern is used rather than the
  raw path for a route like `/api/account/{action}`.

- [ ] 4. Add `METRICS_ALLOW_CIDR` to `internal/config/config.go` and
  `metricsHandler` to `cmd/server/main.go` (depends on 2) — DoD: `Config.
  MetricsAllowCIDR` is loaded from the env var; `metricsHandler` wraps
  `promhttp.HandlerFor(m.Prometheus, ...)` with a CIDR check that returns 403
  when set and the remote IP is outside the CIDR; when unset the handler is
  open; `/metrics` is mounted on the chi router without auth middleware.

- [ ] 5. Wire HTTP middleware into `cmd/server/main.go` (depends on 3, 4) — DoD:
  `mux.Use(m.HTTPMiddleware())` is registered before any route; a scrape of
  /metrics after a /healthz request shows `mctl_http_requests_total{route=
  "/healthz", ...}` incremented.

- [ ] 6. Extend `auth.Middleware` in `internal/auth/middleware.go` to accept and
  use `*metrics.Registry` (depends on 2) — DoD: function signature gains a
  `*metrics.Registry` parameter (nil-safe); on auth failure the error string is
  classified into one of {jwt_expired, jwt_invalid_signature, jwt_invalid_issuer,
  jwt_missing_audience, jwt_wrong_audience, bearer_scheme_error, other} and
  `mctl_auth_failures_total` is incremented; all call sites in
  `cmd/server/main.go` pass `m`; existing auth middleware tests still pass.

- [ ] 7. Wire rate-limit counter into `internal/audit/ratelimit.go` (depends on 2)
  — DoD: `RateLimiter` gains a `WithMetrics(*metrics.Registry)` chaining method;
  after writing the 429 response, `mctl_rate_limit_events_total{identity_kind}`
  is incremented (identity_kind="user" when an identity is present, "anon"
  otherwise); `cmd/server/main.go` chains `.WithMetrics(m)` on the limiter; unit
  test asserts counter increments on 429.

- [ ] 8. Extend `mcp.Server` and `s.audit()` in `internal/mcp/server.go` and
  `internal/mcp/tools.go` to record tool metrics (depends on 2) — DoD: `Server`
  gains `WithMetrics(*metrics.Registry)`; `s.audit()` gains a `startedAt time.
  Time` parameter; every tool handler records `time.Now()` at entry and passes
  it; inside `s.audit()` the histogram and counter are observed/incremented for
  all 12 registered tools; `cmd/server/main.go` chains `.WithMetrics(m)` on the
  MCP server; unit test (mcp/tools_test.go or a new file) verifies counter and
  histogram are populated after a tool call.

- [ ] 9. Wire Telegram client pool metrics into `internal/telegram/clientpool.go`
  (depends on 2) — DoD: `ClientPool` gains `WithMetrics(*metrics.Registry)`;
  `acquire()` increments `mctl_telegram_client_pool_size` when a new entry is
  created; `run()` decrements the gauge when the goroutine exits and increments
  `mctl_telegram_client_errors_total` on non-context-canceled errors;
  `cmd/server/main.go` passes `m` via `pool.WithMetrics(m)`; existing
  `clientpool_test.go` tests still pass.

- [ ] 10. Add `reason` parameter to `db.Store.RevokeActiveSession` and wire session
  lifecycle metrics into `internal/db/store.go` (depends on 2) — DoD:
  `RevokeActiveSession(ctx, userID, reason string)` replaces the current
  signature; all callers updated (self-service disconnect in mcp/tools.go passes
  "disconnect"; CheckSessionValid passes "idle_expiry" or "absolute_expiry"
  matching db.ReasonIdle / db.ReasonAbsolute); `SaveSession` increments
  `mctl_sessions_connected_total` after commit; `HardDeleteAccount` increments
  `mctl_sessions_revoked_total{reason="delete"}` by rows removed; unit tests
  for SaveSession and HardDeleteAccount assert counter state.

- [ ] 11. Split `SweepExpiredSessions` into `SweepIdleSessions` and
  `SweepAbsoluteSessions` in `internal/db/store.go` and update
  `internal/sweeper/sweeper.go` (depends on 10) — DoD: `SweepIdleSessions`
  revokes rows where `last_used_at < $idle_cutoff`; `SweepAbsoluteSessions`
  revokes rows where `expires_at < $now`; each returns row count; `sweeper.
  Sessions` calls both in sequence and increments `mctl_sessions_revoked_total`
  by the respective counts; existing `store_ttl_test.go` tests pass against both
  methods; `Store` gains `WithMetrics`.

- [ ] 12. Add `db.Store.CountActiveSessions` and the active session sampler goroutine
  in `cmd/server/main.go` (depends on 2, 11) — DoD: `CountActiveSessions` runs
  the SELECT COUNT(*) query described in the design (non-revoked, last_used_at
  within last hour); a goroutine in `main()` calls it every 60 seconds and sets
  `m.SessionsActiveGauge`; the goroutine exits on ctx cancellation; a unit test
  for `CountActiveSessions` verifies the count changes after inserting and
  revoking a session.

- [ ] 13. Write PrometheusRule alert YAML and commit to gitops repo (depends on
  1-12) — DoD: a PrometheusRule YAML containing the 8 alert rules from the
  design is committed under an appropriate path in mctl-gitops; all rule names
  match the requirements (JWTExpiredSpike, JWTInvalidSpike, HighToolErrorRate,
  HighToolLatency, ZeroTraffic, RateLimitSpike, TelegramClientErrors,
  ServiceUnavailable); `promtool check rules` passes on the file.

## Tests

- [ ] T1. `internal/metrics/metrics_test.go` — verify `New()` registers all
  expected metric names on the registry; `prometheus.Gatherer.Gather()` returns
  a family for each of the 10 metric names defined in the design.

- [ ] T2. `internal/metrics/middleware_test.go` — verify that a request to a chi
  route `/api/account/{action}` is recorded as route="/api/account/{action}"
  (pattern), not as "/api/account/disconnect" (raw path); verify status code
  label matches the response code.

- [ ] T3. `internal/auth/middleware_test.go` (extend existing) — for each error
  string variant emitted by sharedhmac/verifier.go and localjwt/issuer.go, verify
  that the correct `reason` label is incremented.

- [ ] T4. `internal/audit/ratelimit_test.go` (extend existing) — verify that a
  request that exceeds the per-user bucket increments `mctl_rate_limit_events_
  total{identity_kind="user"}` and that an anonymous request increments the
  "anon" variant.

- [ ] T5. `internal/mcp/tools_test.go` (extend existing) — call `toolListDialogs`
  handler with a fake store and pool; verify `mctl_tool_invocations_total{tool=
  "list_dialogs", status="ok"}` increments by 1 and
  `mctl_tool_invocation_duration_seconds` has one observation.

- [ ] T6. `internal/telegram/clientpool_test.go` (extend existing) — verify that
  after `Borrow` creates a new entry, `mctl_telegram_client_pool_size` is 1;
  after the entry's context is cancelled and the run goroutine exits, the gauge
  returns to 0.

- [ ] T7. `internal/db/store_test.go` (extend existing) — verify that
  `SaveSession` increments `mctl_sessions_connected_total`; `RevokeActiveSession`
  with reason="disconnect" increments `mctl_sessions_revoked_total{reason=
  "disconnect"}`; `HardDeleteAccount` increments `mctl_sessions_revoked_total
  {reason="delete"}`.

- [ ] T8. Integration smoke test in `cmd/server/` — start the server in-process
  (as existing tests do), make one `/healthz` request and one `/mcp` request,
  then GET `/metrics`; assert the response contains
  `mctl_http_requests_total` and `mctl_tool_invocation_duration_seconds_bucket`.

## Rollback

1. **Config**: remove `METRICS_ALLOW_CIDR` from environment / Helm values.yaml.
   The env var is optional so existing deployments are not affected even if the
   binary still reads it.

2. **Application code**: revert the following files to their pre-PR state:
   - `internal/metrics/` (delete entire package)
   - `cmd/server/main.go` (remove metrics.New, mux.Use(m.HTTPMiddleware()),
     mux.Get("/metrics"), active session sampler goroutine, and WithMetrics calls)
   - `internal/auth/middleware.go` (remove metrics parameter)
   - `internal/audit/ratelimit.go` (remove WithMetrics and counter increment)
   - `internal/mcp/server.go` and `internal/mcp/tools.go` (remove WithMetrics,
     startedAt parameter, and metric observations)
   - `internal/telegram/clientpool.go` (remove WithMetrics, gauge increments)
   - `internal/db/store.go` (restore RevokeActiveSession signature, remove
     CountActiveSessions, remove counter increments; revert SweepExpiredSessions
     split back to the original single method)
   - `internal/sweeper/sweeper.go` (restore call to SweepExpiredSessions)

3. **Dependency**: run `go mod tidy` to drop `github.com/prometheus/
   client_golang` from go.mod and go.sum after removing all import sites.

4. **Alert rules**: delete the PrometheusRule YAML from the gitops repo. This
   is independent of the binary rollback and can be done before or after step 2.

5. **No DB migrations**: there are no schema changes. The `SweepExpiredSessions`
   split is purely in Go and SQL DML (UPDATE statements); reverting it requires
   no DDL.
