# Prometheus metrics for incident auto-cleanup

## Context

The incident auto-cleanup track shipped in three phases (mctl-agent
1.8.0 / 1.9.0 / 1.10.0). Each phase adds a poll-cycle pass — Phase 1
stale-TTL GC, Phase 3 orphan pruning, Phase 2 AlertManager
fingerprint reconciliation — and emits structured `slog` lines on
resolution and on guard activation. None of those passes are
currently visible to the metrics stack.

Operationally this is fine for spot-checks (`kubectl logs | grep
poller:`) but inadequate for trend monitoring:

- Counts by reason (resolved by stale TTL vs orphan vs AM reconcile)
  cannot be aggregated over days from logs without a parser.
- Empty-inventory guard activations on every cycle (visible today
  in Loki) cannot be alerted on.
- AM call failure rate / latency cannot be seen at all — silent on
  success, slog.Warn on error, no histogram of HTTP duration.
- Open-ticket counts by status / source — already in the DB but
  exposing as a gauge gives a free single-glass dashboard.

mctl-api already publishes Prometheus metrics on `/metrics` over the
service's main port (8080); the cluster's VictoriaMetrics k8s-stack
scrapes it via a standalone `ServiceMonitor` at
`bootstrap/templates/mctl-platform/mctl-api-monitor.yaml`. mctl-agent
does **not** wire `prometheus/client_golang` and exposes only a
narrow `/api/v1/skills/{name}/metrics` JSON endpoint for skill-level
introspection. There is no `/metrics` Prometheus endpoint.

This proposal adds a standard Prometheus metrics surface to
mctl-agent and a sibling ServiceMonitor in gitops, mirroring the
mctl-api pattern.

## User stories

- AS an on-call SRE I WANT a Grafana panel showing the rate of
  auto-resolved incidents per reason (stale TTL by status, orphan,
  AM reconcile) SO THAT I can confirm the cleanup track is actually
  doing work and detect regressions.
- AS a platform engineer I WANT to alert on `mctl_agent_open_tickets`
  staying above a threshold SO THAT a wedged self-healing pipeline
  (no resolutions, ticket count climbing) becomes visible without me
  watching logs.
- AS a future maintainer I WANT a histogram of AlertManager call
  duration SO THAT I can spot when AM becomes slow before it starts
  timing out.
- AS an operator I WANT every metric to follow the established
  naming conventions (`mctl_agent_*`, snake_case, `_total` suffix on
  counters) SO THAT existing Grafana dashboards and alerting
  templates remain consistent.

## Acceptance criteria (EARS)

- WHEN the binary starts, THE SYSTEM SHALL register a default
  Prometheus collector and expose it at `GET /metrics` on the same
  HTTP port as the existing API (8080).
- WHEN a ticket is auto-resolved by `resolveStale()`, THE SYSTEM
  SHALL increment `mctl_agent_stale_ttl_resolved_total{status}`
  exactly once with the ticket's previous status as the label
  value (`open`, `analyzing`, or `fix_proposed`).
- WHEN a ticket is auto-resolved by `pruneOrphans()`, THE SYSTEM
  SHALL increment `mctl_agent_orphan_pruned_total` exactly once.
- WHEN a ticket is auto-resolved by `reconcileWithAlertManager()`,
  THE SYSTEM SHALL increment `mctl_agent_am_reconcile_resolved_total`
  exactly once.
- WHEN any of the three passes is short-circuited by a guard
  (`empty_inventory`, `am_unknown`, `am_empty_set`,
  `am_fetch_error`), THE SYSTEM SHALL increment
  `mctl_agent_cleanup_skipped_total{reason}` with the matching
  reason label.
- WHILE the AlertManager client issues a request, THE SYSTEM SHALL
  observe the request duration in
  `mctl_agent_am_request_duration_seconds{outcome}` where outcome
  is `success`, `http_error`, `decode_error`, or `transport_error`.
- WHILE the agent runs, THE SYSTEM SHALL update a gauge
  `mctl_agent_open_tickets{status, source}` reflecting the count of
  non-terminal tickets by status and source. Update cadence: on
  every poll cycle (after the cleanup passes have run), so the gauge
  reflects post-cleanup state.
- WHEN scraping `GET /metrics`, THE SYSTEM SHALL return a 200
  response with `text/plain; version=0.0.4` Content-Type and SHALL
  NOT require authentication (existing convention; Phase 4 inherits
  the same router setup).
- WHEN counters are first exposed (after a fresh restart), THE
  SYSTEM SHALL register them with their full label sets so the
  metric appears at zero rather than only after the first
  increment, allowing rate() queries from t=0.

## Out of scope

- Grafana dashboard JSON / alerting rules — separate concern, can be
  authored once metrics are flowing. Mention a short follow-up note
  in `design.md` but do not include in this PR.
- Skill-level metrics already exposed at
  `/api/v1/skills/{name}/metrics` (JSON snapshot) — keep as-is for
  now; converting to Prometheus format is a separate proposal.
- Authentication / authorization on `/metrics` — cluster network
  policy already restricts ingress; matches mctl-api precedent.
- Push-mode (Pushgateway) — pull-only via the existing scrape path.
- HTTP request metrics for the API surface (request count, latency
  by route) — would be useful but is an orthogonal addition; this
  proposal stays focused on the cleanup-track observability.
