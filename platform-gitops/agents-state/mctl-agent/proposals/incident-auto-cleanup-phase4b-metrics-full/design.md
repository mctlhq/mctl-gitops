# Design: incident-auto-cleanup-phase4b-metrics-full

## Current state

After Phase 4a (mctl-agent 1.11.0):

- `internal/metrics/metrics.go` exports a single
  `StaleTTLResolved CounterVec{status}` registered via `promauto`,
  with an `init()` that pre-populates the three known status
  labels.
- `internal/api/router.go` mounts `r.Handle("/metrics",
  promhttp.Handler())` and blank-imports
  `mctl-agent/internal/metrics` so the registration runs even on
  test binaries.
- `internal/monitor/poller.go` `resolveStale()` increments
  `metrics.StaleTTLResolved.WithLabelValues(string(t.Status)).Inc()`
  on each successful resolve in both the `StatusOpen` and the
  `else` branch.

`internal/monitor/poller.go` `pruneOrphans` (Phase 3) and
`reconcileWithAlertManager` (Phase 2) emit log lines on success and
on guard activation but do not touch any metric.
`internal/monitor/alertmanager_client.go` `ActiveFingerprints` does
not measure request duration.

`internal/ticket/store.go` has no breakdown helper for open tickets
by `(status, source)`.

A misplaced file lives at
`platform-gitops/bootstrap/templates/mctl-platform/mctl-agent-monitor.yaml`
inside the mctl-agent repo — the implementer's sandbox could not
push to mctl-gitops, so the YAML landed in the wrong repo. The
canonical copy is already in mctl-gitops main (`bac7212`). The
mctl-agent-side file is dead bytes.

## Proposed solution

### Part 1: Extend the metrics package

Edit `internal/metrics/metrics.go` to add five new package-level
handles next to the existing `StaleTTLResolved`:

```go
var OrphanPruned = promauto.NewCounter(
    prometheus.CounterOpts{
        Name: "mctl_agent_orphan_pruned_total",
        Help: "Tickets auto-resolved by orphan pruning (service no longer in inventory).",
    },
)

var AMReconcileResolved = promauto.NewCounter(
    prometheus.CounterOpts{
        Name: "mctl_agent_am_reconcile_resolved_total",
        Help: "Tickets auto-resolved by AlertManager fingerprint reconciliation.",
    },
)

var CleanupSkipped = promauto.NewCounterVec(
    prometheus.CounterOpts{
        Name: "mctl_agent_cleanup_skipped_total",
        Help: "Cleanup passes short-circuited by safety guards.",
    },
    []string{"reason"},
)

var AMRequestDuration = promauto.NewHistogramVec(
    prometheus.HistogramOpts{
        Name:    "mctl_agent_am_request_duration_seconds",
        Help:    "AlertManager /api/v2/alerts request duration.",
        Buckets: prometheus.DefBuckets,
    },
    []string{"outcome"},
)

var OpenTickets = promauto.NewGaugeVec(
    prometheus.GaugeOpts{
        Name: "mctl_agent_open_tickets",
        Help: "Non-terminal tickets by status and source.",
    },
    []string{"status", "source"},
)
```

Replace the existing `init()` (which pre-populates only three
`StaleTTLResolved` labels) with a broader `init()` that also
pre-populates:

- `CleanupSkipped`: `empty_inventory`, `am_unknown`,
  `am_empty_set`, `am_fetch_error`
- `AMRequestDuration`: emit a synthetic zero-duration `Observe(0)`
  for each of `success`, `http_error`, `decode_error`,
  `transport_error` so the histogram series appears at first
  scrape.

`OrphanPruned` and `AMReconcileResolved` are bare counters and
appear at zero on first scrape automatically; no pre-population
needed for them.

### Part 2: Wire counters into Phase 3 `pruneOrphans`

In `internal/monitor/poller.go` `pruneOrphans(state refreshState)`:

- After the existing
  `slog.Warn("poller: orphan prune skipped, service inventory is empty")`
  return path, add
  `metrics.CleanupSkipped.WithLabelValues("empty_inventory").Inc()`.
- After the existing `if state.allUnknown { return }` (which is
  currently silent), add a `slog.Warn` line
  `"poller: orphan prune skipped, service inventory unknown"` AND
  `metrics.CleanupSkipped.WithLabelValues("am_unknown").Inc()`.
  The `am_unknown` label is reused across passes to mean "the AM
  / mctl-api inventory state is unreliable for this cycle"; the
  log line distinguishes the two callers.
- On each successful resolution (when `resolved == true` is
  returned from `store.ResolveByIDFromStatus`), add
  `metrics.OrphanPruned.Inc()` immediately before the existing
  `slog.Info "poller: orphan-pruned"` line.

### Part 3: Wire counters into Phase 2 `reconcileWithAlertManager`

In `internal/monitor/poller.go` `reconcileWithAlertManager(ctx)`:

- After
  `slog.Warn("poller: AM reconcile skipped, fetch failed", "err", err)`
  return path, add
  `metrics.CleanupSkipped.WithLabelValues("am_fetch_error").Inc()`.
- After
  `slog.Warn("poller: AM reconcile skipped, empty active alert set")`
  return path, add
  `metrics.CleanupSkipped.WithLabelValues("am_empty_set").Inc()`.
- On each successful resolve (when
  `store.ResolveByIDFromStatus` returns `resolved == true`), add
  `metrics.AMReconcileResolved.Inc()` immediately before the
  existing `slog.Info "poller: AM reconcile resolved"` line.

### Part 4: Wire histogram into AM client

In `internal/monitor/alertmanager_client.go` `ActiveFingerprints(ctx)`:

```go
start := time.Now()
defer func() {
    metrics.AMRequestDuration.WithLabelValues(outcome).Observe(time.Since(start).Seconds())
}()
```

`outcome` is a local string variable initialised to `"success"` and
overwritten before each `return nil, fmt.Errorf(...)` site:

- HTTP do failure (transport / context cancellation): `outcome = "transport_error"`.
- Non-2xx HTTP response: `outcome = "http_error"`.
- JSON decode failure: `outcome = "decode_error"`.

The success path leaves `outcome` at its initial value.

### Part 5: Open-ticket gauge breakdown

Add `Store.OpenTicketBreakdown` helper to `internal/ticket/store.go`:

```go
type StatusSourcePair struct {
    Status string
    Source string
}

func (s *Store) OpenTicketBreakdown() (map[StatusSourcePair]int, error) {
    const q = `
        SELECT status, source, COUNT(*) FROM tickets
        WHERE status NOT IN ('resolved', 'suppressed')
        GROUP BY status, source`
    rows, err := s.db.Query(s.rebind(q))
    if err != nil {
        return nil, err
    }
    defer func() { _ = rows.Close() }()
    out := map[StatusSourcePair]int{}
    for rows.Next() {
        var k StatusSourcePair
        var n int
        if err := rows.Scan(&k.Status, &k.Source, &n); err != nil {
            return nil, err
        }
        out[k] = n
    }
    return out, rows.Err()
}
```

Both `'resolved'` and `'suppressed'` exclusions match
`internal/ticket/ticket.go` constants
(`StatusResolved` / `StatusSuppressed`). `s.rebind` is the existing
helper that handles SQLite vs Postgres placeholder dialect.

In `internal/monitor/poller.go` `(*Poller).poll()`, after all three
cleanup passes, add:

```go
if breakdown, err := p.store.OpenTicketBreakdown(); err == nil {
    metrics.OpenTickets.Reset()
    for k, v := range breakdown {
        metrics.OpenTickets.WithLabelValues(k.Status, k.Source).Set(float64(v))
    }
} else {
    slog.Warn("poller: open-ticket breakdown failed", "err", err)
}
```

The `Reset()` is required so labels for tuples that dropped to zero
are removed from the gauge (e.g. all `analyzing` tickets resolved
this cycle).

### Part 6: Tests

Extend the existing Phase 1/2/3 happy-path and guard tests in
`internal/monitor/poller_test.go` with delta assertions, using the
same `testutil.ToFloat64` pattern from 4a's
`TestPollerResolvesStaleAnalyzingTicket`:

| Existing test | Counter to assert |
|---|---|
| `TestPrunesOrphanTicketAfterGracePeriod` (Phase 3 happy) | `OrphanPruned` delta == 1 (per status case) |
| `TestSkipsOrphanPruneOnEmptyInventory` (Phase 3 guard) | `CleanupSkipped{empty_inventory}` delta == 1 |
| `TestSkipsOrphanPruneWhenInventoryUnknown` (Phase 3 guard) | `CleanupSkipped{am_unknown}` delta == 1 |
| `TestAMReconcileResolvesNonFiringTicket` (Phase 2 happy) | `AMReconcileResolved` delta == 1 |
| `TestAMReconcileResolvesWhenAllFingerprintsAbsent` (Phase 2 happy) | `AMReconcileResolved` delta == 1 |
| `TestAMReconcileSkipsEmptyActiveSet` (Phase 2 guard) | `CleanupSkipped{am_empty_set}` delta == 1 |
| `TestAMReconcileSkipsOnAMError` (Phase 2 guard) | `CleanupSkipped{am_fetch_error}` delta == 1 |

Plus three new tests:

- `TestAMRequestDurationObservesOutcomes` in
  `internal/monitor/alertmanager_client_test.go` — three
  `httptest.NewServer` cases (200+JSON, 500, malformed JSON);
  capture histogram count via
  `testutil.CollectAndCount(metrics.AMRequestDuration)` before /
  after each call to assert exactly one observation per call.
- `TestStoreOpenTicketBreakdown` in `internal/ticket/store_test.go`
  — create three tickets across two `(status, source)` pairs +
  one resolved; call `OpenTicketBreakdown`; assert the map has the
  expected counts and excludes the resolved one.
- `TestPollerUpdatesOpenTicketsGauge` in `poller_test.go` — create
  two open + one analyzing + one resolved ticket; call
  `p.poll()` (mock the AM/inventory clients to no-op); read gauge
  via `testutil.ToFloat64(metrics.OpenTickets.WithLabelValues(...))`;
  assert exact values.

The ticket-store test added to `store_test.go` does NOT require a
file-backed DB — it runs sequentially against the existing
`newTestStore(t)` helper.

### Part 7: Cleanup misplaced gitops file

`git rm
platform-gitops/bootstrap/templates/mctl-platform/mctl-agent-monitor.yaml`
inside the mctl-agent repo. The canonical copy is already in
mctl-gitops main at the same path — committed in `bac7212`. No
runtime impact.

## Alternatives

### (a) Replace the bare `init()` with an exported `PreRegister()`

Slightly cleaner test isolation but adds a wiring task. The
existing 4a pattern (bare `init()` populating known label values)
extends naturally; staying with it keeps the diff focused.

### (b) High-cardinality labels (tenant, service, alertname)

Useful for ad-hoc Grafana drilldowns but creates one time series
per (tenant, service, status) tuple. With ~30 deployed services,
the count is bounded today but grows linearly with cluster scale.
Logging keeps the data accessible without the cardinality cost.
Rejected for v1.

### (c) Per-fingerprint cooldown / two-pass confirmation gate

Outside Phase 4 scope; a future proposal can add it on top of the
AMRequestDuration histogram once we have data on AM latency
patterns.

## Platform impact

- **Database:** none. The new
  `OpenTicketBreakdown` helper is a read-only `SELECT ... GROUP BY`
  that runs once per poll cycle. No schema changes.
- **API:** none. Existing `/metrics` route now returns more lines.
- **Network:** scrape payload grows from ~2 KB (4a) to ~10 KB at
  steady state.
- **Memory / CPU:** Prometheus collectors are essentially free.
  The new gauge is reset and re-set every cycle; cardinality is
  bounded by `count(distinct (status, source))` ≈ 5×3 = 15.
- **Observability:** all six metric names appear in `/metrics` once
  this PR ships; no change to log lines except the new symmetric
  `slog.Warn` for the orphan-prune `am_unknown` guard.
- **Configuration:** no new env vars.
- **Backwards compatibility:** existing routes, log lines (except
  the new symmetric warn), and CLI flags unchanged.
- **Failure modes:**
  - Increment / Observe operations are atomic in `client_golang`;
    no panic risk.
  - Double-registration impossible because all handles are
    declared at package level via `promauto`.
  - `OpenTicketBreakdown` SQL failure logs at `slog.Warn` and the
    cycle proceeds; the gauge retains its previous value (no
    `Reset()` happens), which is acceptable degradation.
