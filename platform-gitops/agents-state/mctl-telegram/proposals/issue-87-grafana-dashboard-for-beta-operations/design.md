# Design: issue-87-grafana-dashboard-for-beta-operations

## Current state

`internal/metrics/metrics.go` defines a `Registry` struct that holds every
Prometheus collector for mctl-telegram. A single `New()` call registers all
thirteen metric families on a fresh (non-global) `prometheus.Registry`:

| Metric name | Kind | Labels |
|---|---|---|
| `mctl_http_requests_total` | CounterVec | `method`, `route`, `status_code` |
| `mctl_auth_failures_total` | CounterVec | `reason`, `provider` |
| `mctl_rate_limit_events_total` | CounterVec | `identity_kind` |
| `mctl_tool_invocations_total` | CounterVec | `tool`, `status` |
| `mctl_tool_invocation_duration_seconds` | HistogramVec | `tool` |
| `mctl_telegram_client_pool_size` | Gauge | (none) |
| `mctl_telegram_client_errors_total` | Counter | (none) |
| `mctl_telegram_pool_capacity` | Gauge | (none) |
| `mctl_telegram_flood_wait_events_total` | CounterVec | `tool` |
| `mctl_sessions_connected_total` | Counter | (none) |
| `mctl_sessions_revoked_total` | CounterVec | `reason` |
| `mctl_sessions_active` | Gauge | (none) |
| `mctl_oauth_pending_auth_size` | Gauge | (none) |

`internal/metrics/middleware.go` implements `HTTPMiddleware()`, a chi-compatible
wrapper that increments `mctl_http_requests_total` with the chi route pattern as
the `route` label (not the raw URL, to prevent high-cardinality label explosion).

`cmd/server/main.go` calls `metrics.New()` at startup, wires the registry into
every subsystem (pool, store, OAuth server, rate limiter, MCP server), sets
`mctl_telegram_pool_capacity` to the configured `TELEGRAM_MAX_SESSIONS` value
or -1 when uncapped, and exposes the Prometheus text format at `GET /metrics`
via `promhttp.HandlerFor(m.Prometheus, ...)` (lines 274-306).

The MCP tool names that appear in the `tool` label are defined in
`internal/mcp/tools.go`:
`list_dialogs`, `get_unread_messages`, `prepare_send_message`, `send_message`,
`get_messages`, `prepare_pin_message`, `pin_message`, `disconnect_telegram_account`,
`delete_telegram_account`, `get_my_audit_log`, `list_telegram_identities`,
`set_telegram_access`, `get_user_audit_log`, `revoke_telegram_session`.

`docs/hpa.md` documents the HPA guide, Prometheus Adapter config, and
PrometheusRule. It references `mctl_telegram_pool_capacity` and
`mctl_telegram_flood_wait_events_total` in prose but contains no link to a
Grafana dashboard.

There is no `deploy/` directory in the repository. No Grafana JSON is committed.

## Proposed solution

### New file: `deploy/grafana/mctl-telegram-beta.json`

A single Grafana 10.x-compatible dashboard JSON file. The file is
self-describing and importable via Grafana's UI "Import dashboard" flow or via
a provisioning sidecar that reads from the same Git path.

**Dashboard identity**

```
uid:   mctl-telegram-beta
title: mctl-telegram Beta
tags:  [mctl, beta, telegram]
```

A stable `uid` means repeated imports via provisioning are idempotent (Grafana
updates the existing dashboard rather than creating a duplicate).

**Data source input**

The file declares a `__inputs__` block with one entry:

```json
{
  "name": "DS_PROMETHEUS",
  "label": "Prometheus",
  "type": "datasource",
  "pluginId": "prometheus"
}
```

On import Grafana prompts the operator to map `DS_PROMETHEUS` to the
environment's Prometheus data source. All panel targets reference
`${DS_PROMETHEUS}`. This avoids hardcoding a data source UID that differs
between environments.

**Template variables**

Three chained Prometheus label-value query variables:

| Variable | Type | Query | Regex | Multi-value |
|---|---|---|---|---|
| `namespace` | query | `label_values(mctl_http_requests_total, namespace)` | — | no |
| `pod` | query | `label_values(mctl_http_requests_total{namespace="$namespace"}, pod)` | — | yes |
| `instance` | query | `label_values(mctl_http_requests_total{namespace="$namespace",pod=~"$pod"}, instance)` | — | yes |

All panel metric selectors include
`{namespace="$namespace",pod=~"$pod",instance=~"$instance"}` so that
single-replica and fleet-wide views work by adjusting the pod/instance
variables.

Note: `namespace`, `pod`, and `instance` labels are not emitted by the Go
process. They are attached by the Prometheus Operator PodMonitor scrape
relabeling that injects Kubernetes metadata. Standard Kubernetes deployments
with the Prometheus Operator supply these labels automatically.

**Panel rows and panels**

Each row is a `type: "row"` panel with `collapsed: false`. Panels within a row
carry a `description` string (Grafana shows this as a tooltip on the panel
header) so a fresh on-call understands the signal at a glance.

Row 1 — Traffic:
- `HTTP request rate` (time series): `rate(mctl_http_requests_total{...}[$__rate_interval])` grouped by `route, status_code`. Description: "Requests per second by chi route pattern and HTTP status code. High 5xx rate or sudden drop signals handler failures."
- `MCP tool invocations` (time series): `rate(mctl_tool_invocations_total{...}[$__rate_interval])` grouped by `tool, status`. Description: "MCP tool calls per second, split by tool name and outcome (ok / error). Spike in error series often precedes FloodWait events."
- `Tool invocation duration p50/p95/p99` (time series): `histogram_quantile(0.50|0.95|0.99, sum(rate(mctl_tool_invocation_duration_seconds_bucket{...}[$__rate_interval])) by (le, tool))`. Description: "Wall-clock latency percentiles per MCP tool. Histograms use fixed buckets [0.05,0.1,0.25,0.5,1,2.5,5,10] seconds (defined in metrics.go)."

Row 2 — Session pool:
- `Pool size vs capacity` (time series): `mctl_telegram_client_pool_size{...}` and `mctl_telegram_pool_capacity{...}`. Description: "Live MTProto client pool entries versus the configured TELEGRAM_MAX_SESSIONS cap. A -1 capacity line means the pool is uncapped."
- `Pool utilization %` (gauge/stat): `mctl_telegram_client_pool_size{...} / clamp_min(mctl_telegram_pool_capacity{...}, 1) * 100`. The `clamp_min(..., 1)` guards against the -1 sentinel (when uncapped the panel shows a nonsensical value, which is acceptable and documented in the panel description). Description: "Session pool fill fraction. Meaningful only when TELEGRAM_MAX_SESSIONS > 0 (capacity > 0). Used as the HPA signal; see docs/hpa.md."
- `Client error rate` (time series): `rate(mctl_telegram_client_errors_total{...}[$__rate_interval])`. Description: "Rate of MTProto client goroutine exits with a non-context-canceled error. Non-zero baseline here usually means Telegram connectivity issues or auth-key corruption."

Row 3 — Telegram pressure:
- `FloodWait events` (time series): `rate(mctl_telegram_flood_wait_events_total{...}[$__rate_interval])` grouped by `tool`. Description: "Rate of Telegram FLOOD_WAIT_X errors by MCP tool. Each increment means a tool call was delayed by a server-side rate limit; sustained values > 0 indicate Telegram is throttling this account."

Row 4 — Sessions lifecycle:
- `Active sessions` (stat): `mctl_sessions_active{...}`. Description: "Non-revoked sessions last used within the past hour. Refreshed every minute by a background sampler in main(). Sudden drop may indicate a bulk revocation or session sweep."
- `New sessions rate` (time series): `rate(mctl_sessions_connected_total{...}[$__rate_interval])`. Description: "Rate of new Telegram sessions persisted via SaveSession. Each increment corresponds to a user successfully completing Telegram login."
- `Session revocation rate by reason` (time series): `rate(mctl_sessions_revoked_total{...}[$__rate_interval])` grouped by `reason`. Description: "Revocations per second by reason: disconnect, delete, idle_expiry (30d), absolute_expiry (90d). Spikes in idle_expiry are expected during quiet periods."

Row 5 — OAuth:
- `Pending OAuth flows` (stat): `mctl_oauth_pending_auth_size{...}`. Description: "Count of in-flight OAuth authorization flows. Refreshed every minute. A sustained non-zero value with no corresponding traffic may indicate abandoned flows or bot-scan activity against /oauth/authorize (see docs/hpa.md)."
- `Auth failure rate by reason` (time series): `rate(mctl_auth_failures_total{...}[$__rate_interval])` grouped by `reason, provider`. Description: "Authentication failures per second by failure reason and provider. Elevated values may indicate misconfigured tokens, clock skew, or brute-force attempts."

Row 6 — Rate limiting:
- `Rate limit events by identity kind` (time series): `rate(mctl_rate_limit_events_total{...}[$__rate_interval])` grouped by `identity_kind`. Description: "HTTP 429 responses issued by the rate limiter per second, split by identity_kind (user / anon). High anon rate may indicate unauthenticated scanning; high user rate may indicate a runaway MCP client."

**JSON structure notes**

- `schemaVersion: 39` (Grafana 10.3+).
- `refresh: "30s"` default; time range default `now-1h` to `now`.
- All time series panels use `fillOpacity: 10`, `lineWidth: 1`, `spanNulls: false`.
- Stat/gauge panels use `reducers: ["last"]` and `orientation: "auto"`.
- Panel IDs are sequential integers starting at 1.
- The file is formatted with two-space indentation so diffs are readable.

### Edit: `docs/hpa.md`

Add a new section at the end of the file:

```markdown
## Grafana dashboard

A pre-built operator dashboard is committed at
`deploy/grafana/mctl-telegram-beta.json`. Import it into Grafana via
**Dashboards > Import** and map the `DS_PROMETHEUS` input to your Prometheus
data source. The dashboard covers the same pool-utilization signal used by the
HPA (Session pool row) plus traffic, Telegram pressure, session lifecycle, OAuth,
and rate-limiting panels.
```

## Alternatives

### 1. Grafonnet / Jsonnet-generated dashboard

Grafana Labs maintains Grafonnet, a Jsonnet library for generating dashboard
JSON. This approach keeps the source DRY and catches structural errors at
generation time. It was rejected because it adds a Jsonnet toolchain dependency
(not present in the repo's Go stack), introduces a build step before the file
can be committed, and is disproportionate for a single static dashboard. The
maintenance burden of a hand-authored JSON file is low at this scale.

### 2. Multiple dashboards — one per tier (beta, prod)

Separate dashboard files per tier allow tier-specific thresholds and panel
sets. Rejected because the metric schema is identical across tiers; the
`namespace`/`pod`/`instance` template variables already provide the scope
needed to filter to a specific tier. A single dashboard reduces drift.

### 3. Continue with ad-hoc per-environment dashboards

Maintains the status quo: operators build panels locally, no file is committed.
Rejected explicitly by the issue — it is the problem this work solves. Ad-hoc
dashboards do not survive environment teardown and cannot be code-reviewed.

## Platform impact

**Migrations**: none. No Go code changes, no schema changes, no Kubernetes
manifest changes.

**Backward compatibility**: the new `deploy/grafana/` directory is additive.
Nothing depends on its absence.

**Resource impact**: the dashboard JSON is a static file (estimated ~60 KB
formatted). It has no runtime footprint.

**Risks and mitigations**:

| Risk | Mitigation |
|---|---|
| `namespace`/`pod`/`instance` labels absent on non-Kubernetes scrape targets | Document the assumption in `deploy/grafana/` and in `docs/hpa.md`. Variable queries degrade gracefully to empty (panels still render with no filter). |
| Pool utilization panel divides by -1 when uncapped | Use `clamp_min(mctl_telegram_pool_capacity, 1)` in the PromQL expression so the result is nonsensical but not a Grafana error. Add a panel description warning. |
| Grafana version incompatibility | `schemaVersion: 39` is supported by Grafana 10.3+. A `__requires__` block declares the minimum Grafana version so import validation catches older instances. |
| Dashboard UID collision with another dashboard | The uid `mctl-telegram-beta` is specific enough to avoid collision; operators can change it on import. |
