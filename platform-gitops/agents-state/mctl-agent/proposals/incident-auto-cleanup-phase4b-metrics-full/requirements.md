# Phase 4b: remaining metrics on top of Phase 4a

## Context

Phase 4a (mctl-agent 1.11.0, PR #16) wired
`prometheus/client_golang`, mounted `/metrics` on the chi router,
added the single counter `mctl_agent_stale_ttl_resolved_total{status}`,
and committed a sibling `ServiceMonitor` in mctl-gitops. That gives
the cluster's VictoriaMetrics scraper a working endpoint and one
useful counter — but four observable surfaces are still
log-only:

- Phase 3 orphan-prune resolutions (currently
  `slog.Info "poller: orphan-pruned"`).
- Phase 2 AM-reconcile resolutions (currently
  `slog.Info "poller: AM reconcile resolved"`).
- Guard activations across Phase 2 and Phase 3
  (`empty_inventory`, `am_unknown` for orphan prune, `am_empty_set`
  and `am_fetch_error` for AM reconcile — currently `slog.Warn`).
- AlertManager call latency / outcome (Phase 2 client; currently
  unobserved entirely).

Plus one cross-cutting visibility: open-ticket count by status and
source. The data lives in the DB and is trivial to surface as a
gauge updated each poll cycle.

Phase 4b layers all five remaining metric handles on top of the 4a
package, wires them where the corresponding events fire, and adds
matching counter assertions to the existing Phase 1/2/3 happy-path
and guard tests.

This proposal also performs a one-line cleanup: the original
implementer of 4a created the `ServiceMonitor` YAML at the gitops
path inside the mctl-agent repo (the implementer's sandbox can only
push to the matching service repo). The canonical copy was committed
to mctl-gitops directly; the mctl-agent-side stray file is now dead
bytes and is removed here.

## User stories

- AS an on-call SRE I WANT a Grafana panel showing the rate of
  orphan-prune and AM-reconcile resolutions SO THAT I can confirm
  the cleanup track is doing real work, not just stale-TTL.
- AS a platform engineer I WANT to alert on
  `mctl_agent_cleanup_skipped_total{reason="empty_inventory"}` rate
  staying high SO THAT a wedged mctlclient or pollDegraded
  regression becomes visible without me grepping logs.
- AS an operator I WANT a histogram of AlertManager request latency
  SO THAT I can see when AM becomes slow before it starts timing
  out and silently disabling Phase 2.
- AS a future maintainer I WANT a gauge of open tickets by status
  and source SO THAT a wedged self-healing pipeline (no resolutions,
  ticket count climbing) becomes visible at a glance.

## Acceptance criteria (EARS)

- WHEN a ticket is auto-resolved by `pruneOrphans()` (Phase 3),
  THE SYSTEM SHALL increment `mctl_agent_orphan_pruned_total`
  exactly once.
- WHEN a ticket is auto-resolved by `reconcileWithAlertManager()`
  (Phase 2), THE SYSTEM SHALL increment
  `mctl_agent_am_reconcile_resolved_total` exactly once.
- WHEN `pruneOrphans()` short-circuits because the service
  inventory is empty (existing log line
  `"poller: orphan prune skipped, service inventory is empty"`),
  THE SYSTEM SHALL increment
  `mctl_agent_cleanup_skipped_total{reason="empty_inventory"}`.
- WHEN `pruneOrphans()` short-circuits because
  `state.allUnknown == true`, THE SYSTEM SHALL increment
  `mctl_agent_cleanup_skipped_total{reason="am_unknown"}` and emit a
  new `slog.Warn "poller: orphan prune skipped, service inventory
  unknown"` line (the path is currently silent — symmetric logging
  with the empty-inventory guard).
- WHEN `reconcileWithAlertManager()` short-circuits because the AM
  active set is empty (existing log
  `"poller: AM reconcile skipped, empty active alert set"`), THE
  SYSTEM SHALL increment
  `mctl_agent_cleanup_skipped_total{reason="am_empty_set"}`.
- WHEN `reconcileWithAlertManager()` short-circuits because the AM
  call returned an error (existing log
  `"poller: AM reconcile skipped, fetch failed"`), THE SYSTEM SHALL
  increment
  `mctl_agent_cleanup_skipped_total{reason="am_fetch_error"}`.
- WHILE the AlertManager client `ActiveFingerprints(ctx)` issues a
  request, THE SYSTEM SHALL observe the wall-clock duration in
  `mctl_agent_am_request_duration_seconds{outcome}` where outcome
  is `success` (HTTP 2xx + JSON decode OK), `http_error` (non-2xx
  response), `decode_error` (JSON decode failure), or
  `transport_error` (HTTP do failed / context cancelled).
- WHEN the poll cycle has run all three cleanup passes, THE SYSTEM
  SHALL update the gauge `mctl_agent_open_tickets{status, source}`
  with the current per-(status, source) count of non-terminal
  tickets, by calling `metrics.OpenTickets.Reset()` and then
  `WithLabelValues(status, source).Set(float64(count))` for each
  pair returned by a new
  `Store.OpenTicketBreakdown() (map[StatusSourcePair]int, error)`
  helper.
- WHEN the binary starts, THE SYSTEM SHALL pre-register all label
  combinations enumerated in `design.md` Part 2 so that
  `rate()` / `increase()` queries cover the full series from t=0
  on the next scrape.
- WHEN scraping `GET /metrics` after the first poll cycle, THE
  SYSTEM SHALL include all six metric names defined across 4a and
  4b in the response body (`mctl_agent_stale_ttl_resolved_total`,
  `mctl_agent_orphan_pruned_total`,
  `mctl_agent_am_reconcile_resolved_total`,
  `mctl_agent_cleanup_skipped_total`,
  `mctl_agent_am_request_duration_seconds`,
  `mctl_agent_open_tickets`).
- WHILE the implementer cleans up the mctl-agent repo, THE SYSTEM
  SHALL delete the misplaced file
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-agent-monitor.yaml`
  from the mctl-agent repo (the canonical copy already lives at the
  same path in mctl-gitops, committed in `bac7212`).

## Out of scope

- Grafana dashboard JSON / alerting rules — separate proposal once
  metrics are flowing.
- HTTP request metrics for the rest of the API surface (request
  count, latency by route).
- Skill-level metrics already exposed at
  `/api/v1/skills/{name}/metrics` (JSON snapshot) — convert to
  Prometheus separately.
- High-cardinality labels (tenant, service, alertname) — kept on
  log lines instead.
- Authentication / authorization on `/metrics`.
