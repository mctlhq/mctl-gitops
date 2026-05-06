# Tasks: incident-auto-cleanup-phase4-metrics

- [ ] 1. Add `prometheus/client_golang` to `go.mod` and create the
  `internal/metrics` package — DoD: `go.mod` declares
  `github.com/prometheus/client_golang` as a direct dependency at
  the latest stable v1 minor (`go get github.com/prometheus/client_golang@latest`
  + `go mod tidy`); a new file `internal/metrics/metrics.go`
  exports the six handles described in `design.md` Part 1
  (`StaleTTLResolved`, `OrphanPruned`, `AMReconcileResolved`,
  `CleanupSkipped`, `AMRequestDuration`, `OpenTickets`); `promauto`
  is used so registration with the default registry is
  side-effecting; `go vet ./...` is clean.

- [ ] 2. Implement `metrics.PreRegister()` and call it from main —
  DoD: `metrics.PreRegister()` zero-initialises the listed label
  values for `StaleTTLResolved` (3 statuses), `CleanupSkipped` (4
  reasons), and `AMRequestDuration` (4 outcomes); `cmd/agent/main.go`
  calls it once after `cfg, err := config.Load()` returns
  successfully; `go test ./internal/metrics/...` includes a unit
  test asserting the labels exist at zero on a fresh registry.

- [ ] 3. Mount `/metrics` on the chi router (depends on 1) — DoD:
  `internal/api/router.go` adds `r.Handle("/metrics",
  promhttp.Handler())` at the top level alongside `/healthz` /
  `/readyz`; the route is exempt from any audit-logging or
  per-request middleware that touches request bodies (matches
  mctl-api's exemption pattern); a smoke test in
  `internal/api/router_test.go` (create if absent) issues
  `GET /metrics`, asserts HTTP 200, asserts `Content-Type` starts
  with `text/plain; version=0.0.4`, and asserts the body contains
  the metric name `mctl_agent_stale_ttl_resolved_total`.

- [ ] 4. Wire counters into Phase 1 `resolveStale` (depends on 1) —
  DoD: `internal/monitor/poller.go` `resolveStale` calls
  `metrics.StaleTTLResolved.WithLabelValues(string(t.Status)).Inc()`
  on every successful `ResolveByID` / `ResolveByIDFromStatus`
  return; the existing test
  `TestPollerResolvesStaleAnalyzingTicket` is extended to assert
  the counter for status `analyzing` increments by 1 (use
  `testutil.ToFloat64`); same for `_open` and `_fix_proposed`
  variants.

- [ ] 5. Wire counters into Phase 3 `pruneOrphans` (depends on 1) —
  DoD: `pruneOrphans` increments
  `metrics.OrphanPruned` on each successful resolution and
  `metrics.CleanupSkipped` with the matching reason
  (`empty_inventory`, `am_unknown`) on each guard short-circuit;
  the `am_unknown` short-circuit also gains a new `slog.Warn` line
  for symmetry with the existing `empty_inventory` warn (not
  currently logged); existing guard tests are extended to assert
  the matching `cleanup_skipped_total{reason}` counter.

- [ ] 6. Wire counters and histogram into Phase 2 reconcile + AM
  client (depends on 1) — DoD:
  `reconcileWithAlertManager` increments
  `metrics.AMReconcileResolved` per resolution and
  `metrics.CleanupSkipped` with reasons `am_empty_set` /
  `am_fetch_error`; `alertmanager_client.go ActiveFingerprints`
  observes request duration in
  `metrics.AMRequestDuration.WithLabelValues(outcome)` where
  outcome is `success` (2xx + parse OK), `http_error` (non-2xx),
  `decode_error` (JSON failure), or `transport_error` (HTTP do
  failed); existing tests are extended to assert the increments.

- [ ] 7. Add `Store.OpenTicketBreakdown` and gauge update in poll
  cycle (depends on 1) — DoD: `internal/ticket/store.go` declares
  `OpenTicketBreakdown() (map[StatusSourcePair]int, error)` running
  one grouped SQL query (`SELECT status, source, COUNT(*) FROM
  tickets WHERE status NOT IN ('resolved', 'suppressed') GROUP BY
  status, source`) and tested in `store_test.go` against multiple
  fixtures; `poller.go` `poll()` calls
  `metrics.OpenTickets.Reset()` then iterates the breakdown
  setting `WithLabelValues(status, source).Set(float64(count))`
  AFTER the three cleanup passes complete; behaviour is exercised
  end-to-end in a poller test that creates 2 open + 1 analyzing
  ticket, runs `poll()`, and asserts the gauge values via
  `testutil.ToFloat64`.

- [ ] 8. Add the ServiceMonitor manifest to gitops (depends on 3) —
  DoD: a new file
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-agent-monitor.yaml`
  declares a `monitoring.coreos.com/v1 ServiceMonitor` named
  `mctl-agent` in namespace `monitoring`, selecting on
  `app.kubernetes.io/instance: admins-mctl-agent +
  app.kubernetes.io/name: base-service`, with namespace selector
  `admins`, port `http`, path `/metrics`, interval `30s`, label
  `release: monitoring`; identical pattern to
  `mctl-api-monitor.yaml`.

- [ ] 9. Negative-regression coverage (depends on 4-7) — DoD:
  existing Phase 1/2/3 tests not touching the metrics layer keep
  passing without modification; `go test ./... -race -v -count=1`
  is green on the PR branch.

## Tests

- [ ] T1. `go test ./... -race -v -count=1` is green.
- [ ] T2. Manual sanity in cluster (after deploy of new image): port-forward
  the pod's 8080 and `curl localhost:8080/metrics` — assert the
  expected metric names appear and counters are at zero or above.
- [ ] T3. After the next poll cycle in a healthy cluster, confirm
  `mctl_agent_open_tickets` is non-zero (the agent always has at
  least the heartbeat / synthetic tickets in some envs) and
  `mctl_agent_cleanup_skipped_total{reason="empty_inventory"}`
  stops growing once the mctlclient app/name fix is in place.

## Rollback

1. Revert the changes to `internal/api/router.go`,
   `internal/monitor/poller.go`,
   `internal/monitor/alertmanager_client.go`,
   `internal/ticket/store.go`, `cmd/agent/main.go`. Delete
   `internal/metrics/` and the test files.
2. Remove `github.com/prometheus/client_golang` from `go.mod` /
   `go.sum` via `go mod tidy`.
3. Delete
   `platform-gitops/bootstrap/templates/mctl-platform/mctl-agent-monitor.yaml`
   (the ServiceMonitor) so Prometheus stops trying to scrape a
   non-existent route.
4. Redeploy. The pod no longer exposes `/metrics`; existing log
   lines remain unchanged; no DB schema affected.
