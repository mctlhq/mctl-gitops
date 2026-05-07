# Design: incident-auto-cleanup-phase4a-metrics-wiring

## Current state

`mctl-agent` does not export Prometheus metrics. `go.mod` has no
`github.com/prometheus/client_golang` dependency. The chi router at
`internal/api/router.go` exposes a narrow JSON metrics endpoint at
`/api/v1/skills/{name}/metrics` for skill introspection only.

`internal/monitor/poller.go` `resolveStale()` (Phase 1) emits
`slog.Info("poller: auto-resolved stale ticket", ...)` for `StatusOpen`
and `slog.Info("poller: stale TTL resolved", ...)` for
`StatusAnalyzing` / `StatusFixProposed` on every successful
`store.ResolveByID` / `store.ResolveByIDFromStatus` return — but
neither resolution emits a metric.

`mctl-api` shows the exact pattern this proposal mirrors:

- `internal/api/router.go:31-32` imports
  `github.com/prometheus/client_golang/prometheus` and
  `github.com/prometheus/client_golang/prometheus/promhttp`.
- Line 108 mounts `r.Handle("/metrics", promhttp.Handler())` on the
  shared HTTP server.
- Lines 256-262 exempt `/metrics` from the audit-logging middleware
  via a small `infraPaths` map: `{"/healthz": true, "/readyz":
  true, "/metrics": true}`.
- gitops `bootstrap/templates/mctl-platform/mctl-api-monitor.yaml`
  declares a standalone `ServiceMonitor` named `mctl-api` in the
  `monitoring` namespace, selecting on
  `app.kubernetes.io/name: mctl-api`, scraping port `http` (8080)
  on path `/metrics` every 30s.

## Proposed solution

### Part 1: Add the dependency

`go.mod` gains `github.com/prometheus/client_golang` as a direct
dependency. The implementer runs `go get
github.com/prometheus/client_golang@latest` followed by `go mod tidy`
and commits the resulting `go.mod` / `go.sum` updates.

### Part 2: New `internal/metrics` package — single counter

A new file `internal/metrics/metrics.go`:

```go
package metrics

import (
    "github.com/prometheus/client_golang/prometheus"
    "github.com/prometheus/client_golang/prometheus/promauto"
)

// StaleTTLResolved counts tickets auto-resolved by Phase 1's stale-TTL
// GC, labelled by the ticket's status at the moment of resolution
// (open, analyzing, or fix_proposed). Phase 4b will add the remaining
// five handles to this package.
var StaleTTLResolved = promauto.NewCounterVec(
    prometheus.CounterOpts{
        Name: "mctl_agent_stale_ttl_resolved_total",
        Help: "Tickets auto-resolved by the stale-TTL GC, by previous status.",
    },
    []string{"status"},
)
```

`promauto.NewCounterVec` registers against the default Prometheus
registry as a side effect of package init. Any package that imports
`internal/metrics` ensures the metric appears at `/metrics`. Phase
4a achieves this transitively via `internal/api/router.go` (Part 3)
and `internal/monitor/poller.go` (Part 4) both importing the new
package.

### Part 3: Mount `/metrics` on the chi router

In `internal/api/router.go`:

1. Add imports for `prometheus/client_golang/promhttp` and the new
   `mctl-agent/internal/metrics` package (the latter ensures `init()`
   runs even on test binaries that exercise only the router).
2. Mount the route at top level alongside `/healthz` / `/readyz`:
   ```go
   r.Handle("/metrics", promhttp.Handler())
   ```
3. Add `/metrics` to the existing infrastructure-paths exemption set
   so audit-logging middleware does not consume the response body
   on every scrape (mirror mctl-api at lines 256-262).

### Part 4: Increment the counter in `resolveStale()`

`internal/monitor/poller.go` `resolveStale()` increments the counter
on each successful resolution:

```go
import "github.com/mctlhq/mctl-agent/internal/metrics"
// ...
if t.Status == ticket.StatusOpen {
    resolved, err := p.store.ResolveByID(t.ID)
    // ... existing error / no-op handling ...
    if resolved {
        metrics.StaleTTLResolved.WithLabelValues(string(t.Status)).Inc()
        slog.Info(/* existing log */)
    }
} else {
    resolved, err := p.store.ResolveByIDFromStatus(t.ID, t.Status, reason)
    // ... existing error / no-op handling ...
    if resolved {
        metrics.StaleTTLResolved.WithLabelValues(string(t.Status)).Inc()
        slog.Info(/* existing log */)
    }
}
```

The increment is gated on the `resolved == true` return so that a
concurrent transition (ticket moved out from under the GC by the
pipeline) does not inflate the counter.

### Part 5: ServiceMonitor in gitops

A new file `platform-gitops/bootstrap/templates/mctl-platform/mctl-agent-monitor.yaml`,
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
NOT used — that template expects a separate `metrics` port (default
9090) and would require service / container changes. Mirroring the
mctl-api standalone-ServiceMonitor pattern is simpler and requires
no chart edits.

### Part 6: Tests

Two tests, both small:

- **`internal/api/router_test.go` `TestMetricsEndpoint`** (new
  function, may be added to existing file or in a new
  `router_metrics_test.go`):
  - Build the test router via the same constructor used by the
    rest of the package's tests.
  - Issue a `GET /metrics`.
  - Assert HTTP 200.
  - Assert `Content-Type` header begins with `text/plain` (the
    Prometheus exposition format negotiates between
    `version=0.0.4` and OpenMetrics; both start with `text/plain`).
  - Assert response body contains the literal string
    `mctl_agent_stale_ttl_resolved_total`.

- **`internal/monitor/poller_test.go`** — extend ONE existing
  Phase 1 happy-path test (e.g.
  `TestPollerResolvesStaleAnalyzingTicket`) with a counter
  assertion using
  `github.com/prometheus/client_golang/prometheus/testutil`:
  ```go
  before := testutil.ToFloat64(metrics.StaleTTLResolved.WithLabelValues("analyzing"))
  // ... existing test body ...
  after := testutil.ToFloat64(metrics.StaleTTLResolved.WithLabelValues("analyzing"))
  if after-before != 1 {
      t.Errorf("StaleTTLResolved{analyzing}: delta = %f, want 1", after-before)
  }
  ```
  Only ONE existing test extended in 4a — not all three Phase 1
  status variants. Phase 4b adds the rest plus assertions for the
  other counters. This keeps the implementer's test-edit budget
  tight.

Existing Phase 1/2/3 tests not touching the metrics layer must keep
passing without modification.

## Alternatives

### (a) Add all six metrics in one PR (the original Phase 4)

Already attempted; hit $3 implementer budget cap before tests
landed. Rejected as the empirical reason for this proposal.

### (b) Use OpenTelemetry instead of Prometheus

Cluster scraper is VictoriaMetrics speaking Prometheus protocol;
adding an OTLP collector hop is overkill for one service.
Rejected.

### (c) Mount `/metrics` on a separate port (9090)

Matches the base-service chart's `metrics.enabled` defaults but
requires Service / Deployment / NetworkPolicy changes. mctl-api's
single-port pattern is cleaner. Rejected.

### (d) Pre-register the single counter's three label values

`promauto.NewCounterVec` does not surface label combinations until
`WithLabelValues` is called. Pre-registering would emit
`mctl_agent_stale_ttl_resolved_total{status="open"} 0` etc. on
first scrape so `rate()` queries cover from t=0. The single
counter is small enough that operators can wait for the first
real resolution to populate it; Phase 4b adds the more elaborate
`PreRegister()` for the larger set.

## Platform impact

- **Database:** none. No schema changes.
- **API:** one new public route `/metrics`. No authentication
  required (cluster network policy enforces).
- **Network:** one extra scrape per 30s from the cluster's
  VictoriaMetrics scraper. Response payload is currently <2 KB
  with one counter.
- **Memory / CPU:** Prometheus collectors are essentially free.
  One increment per Phase 1 resolution adds nanoseconds.
- **Observability:** the agent becomes scrapable; Phase 4b layers
  more metrics; a Grafana dashboard follows in a later proposal.
- **Configuration:** none new. No env vars introduced; metrics are
  always-on. Future opt-out can be added later if needed.
- **Backwards compatibility:** existing routes, log lines, and
  CLI flags unchanged. The new `/metrics` endpoint is purely
  additive.
- **Failure modes:**
  - Increment under concurrent `Inc()` is atomic in
    `client_golang`; no panic risk.
  - Double-registration is impossible because there's only one
    metric handle declared at package level via `promauto`.
  - If `/metrics` HTTP returns 5xx for any reason (it shouldn't),
    VictoriaMetrics records a scrape error but does not retry
    unduly.
