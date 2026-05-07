# Tasks: incident-auto-cleanup-phase4b-metrics-full

- [ ] 1. Extend `internal/metrics/metrics.go` with five new handles
  — DoD: file declares `OrphanPruned Counter`,
  `AMReconcileResolved Counter`,
  `CleanupSkipped CounterVec{reason}`,
  `AMRequestDuration HistogramVec{outcome}` (using
  `prometheus.DefBuckets`), and
  `OpenTickets GaugeVec{status, source}`, each via `promauto` so
  default-registry registration is automatic. Help strings as
  spelled in `design.md` Part 1. The existing `StaleTTLResolved`
  handle and its `init()` body are NOT removed — both are extended.
  `go build ./...` and `go vet ./...` clean.

- [ ] 2. Extend the existing `init()` for zero-baseline series
  (depends on 1) — DoD: the `init()` block in
  `internal/metrics/metrics.go` (which today only loops the three
  `StaleTTLResolved` status labels) is extended to also pre-populate:
  - `CleanupSkipped`: labels `empty_inventory`, `am_unknown`,
    `am_empty_set`, `am_fetch_error` (call
    `WithLabelValues(reason)` for each — does NOT call `Inc()`).
  - `AMRequestDuration`: labels `success`, `http_error`,
    `decode_error`, `transport_error` (call
    `WithLabelValues(outcome).Observe(0)` for each, so the
    histogram series exists from t=0).

- [ ] 3. Wire counters into `pruneOrphans()` (depends on 1) — DoD:
  in `internal/monitor/poller.go` `pruneOrphans(state refreshState)`:
  - Existing `slog.Warn("poller: orphan prune skipped, service inventory is empty")`
    return path: add
    `metrics.CleanupSkipped.WithLabelValues("empty_inventory").Inc()`
    immediately before the `return`.
  - Existing silent `if state.allUnknown { return }` short-circuit:
    add a new `slog.Warn` line
    `"poller: orphan prune skipped, service inventory unknown"`
    AND
    `metrics.CleanupSkipped.WithLabelValues("am_unknown").Inc()`
    immediately before the `return` (the path is currently silent;
    this proposal adds symmetric logging).
  - Existing `slog.Info("poller: orphan-pruned", ...)` success path:
    add `metrics.OrphanPruned.Inc()` immediately before the
    `slog.Info` (after the `resolved == true` gate).

- [ ] 4. Wire counters into `reconcileWithAlertManager()` (depends
  on 1) — DoD: in
  `internal/monitor/poller.go reconcileWithAlertManager(ctx)`:
  - `slog.Warn("poller: AM reconcile skipped, fetch failed", ...)`
    return path: add
    `metrics.CleanupSkipped.WithLabelValues("am_fetch_error").Inc()`.
  - `slog.Warn("poller: AM reconcile skipped, empty active alert set")`
    return path: add
    `metrics.CleanupSkipped.WithLabelValues("am_empty_set").Inc()`.
  - `slog.Info("poller: AM reconcile resolved", ...)` success
    path: add `metrics.AMReconcileResolved.Inc()` immediately
    before the `slog.Info` (after the `resolved == true` gate).

- [ ] 5. Add request-duration observation in AM client (depends on
  1) — DoD: in
  `internal/monitor/alertmanager_client.go ActiveFingerprints(ctx)`:
  add `start := time.Now()` at the top, declare `outcome :=
  "success"` local variable, set it to `"transport_error"` /
  `"http_error"` / `"decode_error"` immediately before each
  `return nil, fmt.Errorf(...)` site as appropriate (transport
  failure on `httpClient.Do`, non-2xx on status check, JSON decode
  failure on `Decode`), and add a deferred call:
  ```go
  defer func() {
      metrics.AMRequestDuration.WithLabelValues(outcome).Observe(time.Since(start).Seconds())
  }()
  ```
  immediately after `start :=`. Tests should observe exactly one
  observation per call.

- [ ] 6. Add `Store.OpenTicketBreakdown` helper (no dep on 1, can
  ship in parallel) — DoD: `internal/ticket/store.go` declares
  `type StatusSourcePair struct { Status string; Source string }`
  AND
  `func (s *Store) OpenTicketBreakdown() (map[StatusSourcePair]int, error)`
  that runs the grouped SQL query from `design.md` Part 5 via
  `s.rebind(...)` and aggregates into the map. Uses the existing
  status constants (`StatusResolved`, `StatusSuppressed`) inside the
  query string. Returns the map and `rows.Err()`.

- [ ] 7. Update gauge in poll cycle (depends on 1, 6) — DoD: in
  `internal/monitor/poller.go (*Poller).poll()`, after the call to
  `p.reconcileWithAlertManager(ctx)`, add the snippet from
  `design.md` Part 5: call `p.store.OpenTicketBreakdown`, on
  success `metrics.OpenTickets.Reset()` then loop and
  `WithLabelValues(status, source).Set(float64(count))`; on error
  `slog.Warn` and continue.

- [ ] 8. Extend existing happy-path / guard tests with counter
  delta assertions (depends on 3, 4) — DoD: in
  `internal/monitor/poller_test.go`, extend the SEVEN tests
  enumerated in `design.md` Part 6 table. Use the
  `testutil.ToFloat64(metrics.X.WithLabelValues(...))` pattern from
  4a's existing
  `TestPollerResolvesStaleAnalyzingTicket` (already in the file).
  Assertion shape: capture `before` immediately before the
  call-under-test, capture `after` immediately after, assert
  `after-before == 1`. Do NOT extend tests not listed.

- [ ] 9. Add three new tests (depends on 5, 6, 7) — DoD:
  - `TestAMRequestDurationObservesOutcomes` in
    `internal/monitor/alertmanager_client_test.go` — three sub-cases
    (200+valid JSON, 500 response, malformed JSON body), each
    asserts `testutil.CollectAndCount(metrics.AMRequestDuration)`
    delta == 1 around the call.
  - `TestStoreOpenTicketBreakdown` in
    `internal/ticket/store_test.go` — creates three
    `(StatusOpen, SourceAlertManager)` + two
    `(StatusAnalyzing, SourceAlertManager)` + one resolved
    ticket via `store.Create` and direct `Update` for status
    transitions; calls `store.OpenTicketBreakdown()`; asserts the
    map has the two expected non-terminal entries with correct
    counts and excludes the resolved.
  - `TestPollerUpdatesOpenTicketsGauge` in `poller_test.go` —
    create open and analyzing tickets via existing test helpers;
    call `p.poll()` with a mock client (or set
    `p.AMReconcileEnabled = false` and an empty `pollDegraded`
    return so the cleanup passes are no-ops); read
    `testutil.ToFloat64(metrics.OpenTickets.WithLabelValues("open", "alertmanager"))`;
    assert exact value matches the open-ticket count.

- [ ] 10. Cleanup the misplaced gitops file (no code dep) — DoD:
  delete `platform-gitops/bootstrap/templates/mctl-platform/mctl-agent-monitor.yaml`
  from the mctl-agent repo via `git rm`. The canonical copy
  already lives at the same path in mctl-gitops main and is NOT
  affected. Commit message subject: `chore: remove misplaced
  gitops file from Phase 4a`.

- [ ] 11. Negative-regression coverage (depends on 3-9) — DoD: all
  existing tests not touching the metrics layer continue to pass
  without modification; `go test ./... -race -v -count=1` is
  green on the PR branch.

## Tests

- [ ] T1. `go test ./... -race -v -count=1` is green.
- [ ] T2. After deploy: `kubectl -n admins port-forward
  svc/admins-mctl-agent 8080` then `curl http://localhost:8080/metrics
  | grep -E "^mctl_agent_(stale_ttl_resolved|orphan_pruned|am_reconcile_resolved|cleanup_skipped|am_request_duration|open_tickets)"`
  shows all six metric families with at least one series each.
- [ ] T3. Confirm zero-baseline emission: immediately after deploy,
  before any Phase 1/2/3 resolution fires, `curl /metrics` shows
  `mctl_agent_cleanup_skipped_total{reason="empty_inventory"} 0`,
  `mctl_agent_am_request_duration_seconds_count{outcome="success"} 0`,
  etc. — labels enumerated in task 2 are present at zero, not
  missing.

## Rollback

1. Revert all changes to `internal/metrics/metrics.go`,
   `internal/monitor/poller.go`,
   `internal/monitor/alertmanager_client.go`,
   `internal/ticket/store.go`, and the test files.
2. The misplaced `mctl-agent-monitor.yaml` file (deleted in task 10)
   can be restored by reverting the deletion commit if needed —
   though it remains dead bytes; the canonical copy in mctl-gitops
   is untouched by this PR.
3. Redeploy. The `/metrics` endpoint continues to expose only the
   single counter from Phase 4a — Phase 4a is unaffected by
   reverting Phase 4b.
4. No DB schema changes. No env vars added.
