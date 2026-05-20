# Grafana dashboard for Beta operations

## Context

Beta tier operators currently have no single, committed Grafana dashboard for
mctl-telegram. Each environment wires ad-hoc panels against the Prometheus
metrics already exported by the service. `internal/metrics/metrics.go` defines
thirteen metric families (HTTP, auth, rate-limiting, MCP tool layer, Telegram
client pool, flood-wait pressure, session lifecycle, and OAuth). A stable
dashboard JSON checked into the repository alongside the code means every
deployment inherits the same operational view and the dashboard rolls forward
with the service automatically.

The scope is a single, importable Grafana JSON file at
`deploy/grafana/mctl-telegram-beta.json`, six panel rows (Traffic, Session pool,
Telegram pressure, Sessions lifecycle, OAuth, Rate limiting), template variables
for `namespace`/`pod`/`instance` filtering, and reference links added to
`docs/hpa.md`.

## User stories

- AS an on-call engineer I WANT a single dashboard showing request rates,
  error ratios, and tool durations SO THAT I can triage an incident without
  building panels from scratch.
- AS a platform operator I WANT the dashboard checked into source control SO
  THAT it is reviewed, versioned, and deployed consistently across environments.
- AS an on-call engineer I WANT each panel to carry a one-line description SO
  THAT I understand what I am looking at without reading the metrics source.
- AS a platform operator I WANT template variables for namespace, pod, and
  instance SO THAT I can scope the dashboard to a single replica or to the
  entire fleet.
- AS a developer I WANT the dashboard JSON referenced from `docs/hpa.md` SO
  THAT readers of the HPA guide can navigate to the operational dashboard
  without a separate search.

## Acceptance criteria (EARS)

- WHEN the file `deploy/grafana/mctl-telegram-beta.json` is imported into a
  Grafana instance connected to a Prometheus data source that scrapes
  mctl-telegram, THE SYSTEM SHALL render all panels without configuration
  errors.
- WHEN a user changes the `namespace`, `pod`, or `instance` template variable,
  THE SYSTEM SHALL filter every panel query to the selected scope.
- WHILE the dashboard is open, THE SYSTEM SHALL display panels grouped into six
  named rows: Traffic, Session pool, Telegram pressure, Sessions lifecycle,
  OAuth, and Rate limiting.
- WHEN a panel is viewed in Grafana, THE SYSTEM SHALL display a non-empty
  description string explaining what the panel measures.
- THE SYSTEM SHALL include a Traffic row containing: `mctl_http_requests_total`
  rate by route and status_code; `mctl_tool_invocations_total` rate by tool;
  `mctl_tool_invocation_duration_seconds` p50/p95/p99 by tool.
- THE SYSTEM SHALL include a Session pool row containing:
  `mctl_telegram_client_pool_size` vs `mctl_telegram_pool_capacity`; pool
  utilization percentage derived from those two gauges;
  `mctl_telegram_client_errors_total` rate.
- THE SYSTEM SHALL include a Telegram pressure row containing:
  `mctl_telegram_flood_wait_events_total` rate by tool.
- THE SYSTEM SHALL include a Sessions lifecycle row containing:
  `mctl_sessions_active` gauge; `mctl_sessions_connected_total` rate;
  `mctl_sessions_revoked_total` rate by reason.
- THE SYSTEM SHALL include an OAuth row containing:
  `mctl_oauth_pending_auth_size` gauge; `mctl_auth_failures_total` rate by
  reason.
- THE SYSTEM SHALL include a Rate limiting row containing:
  `mctl_rate_limit_events_total` rate by identity_kind.
- IF `mctl_telegram_pool_capacity` is -1 (uncapped pool) THEN THE SYSTEM SHALL
  render the utilization panel without a divide-by-zero error (the expression
  must guard against the -1 sentinel).
- WHEN `docs/hpa.md` is read, THE SYSTEM SHALL contain a reference link to
  `deploy/grafana/mctl-telegram-beta.json`.

## Out of scope

- Alert routing and PrometheusRule manifests (covered by a separate issue).
- SLO burn-rate panels (covered by a separate issue).
- Grafana provisioning YAML or folder configuration — the file is importable
  manually or via any existing provisioning pipeline; this issue does not own
  that pipeline.
- Changes to Go source code or metric definitions.

## Open questions

1. The issue body lists `http_requests_total` (no prefix) in the Traffic row,
   but the registered metric name in `internal/metrics/metrics.go` line 74 is
   `mctl_http_requests_total`. This proposal uses `mctl_http_requests_total`.
   Confirm there is no secondary un-prefixed counter.
2. The `namespace`, `pod`, and `instance` labels are not emitted by the Go
   process itself; they are added by the Prometheus Operator PodMonitor
   relabeling rules. The dashboard assumes standard Kubernetes PodMonitor label
   injection. If a non-Kubernetes scrape target is used, those variables will
   not filter correctly.
3. The Prometheus data source UID is unknown at author time. The dashboard JSON
   will use a named input (`DS_PROMETHEUS`) with `__inputs__` so operators can
   map it to their environment's data source on import without editing JSON.
4. No deployment README file (`deploy/README.md`) exists in the clone. The
   issue requests a reference "from any deployment README that exists"; this
   proposal adds the link only to `docs/hpa.md`. If a deployment README is
   added later it should also reference the dashboard.
