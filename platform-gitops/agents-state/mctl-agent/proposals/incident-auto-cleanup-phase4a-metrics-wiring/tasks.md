# Tasks: incident-auto-cleanup-phase4a-metrics-wiring

- [ ] 1. Add `prometheus/client_golang` dependency — DoD: run
  `go get github.com/prometheus/client_golang@latest` then
  `go mod tidy`; the resulting `go.mod` declares
  `github.com/prometheus/client_golang` as a direct require at the
  latest stable v1 minor; `go build ./...` succeeds; `go vet
  ./...` is clean.

- [ ] 2. Create `internal/metrics` package with the single counter
  (depends on 1) — DoD: a new file `internal/metrics/metrics.go`
  declares package `metrics` and exports
  ```
  var StaleTTLResolved = promauto.NewCounterVec(
      prometheus.CounterOpts{
          Name: "mctl_agent_stale_ttl_resolved_total",
          Help: "Tickets auto-resolved by the stale-TTL GC, by previous status.",
      },
      []string{"status"},
  )
  ```
  imports are clean (`prometheus`, `promauto`); `go vet ./...`
  remains clean.

- [ ] 3. Mount `/metrics` on the chi router with audit-middleware
  exemption (depends on 2) — DoD: `internal/api/router.go` adds
  `_ "github.com/mctlhq/mctl-agent/internal/metrics"` blank import
  (so the package's `promauto` registration runs even on test
  binaries that exercise only the router) AND
  `"github.com/prometheus/client_golang/prometheus/promhttp"`;
  `r.Handle("/metrics", promhttp.Handler())` is mounted at top
  level alongside `/healthz` / `/readyz`; the existing
  audit-logging / body-buffering middleware (search for the
  `infraPaths` map or the similar `/metrics: true` exemption used
  by mctl-api) is extended to also exempt `/metrics`; `go test
  ./internal/api/... -count=1` is green; `go vet ./...` is clean.

- [ ] 4. Increment the counter in `resolveStale()` for both code
  paths (depends on 2) — DoD: `internal/monitor/poller.go` imports
  the new metrics package; both branches of `resolveStale()` (the
  `t.Status == ticket.StatusOpen` branch using
  `store.ResolveByID`, and the `else` branch using
  `store.ResolveByIDFromStatus`) call
  `metrics.StaleTTLResolved.WithLabelValues(string(t.Status)).Inc()`
  ONLY after a successful `resolved == true` return — never on
  the no-op path or on errors; `go vet ./...` is clean.

- [ ] 5. Add `TestMetricsEndpoint` to the api package (depends on
  3) — DoD: a new test (in the existing
  `internal/api/router_test.go` or a new file) constructs the
  router via the same helper used by other tests in the package,
  issues `GET /metrics`, and asserts:
  - HTTP status 200
  - Response `Content-Type` begins with `text/plain`
  - Response body contains the literal string
    `mctl_agent_stale_ttl_resolved_total`
  the test runs via `go test ./internal/api/... -count=1` and
  passes.

- [ ] 6. Extend ONE existing Phase 1 test with a counter assertion
  (depends on 4) — DoD: pick the first existing happy-path test
  in `internal/monitor/poller_test.go` whose backdated ticket
  status is `analyzing` (likely
  `TestPollerResolvesStaleAnalyzingTicket`); capture the counter
  value via
  `testutil.ToFloat64(metrics.StaleTTLResolved.WithLabelValues("analyzing"))`
  before invoking `p.resolveStale(...)`, capture again after,
  assert the delta is exactly 1; uses
  `github.com/prometheus/client_golang/prometheus/testutil`. Do
  NOT extend the open-status or fix_proposed-status variants in
  4a — those are part of 4b's broader test pass.

- [ ] 7. Add the ServiceMonitor manifest to gitops (depends on
  none of the code tasks — independent) — DoD: a new file
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-agent-monitor.yaml`
  declares a `monitoring.coreos.com/v1 ServiceMonitor` named
  `mctl-agent` in namespace `monitoring`, selecting on
  `app.kubernetes.io/instance: admins-mctl-agent +
  app.kubernetes.io/name: base-service`, with namespace selector
  `admins`, port `http`, path `/metrics`, interval `30s`, label
  `release: monitoring`. The shape mirrors
  `mctl-api-monitor.yaml`.

- [ ] 8. Negative-regression coverage (depends on 4-6) — DoD: all
  existing tests not touching the metrics layer continue to pass
  without modification; `go test ./... -race -v -count=1` is
  green on the PR branch.

## Tests

- [ ] T1. `go test ./... -race -v -count=1` is green.
- [ ] T2. After deploy of the new image, manual sanity:
  `kubectl -n admins port-forward svc/admins-mctl-agent 8080:8080`
  then `curl http://localhost:8080/metrics | grep
  mctl_agent_stale_ttl_resolved_total` returns at least one line
  (initially the help/type comments at zero count).
- [ ] T3. Confirm VictoriaMetrics scrapes the new ServiceMonitor:
  `kubectl -n monitoring port-forward svc/vmagent-monitoring-victoria-metrics-k8s-stack 8429`
  then check `localhost:8429/api/v1/targets` includes the
  `mctl-agent` target in `up=1` state. (Or simply query
  `mctl_agent_stale_ttl_resolved_total` in the cluster's Grafana
  data source after a Phase 1 resolution fires.)

## Rollback

1. Revert the changes to `internal/api/router.go`,
   `internal/monitor/poller.go`. Delete
   `internal/metrics/metrics.go` and any test files added in this
   PR. Run `go mod tidy` to drop
   `github.com/prometheus/client_golang` from `go.mod` if no
   other code references remain.
2. Delete
   `platform-gitops/bootstrap/templates/mctl-platform/mctl-agent-monitor.yaml`
   so VictoriaMetrics stops trying to scrape a non-existent
   route.
3. Redeploy. The pod no longer exposes `/metrics`. No DB schema
   affected.
