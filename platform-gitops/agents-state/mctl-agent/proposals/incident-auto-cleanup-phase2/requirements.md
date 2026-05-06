# Active AlertManager reconciliation by fingerprint

## Context

Phase 1 (mctl-agent 1.8.0, PR #11) extends the stale-ticket TTL GC to
cover `analyzing` (48h) and `fix_proposed` (7d). Phase 3 (1.9.0,
PR #12) adds an orphan pruning pass that resolves tickets whose
`(tenant, service)` is not in the platform service inventory after a
short grace (1h).

The remaining gap is the **legitimate-service-but-alert-cleared-without-resolved-webhook**
case: a real service had a transient pod_crashloop or CPU throttle,
the alert recovered, but AlertManager never sent a `resolved` webhook
to mctl-agent (AM restart, route mis-config, network drop, or
bug). The Phase 1 wall-clock TTL eventually catches it at 24-48h, but
that is far too coarse — by then the daily Telegram digest is
polluted with multi-day-old "incidents" that are no longer real.

Phase 2 closes that gap by **actively asking AlertManager** whether
each ticket's underlying alert is still firing. mctl-agent's poll
loop already runs every 5 minutes; one outbound HTTP call to AM per
cycle is enough to discover stale tickets within minutes of the
underlying alert clearing.

This proposal validated the cluster setup before being seeded:
AlertManager is `prom/alertmanager:v0.28.1` running under the
VictoriaMetrics k8s-stack, addressable in-cluster at
`http://vmalertmanager-monitoring-victoria-metrics-k8s-stack.monitoring.svc:9093`.
The `/api/v2/alerts?active=true&silenced=false` endpoint returns an
array of objects each carrying a stable `fingerprint` field (16-char
hex hash of the alert's labels) and a `status.state` field. No
authentication is required for in-cluster access.

## User stories

- AS an on-call SRE I WANT incidents whose underlying alert has
  cleared in AlertManager to auto-resolve within ~15 minutes SO THAT
  I do not stare at a stale ticket while the system is already
  healthy.
- AS a platform engineer I WANT mctl-agent to refuse to resolve any
  ticket on the basis of a failed/timeout AlertManager call SO THAT a
  monitoring-stack outage does not mass-close real incidents.
- AS an operator I WANT the new behaviour to be opt-out via a single
  env var SO THAT I can disable it cluster-wide if it ever
  misbehaves, without redeploying the binary.
- AS a future maintainer I WANT each AM-driven resolution to record
  the alert fingerprint and the reconciliation timestamp in the
  ticket's analysis SO THAT auditing why a ticket was closed is one
  read.

## Acceptance criteria (EARS)

- WHEN an AlertManager webhook arrives at `POST /api/v1/alerts`, THE
  SYSTEM SHALL extract the `fingerprint` field from each alert in the
  payload and persist it to the ticket row (`tickets.alert_fingerprint`)
  on creation or duplicate-touch.
- WHEN a ticket already exists for a duplicate alert, THE SYSTEM
  SHALL update the persisted fingerprint to the latest value
  observed in case AM has rotated it (rare but defensive).
- WHEN the poll loop completes its existing `pollDegraded` and
  `resolveStale` and `pruneOrphans` passes, THE SYSTEM SHALL run a
  fourth pass `reconcileWithAlertManager` that calls AM's
  `/api/v2/alerts` endpoint and resolves any ticket whose persisted
  fingerprint is not present in the response.
- WHILE the AlertManager call fails (network error, non-2xx HTTP
  response, request timeout exceeded, or response body unparseable),
  THE SYSTEM SHALL skip the pass entirely and SHALL NOT resolve any
  tickets in this cycle.
- WHEN the AlertManager response is parsed successfully but contains
  zero active alerts, THE SYSTEM SHALL skip the resolution loop with
  a `slog.Warn` line — an empty response is indistinguishable from a
  partial outage and must not trigger a mass-resolve.
- WHEN a ticket has a fingerprint older than `AM_RECONCILE_MIN_AGE`
  (default 15 minutes) and the fingerprint is not in the active set,
  THE SYSTEM SHALL resolve it; for younger tickets, THE SYSTEM SHALL
  leave them alone — the age gate prevents resolving an alert during
  a transient flap window between AM evaluations.
- WHEN a ticket's `alert_fingerprint` column is empty (pre-Phase-2
  ticket), THE SYSTEM SHALL skip it for AM reconciliation — Phase 1
  TTL and Phase 3 orphan pruning will eventually clean those.
- IF `AM_RECONCILE_ENABLED` is set to `false`, THE SYSTEM SHALL skip
  the new pass entirely while leaving Phase 1 and Phase 3 passes
  unchanged.
- WHEN `ALERTMANAGER_URL` is unset, THE SYSTEM SHALL default to
  `http://vmalertmanager-monitoring-victoria-metrics-k8s-stack.monitoring.svc:9093`,
  matching the in-cluster service.
- WHEN `AM_RECONCILE_TIMEOUT` is unset, THE SYSTEM SHALL default to
  10 seconds.
- WHEN the resolution succeeds, THE SYSTEM SHALL append `Auto-resolved
  by AM reconcile (fingerprint=<X>, last_seen_active=<UpdatedAt>)` to
  the ticket's analysis field.
- WHILE the new pass runs, THE SYSTEM SHALL only consider tickets
  whose `Source` is `SourceAlertManager` — other sources do not
  carry a meaningful AM fingerprint.

## Out of scope

- Per-fingerprint cooldown / two-pass confirmation. The
  `AM_RECONCILE_MIN_AGE` age gate is a simpler proxy. If empirically
  flap-resolves are observed, a follow-up proposal can add per-ticket
  consecutive-miss tracking.
- Backfilling fingerprints onto pre-Phase-2 tickets. New tickets get
  fingerprints; old ones stay covered by Phase 1 TTL and Phase 3
  orphan pruning.
- Bypassing the regular store write path (no direct SQL UPDATE bulk
  fix; use `ResolveByIDFromStatus` like Phase 1/3).
- Mutual TLS, bearer auth, or any AM auth scheme — current cluster
  setup has none. If/when AM is exposed externally or requires auth,
  a separate proposal can add it.
- Prometheus metrics for AM call latency / resolve count
  (mctl-agent does not yet wire `prometheus/client_golang`; tracked
  separately).
- AlertManager v1 API support — only v2 is supported, matching the
  cluster.
