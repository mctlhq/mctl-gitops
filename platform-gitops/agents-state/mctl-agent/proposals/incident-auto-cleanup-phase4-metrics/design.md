# Design: incident-auto-cleanup-phase4-metrics

## Current state

`mctl-agent` does not expose Prometheus metrics. `go.mod` does not
import `prometheus/client_golang`. The chi router at
`internal/api/router.go` only mounts a narrow JSON metrics endpoint
for skill introspection at `/api/v1/skills/{name}/metrics`.

`mctl-api` shows the pattern we will follow:

- `internal/api/router.go:31-32` imports `prometheus/client_golang`
  and `prometheus/client_golang/promhttp`.
- Line 108 mounts `r.Handle("/metrics", promhttp.Handler())` directly
  on the same router, on the same port (8080).
- Lines 256-262 exempt `/metrics` from the per-request audit-logging
  middleware so scrape requests do not pollute the audit trail.
- gitops `bootstrap/templates/mctl-platform/mctl-api-monitor.yaml`
  defines a standalone `ServiceMonitor` that scrapes port `http`
  (8080) on path `/metrics` every 30s.

## Proposed solution

### Part 1: Wire `prometheus/client_golang` in mctl-agent

`go.mod` gains `github.com/prometheus/client_golang` as a direct
dependency. Run `go mod tidy` in the implementer step.

A new package `internal/metrics` defines the registry and the
metric handles:

```go
package metrics

import (
    "github.com/prometheus/client_golang/prometheus"
    "github.com/prometheus/client_golang/prometheus/promauto"
)

var (
    StaleTTLResolved = promauto.NewCounterVec(
        prometheus.CounterOpts{
            Name: "mctl_agent_stale_ttl_resolved_total",
            Help: "Tickets auto-resolved by the stale-TTL GC, by previous status.",
        },
        []string{"status"},
    )

    OrphanPruned = promauto.NewCounter(
        prometheus.CounterOpts{
            Name: "mctl_agent_orphan_pruned_total",
            Help: "Tickets auto-resolved by orphan pruning (service no longer in inventory).",
        },
    )

    AMReconcileResolved = promauto.NewCounter(
        prometheus.CounterOpts{
            Name: "mctl_agent_am_reconcile_resolved_total",
            Help: "Tickets auto-resolved by AlertManager fingerprint reconciliation.",
        },
    )

    CleanupSkipped = promauto.NewCounterVec(
        prometheus.CounterOpts{
            Name: "mctl_agent_cleanup_skipped_total",
            Help: "Cleanup passes short-circuited by safety guards.",
        },
        []string{"reason"},
    )

    AMRequestDuration = promauto.NewHistogramVec(
        prometheus.HistogramOpts{
            Name:    "mctl_agent_am_request_duration_seconds",
            Help:    "AlertManager /api/v2/alerts request duration.",
            Buckets: prometheus.DefBuckets, // 5ms..10s; AM should land well within
        },
        []string{"outcome"},
    )

    OpenTickets = promauto.NewGaugeVec(
        prometheus.GaugeOpts{
            Name: "mctl_agent_open_tickets",
            Help: "Non-terminal tickets by status and source.",
        },
        []string{"status", "source"},
    )
)

// PreRegister forces label combinations to appear at zero on first
// scrape so that rate() / increase() queries cover the full series
// from t=0 instead of only after the first increment.
func PreRegister() {
    for _, st := range []string{"open", "analyzing", "fix_proposed"} {
        StaleTTLResolved.WithLabelValues(st).Add(0)
    }
    for _, r := range []string{"empty_inventory", "am_unknown", "am_empty_set", "am_fetch_error"} {
        CleanupSkipped.WithLabelValues(r).Add(0)
    }
    for _, o := range []string{"success", "http_error", "decode_error", "transport_error"} {
        AMRequestDuration.WithLabelValues(o).Observe(0) // emits an initial histogram bucket entry
    }
}
```

Counters and label sets stay tight — high-cardinality labels (tenant,
service, alertname) are deliberately excluded to avoid Prometheus
cardinality explosions. Tenant breakdown for orphan/AM resolutions
goes to logs, not metrics.

### Part 2: Mount `/metrics` and wire callers

`internal/api/router.go`:

```go
r.Handle("/metrics", promhttp.Handler())
```

mounted at the top level. Existing handlers untouched.

Each cleanup pass increments its counter where it currently emits its
`slog.Info` log line:

- `internal/monitor/poller.go` `resolveStale`:
  - On successful resolve: `metrics.StaleTTLResolved.WithLabelValues(string(t.Status)).Inc()`
  - On `state.allUnknown` short-circuit (existing log absent — add one): `metrics.CleanupSkipped.WithLabelValues("am_unknown").Inc()` — wait, that's the orphan-prune path. The stale-TTL pass has no allUnknown gate today. Skip in this pass.
- `internal/monitor/poller.go` `pruneOrphans`:
  - Empty inventory guard:
    `metrics.CleanupSkipped.WithLabelValues("empty_inventory").Inc()`
  - allUnknown short-circuit (no log today; add `slog.Warn` AND
    counter): `metrics.CleanupSkipped.WithLabelValues("am_unknown").Inc()`.
    Note: the existing code returns silently here; this proposal adds
    the log line for symmetry with the empty-inventory guard.
  - On successful resolve: `metrics.OrphanPruned.Inc()`
- `internal/monitor/poller.go` `reconcileWithAlertManager`:
  - Empty active set: `metrics.CleanupSkipped.WithLabelValues("am_empty_set").Inc()`
  - Fetch error: `metrics.CleanupSkipped.WithLabelValues("am_fetch_error").Inc()`
  - On successful resolve: `metrics.AMReconcileResolved.Inc()`
- `internal/monitor/alertmanager_client.go` `ActiveFingerprints`:
  - Wrap the request with `time.Now()` then
    `metrics.AMRequestDuration.WithLabelValues(outcome).Observe(time.Since(start).Seconds())`
    where outcome is determined by the error path taken.

For the open-tickets gauge: extend the poll cycle (after the three
cleanup passes complete) with a call to `store.OpenTicketBreakdown()`
returning a `map[StatusSourcePair]int`. The metric is reset and
re-set on each cycle to handle decreasing counts:

```go
metrics.OpenTickets.Reset()
for k, v := range breakdown {
    metrics.OpenTickets.WithLabelValues(k.Status, k.Source).Set(float64(v))
}
```

Add a small store helper that runs a single grouped SQL query:

```go
func (s *Store) OpenTicketBreakdown() (map[StatusSourcePair]int, error) {
    // SELECT status, source, COUNT(*) FROM tickets
    // WHERE status NOT IN ('resolved', 'suppressed')
    // GROUP BY status, source
}
```

`PreRegister()` is called in `cmd/agent/main.go` right after the
metrics package is first imported (effectively when `init()` runs
under promauto), and an explicit call is made in main to lock in the
zero-baseline labels listed in Part 1.

### Part 3: ServiceMonitor in gitops

New file
`platform-gitops/bootstrap/templates/mctl-platform/mctl-agent-monitor.yaml`,
mirroring `mctl-api-monitor.yaml`:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: mctl-agent
  namespace: monitoring
  labels:
    release: monitoring
spec:
  selector:
    matchLabels:
      app.kubernetes.io/instance: admins-mctl-agent
      app.kubernetes.io/name: base-service
  namespaceSelector:
    matchNames:
      - admins
  endpoints:
    - port: http
      path: /metrics
      interval: 30s
```

The base-service Helm chart's existing `metrics.enabled` toggle is
**not** used — that template expects a separate `metrics` port
(default 9090) and would require service+container changes. Mirroring
the mctl-api standalone-ServiceMonitor pattern is simpler and matches
existing operator habit.

### Part 4: Tests

- `internal/metrics/metrics_test.go` — verify all expected metrics
  are registered, label sets match the AC, and `PreRegister()` emits
  zero-baseline series.
- `internal/monitor/poller_test.go` — extend each existing
  Phase 1/2/3 happy-path test to assert the corresponding counter
  increments by 1 after the resolution call. Use
  `testutil.ToFloat64()` from `client_golang/prometheus/testutil`.
- `internal/monitor/poller_test.go` — extend the existing guard
  tests (empty inventory, AM error, AM empty set) to assert the
  matching `cleanup_skipped_total` counter increments.
- `internal/api/router_test.go` (or new) — `GET /metrics` returns
  200 with the expected Content-Type and contains
  `mctl_agent_stale_ttl_resolved_total` in the response body.

## Alternatives

### (a) Use OpenTelemetry instead of Prometheus

OTLP push to a collector is more modern but does not match the
existing cluster setup (VictoriaMetrics scrapes Prometheus
endpoints). Adding an OTLP collector hop is overkill for one
service. Rejected.

### (b) Mount `/metrics` on a separate port (9090)

Matches the base-service chart's defaults but requires Service /
Deployment / NetworkPolicy changes. The mctl-api precedent
(everything on 8080) is good enough and cluster scrape rules
already trust that port. Rejected.

### (c) Use `promauto.With(reg)` to register against a
non-default registry

Provides cleaner test isolation but introduces the burden of
plumbing the registry through every code path that emits a metric.
Default registry is fine for a single-binary agent. Rejected.

### (d) Add high-cardinality labels (tenant, service)

Useful for ad-hoc Grafana drilldowns but creates one time series per
(tenant, service, status) tuple. With ~30 deployed services, the
count is bounded today but grows linearly with cluster scale.
Logging keeps the data accessible without the cardinality cost.
Rejected for v1; revisit if log-based aggregation proves slow.

## Platform impact

- **Database:** none; the new `OpenTicketBreakdown` helper is a
  read-only `SELECT ... GROUP BY` that runs once per poll cycle.
- **API:** one new route `/metrics` exposing the standard Prometheus
  text format on port 8080. Does not require authentication.
- **Network:** one extra scrape per 30s from the cluster's
  VictoriaMetrics scraper. Response size grows linearly with the
  Phase 1/2/3 metric count (≈10 KB at steady state).
- **Memory / CPU:** Prometheus collectors are essentially free (<1
  MB RSS, microseconds per increment). The poll-cycle gauge update
  adds one extra grouped SQL query per cycle — sub-millisecond on
  any reasonable ticket count.
- **Observability:** the agent becomes scrapable; an obvious
  follow-up is a Grafana dashboard JSON in
  `platform-gitops/observability-stack/dashboards/`. Not in this PR.
- **Configuration:** none; metrics are always-on. If a future need
  arises to disable `/metrics`, a `METRICS_ENABLED` env var can be
  added then.
- **Backwards compatibility:** existing routes, log lines, and CLI
  flags are unchanged. The new `/metrics` endpoint is additive.
- **Failure modes:**
  - The metrics package never panics on increment / observe —
    `client_golang` is internally safe under concurrent use.
  - If the metrics registry double-registers on hot reload (does
    not currently happen — the binary restarts on Helm upgrade),
    `promauto` will panic at init time. Acceptable: hot reload is
    not a feature we support.
