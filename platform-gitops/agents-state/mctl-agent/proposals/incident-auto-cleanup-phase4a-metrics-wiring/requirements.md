# Phase 4a: minimal Prometheus metrics wiring

## Context

The incident auto-cleanup track shipped in three phases (mctl-agent
1.8.0 / 1.9.0 / 1.10.0). All three emit `slog.Info` lines on
resolution and `slog.Warn` lines on guard activation, but none of
that activity is visible to the cluster's metrics stack
(VictoriaMetrics scraping Prometheus endpoints).

A previous attempt at Phase 4 — a single proposal wiring all six
desired metrics, the `/metrics` endpoint, ServiceMonitor, helpers,
and counter assertions across ~10 tests — exhausted the implementer
sub-agent's $3 per-proposal budget cap mid-flight. The implementer
had completed `go build ./...` cleanly but ran out of budget at
`go vet ./...`, never got to commit-and-push, and the branch was
discarded.

Phase 4a is the first half of a deliberate two-PR split. It wires
the bare minimum so that mctl-agent has a live `/metrics` endpoint
exposing one Prometheus counter and a `ServiceMonitor` causes
VictoriaMetrics to scrape it. Phase 4b then layers the remaining
five metric handles on top without re-doing the wiring.

This split keeps each implementer run comfortably under the $3 cap
(empirical reference: Phase 1 PR #11 and Phase 3 PR #12 each landed
4-5 modified files within budget).

## User stories

- AS an on-call SRE I WANT mctl-agent's `/metrics` endpoint to be
  scraped by VictoriaMetrics SO THAT a Grafana panel can be built
  on top of `mctl_agent_*` series without further infrastructure
  changes.
- AS a platform engineer I WANT the first counter
  (`mctl_agent_stale_ttl_resolved_total{status}`) to be live in
  production SO THAT the cleanup track's effectiveness becomes
  measurable starting today, even before Phase 4b lands.
- AS a future maintainer I WANT the metrics layer to follow the
  established mctl-api pattern (port `http`, path `/metrics`,
  standalone ServiceMonitor) SO THAT operator habits transfer
  without surprise.

## Acceptance criteria (EARS)

- WHEN the binary starts, THE SYSTEM SHALL register a default
  Prometheus collector and expose `GET /metrics` on the same HTTP
  port as the existing API (8080), returning the standard
  Prometheus text format.
- WHEN a ticket is auto-resolved by `resolveStale()` (Phase 1 GC),
  THE SYSTEM SHALL increment
  `mctl_agent_stale_ttl_resolved_total{status}` exactly once with
  the ticket's previous status as the label (`open`, `analyzing`,
  or `fix_proposed`).
- WHILE Phase 3's `pruneOrphans` and Phase 2's
  `reconcileWithAlertManager` continue to run, THE SYSTEM SHALL
  NOT increment any new metric in this phase — those wirings are
  deferred to Phase 4b.
- WHEN scraping `GET /metrics`, THE SYSTEM SHALL return HTTP 200
  with `Content-Type` starting with `text/plain` and a body that
  contains the metric name `mctl_agent_stale_ttl_resolved_total`.
- WHILE the request hits `/metrics`, THE SYSTEM SHALL bypass any
  per-request audit-logging or body-buffering middleware (matches
  mctl-api's exemption pattern at `internal/api/router.go:256-262`).
- WHEN the implementer adds the new dependency, THE SYSTEM SHALL
  declare `github.com/prometheus/client_golang` as a direct
  dependency in `go.mod` at the latest stable v1 minor and `go mod
  tidy` shall succeed without errors.
- WHILE the cluster runs the new image, THE SYSTEM SHALL allow
  VictoriaMetrics to scrape `/metrics` via a `ServiceMonitor`
  named `mctl-agent` in the `monitoring` namespace selecting the
  pod's port `http` on path `/metrics` every 30 seconds.

## Out of scope (deferred to Phase 4b)

- The other five metrics: `mctl_agent_orphan_pruned_total`,
  `mctl_agent_am_reconcile_resolved_total`,
  `mctl_agent_cleanup_skipped_total{reason}`,
  `mctl_agent_am_request_duration_seconds{outcome}`,
  `mctl_agent_open_tickets{status, source}`.
- `PreRegister()` zero-baseline series (single counter does not
  need pre-registration; Phase 4b adds it for the multi-label
  series).
- `Store.OpenTicketBreakdown()` helper and the gauge update in the
  poll cycle.
- Counter increments inside `pruneOrphans` and
  `reconcileWithAlertManager`.
- Histogram observation in `alertmanager_client.go ActiveFingerprints`.
- Counter assertions across the guard tests (currently 7+ tests
  in `poller_test.go` would need extensions).

## Out of scope (entirely)

- Grafana dashboard JSON / alerting rules — separate concern,
  authored once metrics flow.
- Authentication / authorization on `/metrics` — cluster network
  policy already restricts ingress; matches mctl-api precedent.
- HTTP request metrics for the API surface (request count,
  latency by route).
- Skill-level metrics already exposed at
  `/api/v1/skills/{name}/metrics`.
