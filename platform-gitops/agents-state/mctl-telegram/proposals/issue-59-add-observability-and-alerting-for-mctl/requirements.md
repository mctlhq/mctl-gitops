# Add Observability and Alerting for mctl-telegram

## Context

mctl-telegram is a Go MCP server that gives AI agents access to a Telegram user
account via MTProto (gotd/td). As operator-facing usage grows, the service must
surface health, usage, and failure signals beyond what structured logs alone can
provide. Today the only persistent observability is slog JSON output (with
redaction via `audit.NewRedactingHandler`) and per-user audit rows written by
`db.Store.LogToolCall`. There is no /metrics endpoint, no Prometheus or OTel
metric SDK wired in, no dashboards, and no alerting.

Issue #59 requests a complete observability layer: Prometheus-style metrics
covering user lifecycle, MCP tool usage, JWT/auth failures, rate limiting, and
Telegram MTProto client errors; plus a set of actionable alerts for JWT spikes,
high error rates, high latency, zero traffic, and service unavailability.

## User stories

- AS an operator I WANT to see active user and tool-invocation trends over time
  SO THAT I can plan capacity and detect usage spikes before they become
  incidents.
- AS an operator I WANT alerts on JWT failures and high error rates SO THAT I
  can respond to authentication misconfigurations or upstream breakage before
  users report them.
- AS an operator I WANT a zero-traffic alert SO THAT I notice when the service
  silently stops receiving requests during expected traffic windows.
- AS an on-call engineer I WANT per-tool invocation counts and latency
  histograms SO THAT I can identify which tool is misbehaving during an
  incident.
- AS a security operator I WANT counters for auth failures, expired tokens, and
  rate-limit events SO THAT I can detect credential stuffing, misconfigured
  clients, or mass token expiry.
- AS an operator I WANT session lifecycle counters (connect, revoke, expire)
  SO THAT I can see user churn and track the effect of TTL policy changes.

## Acceptance criteria (EARS)

- WHEN the /metrics HTTP endpoint is scraped THE SYSTEM SHALL return valid
  Prometheus text-format exposition with all defined metric families.
- WHEN any HTTP handler returns a response THE SYSTEM SHALL record the request in
  mctl_http_requests_total labeled by method, route_pattern, and status_code;
  route_pattern MUST be derived from the chi route pattern (e.g.
  /api/account/{action}), never from the raw request path.
- WHEN a JWT verification step fails in any auth provider THE SYSTEM SHALL
  increment mctl_auth_failures_total with a reason label drawn from the set
  {jwt_expired, jwt_invalid_signature, jwt_invalid_issuer, jwt_missing_audience,
  jwt_wrong_audience, bearer_scheme_error, other}.
- WHEN the per-identity rate limiter rejects a request with HTTP 429 THE SYSTEM
  SHALL increment mctl_rate_limit_events_total labeled by identity_kind (user or
  anon).
- WHEN any MCP tool handler completes (success or error) THE SYSTEM SHALL
  increment mctl_tool_invocations_total{tool, status} and observe the elapsed
  wall-clock duration in mctl_tool_invocation_duration_seconds{tool}.
- WHEN the Telegram MTProto client goroutine exits with a non-context-canceled
  error THE SYSTEM SHALL increment mctl_telegram_client_errors_total.
- WHILE the server is running THE SYSTEM SHALL maintain a gauge
  mctl_telegram_client_pool_size reflecting the number of currently live pool
  entries.
- WHEN a new Telegram session is persisted via SaveSession THE SYSTEM SHALL
  increment mctl_sessions_connected_total.
- WHEN a session is revoked by self-service disconnect THE SYSTEM SHALL increment
  mctl_sessions_revoked_total{reason="disconnect"}.
- WHEN a session is removed by hard delete THE SYSTEM SHALL increment
  mctl_sessions_revoked_total{reason="delete"}.
- WHEN the background sweeper revokes sessions due to idle TTL THE SYSTEM SHALL
  increment mctl_sessions_revoked_total{reason="idle_expiry"} by the count of
  rows affected.
- WHEN the background sweeper revokes sessions due to absolute TTL THE SYSTEM
  SHALL increment mctl_sessions_revoked_total{reason="absolute_expiry"} by the
  count of rows affected.
- WHILE the server is running THE SYSTEM SHALL maintain a gauge
  mctl_sessions_active reflecting the count of non-revoked sessions whose
  last_used_at is within the last hour; this gauge SHALL be refreshed at least
  once per minute.
- IF mctl_auth_failures_total{reason="jwt_expired"} rate over 5 minutes exceeds
  the configured threshold THE SYSTEM SHALL fire the JWTExpiredSpike alert.
- IF the ratio of mctl_tool_invocations_total{status="error"} to
  mctl_tool_invocations_total over 5 minutes exceeds 10% THE SYSTEM SHALL fire
  the HighToolErrorRate alert.
- IF histogram_quantile(0.95, rate(mctl_tool_invocation_duration_seconds_bucket
  [5m])) exceeds 5 seconds THE SYSTEM SHALL fire the HighToolLatency alert.
- IF rate(mctl_tool_invocations_total[15m]) == 0 during the configured expected
  traffic window THE SYSTEM SHALL fire the ZeroTraffic alert.
- IF the /healthz endpoint is unreachable for more than 60 seconds THE SYSTEM
  SHALL fire the ServiceUnavailable alert.
- IF METRICS_ALLOW_CIDR is set THE SYSTEM SHALL respond 403 to /metrics requests
  originating from outside the configured CIDR; when unset the endpoint MUST be
  open for scraping without authentication.

## Out of scope

- Distributed tracing (OpenTelemetry spans, trace propagation) — separate
  initiative.
- Telegram update processing latency: gotd/td handles MTProto updates internally
  and does not expose a per-update callback that mctl-telegram controls; deferred
  unless gotd/td adds a suitable hook.
- Bot API webhook/polling errors: mctl-telegram uses a persistent MTProto
  connection, not the Bot API webhook model. MTProto client errors are covered by
  mctl_telegram_client_errors_total.
- Grafana dashboard JSON provisioning: metric and alert definitions are in scope;
  dashboard wiring is an ops/gitops follow-on.
- Per-user drill-down dashboards: Telegram IDs are PII; exposing per-user labels
  in Prometheus requires careful design and is deferred.
- OpenTelemetry SDK migration: go.mod already carries
  go.opentelemetry.io/otel/metric as an indirect dependency from gotd/td;
  migrating application instrumentation to OTel APIs is a separate task.

## Open questions

1. Scrape authentication: should /metrics require a bearer token in addition to
   the optional CIDR guard? The issue is silent. This proposal defaults to
   CIDR-only (consistent with Kubernetes PodMonitor scrape patterns). If a token
   is required the implementer should add METRICS_BEARER_TOKEN env support.

2. ZeroTraffic window: the issue says "when traffic is expected" without defining
   business hours. Proposal introduces METRICS_TRAFFIC_WINDOW_START_UTC and
   METRICS_TRAFFIC_WINDOW_END_UTC (integer hours 0-23, defaulting to 0 and 23 to
   mean "always"). The implementer should confirm the correct window with ops.

3. SessionsActive definition: "active users over time" could mean users with a
   live pool entry or users with a tool call in the last hour. Proposal tracks
   both: mctl_telegram_client_pool_size (live pool entries) and
   mctl_sessions_active (DB query for non-revoked sessions active in the past
   hour). The implementer should verify the DB query performs acceptably under
   expected row counts.

4. Per-reason sweep split: accurately labeling mctl_sessions_revoked_total by
   reason requires splitting SweepExpiredSessions into two separate UPDATE
   queries (idle vs absolute). This adds one DB round-trip per sweep cycle (every
   hour). Confirm acceptable before implementing.
