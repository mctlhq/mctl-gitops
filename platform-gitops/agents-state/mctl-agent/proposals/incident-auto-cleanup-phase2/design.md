# Design: incident-auto-cleanup-phase2

## Current state

After Phase 1 + Phase 3 (mctl-agent 1.9.0), the poll cycle in
`internal/monitor/poller.go` runs:

```go
func (p *Poller) poll() {
    state := p.pollDegraded()
    p.resolveStale(state)
    p.pruneOrphans(state)
}
```

`pollDegraded()` already enumerates the mctl-api service inventory and
populates `refreshState.knownServices`. `resolveStale()` covers
status-specific TTL (Open/Analyzing/FixProposed). `pruneOrphans()`
covers the synthetic-service case.

The AlertManager webhook handler (`internal/monitor/alerthandler.go`)
decodes the payload into a small struct (`alertManagerPayload` /
`alert`) and creates or touches a ticket. It does **not** decode the
`fingerprint` field from each alert, and the `tickets` table has no
column to hold it. Ticket-to-alert linkage today is a fuzzy match on
`(Tenant, Service, Type)` via `FindDuplicate()`.

The mctl-agent codebase has no AlertManager API client. All outbound
HTTP today goes to mctl-api via `internal/mctlclient`.

The cluster runs `prom/alertmanager:v0.28.1` under VictoriaMetrics
k8s-stack at the service `vmalertmanager-monitoring-victoria-metrics-k8s-stack`
(headless) port 9093, namespace `monitoring`. The `/api/v2/alerts`
endpoint is API-compatible with Prometheus AlertManager and returns
JSON like:

```json
[
  {
    "fingerprint": "311fa035cff4de8b",
    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
    "labels": {"alertname": "CPUThrottlingHigh", "namespace": "...", "pod": "..."},
    "startsAt": "...", "endsAt": "...", "updatedAt": "..."
  },
  ...
]
```

Each alert's `fingerprint` is a stable 16-char hex hash of its
labels — the same fingerprint that AlertManager itself uses as the
primary key in its dispatch / silence / inhibit logic, and the same
one delivered in webhook payloads.

## Proposed solution

### Part 1: Schema migration (in-code)

Following the existing in-code migration pattern at
`internal/ticket/store.go:85-189`, add a column and an index in
`migrate()`:

```go
// inside migrate(), alongside other ensureColumn calls
if err := ensureColumn(ctx, db, dialect, "tickets", "alert_fingerprint", "TEXT"); err != nil {
    return err
}
if err := ensureIndex(ctx, db, dialect, "idx_tickets_alert_fingerprint", "tickets", "alert_fingerprint"); err != nil {
    return err
}
```

(Use whatever `ensureColumn` / `ensureIndex` helpers already exist; if
no `ensureIndex` helper exists, the implementer should add a small
sibling that runs `CREATE INDEX IF NOT EXISTS ...` and is safe under
both SQLite and Postgres.)

The field on the `Ticket` struct in `ticket.go`:

```go
type Ticket struct {
    // ... existing fields ...
    AlertFingerprint string `json:"alert_fingerprint,omitempty"`
}
```

`Create()`, `Update()`, `Get()`, and `ListOpen()` are updated to
read/write the new column. No data migration: the column defaults
to NULL/empty for existing rows.

### Part 2: Persist fingerprint at ticket creation

The webhook payload struct in `alerthandler.go:54-60` adds one field:

```go
type alert struct {
    Fingerprint string            `json:"fingerprint"`
    Status      string            `json:"status"`
    Labels      map[string]string `json:"labels"`
    Annotations map[string]string `json:"annotations"`
    StartsAt    time.Time         `json:"startsAt"`
    EndsAt      time.Time         `json:"endsAt"`
}
```

In `processAlert()` (around line 84), after the existing
`FindDuplicate` / `Touch` logic:

- On a new ticket create, set `t.AlertFingerprint = a.Fingerprint`.
- On a duplicate touch, update the column to the latest fingerprint
  (defensive — AM can in theory rotate it; in practice it is
  deterministic for the same labels).

The `store.Touch(id)` helper gains an optional fingerprint argument
(or a sibling `TouchWithFingerprint(id, fp)`); the simpler choice is
just to do `Update(ticket{AlertFingerprint: fp, ...})`.

### Part 3: AlertManager client (new file)

`internal/monitor/alertmanager_client.go`:

```go
type AlertManagerClient struct {
    BaseURL string
    Timeout time.Duration
    HTTP    *http.Client // injectable for tests
}

type amAlert struct {
    Fingerprint string `json:"fingerprint"`
    Status struct {
        State string `json:"state"`
    } `json:"status"`
}

// ActiveFingerprints returns the set of fingerprints for currently
// active, non-silenced alerts. Returns (nil, err) on any error —
// callers MUST treat that as "do not act on absence".
func (c *AlertManagerClient) ActiveFingerprints(ctx context.Context) (map[string]struct{}, error) {
    ctx, cancel := context.WithTimeout(ctx, c.Timeout)
    defer cancel()
    url := c.BaseURL + "/api/v2/alerts?active=true&silenced=false"
    req, _ := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
    req.Header.Set("User-Agent", "mctl-agent/" + Version)
    resp, err := c.HTTP.Do(req)
    if err != nil { return nil, err }
    defer resp.Body.Close()
    if resp.StatusCode/100 != 2 {
        return nil, fmt.Errorf("alertmanager: HTTP %d", resp.StatusCode)
    }
    var alerts []amAlert
    if err := json.NewDecoder(resp.Body).Decode(&alerts); err != nil {
        return nil, fmt.Errorf("alertmanager: decode: %w", err)
    }
    out := make(map[string]struct{}, len(alerts))
    for _, a := range alerts {
        if a.Fingerprint != "" && a.Status.State == "active" {
            out[a.Fingerprint] = struct{}{}
        }
    }
    return out, nil
}
```

Stdlib `net/http` only — no new go.mod entries.

### Part 4: Config

Three new fields on `Config` (in `internal/config/config.go`):

```go
AlertManagerURL    string        // env: ALERTMANAGER_URL; default per below
AMReconcileEnabled bool          // env: AM_RECONCILE_ENABLED; default true
AMReconcileTimeout time.Duration // env: AM_RECONCILE_TIMEOUT; default 10s
AMReconcileMinAge  time.Duration // env: AM_RECONCILE_MIN_AGE; default 15m
```

Default URL:
`http://vmalertmanager-monitoring-victoria-metrics-k8s-stack.monitoring.svc:9093`
(verified in cluster on 2026-05-06; no auth needed).

Wire to the Poller in `cmd/agent/main.go` next to the existing
`p.OrphanAfter / p.StaleAfter / p.AnalyzingAfter / p.FixProposedAfter`
assignments. The poller gets a `*AlertManagerClient` field constructed
from the URL + timeout + a shared `http.Client`.

### Part 5: Reconciliation pass in poll cycle

```go
func (p *Poller) poll() {
    state := p.pollDegraded()
    p.resolveStale(state)
    p.pruneOrphans(state)
    p.reconcileWithAlertManager(context.Background())
}
```

`reconcileWithAlertManager()`:

```go
func (p *Poller) reconcileWithAlertManager(ctx context.Context) {
    if !p.AMReconcileEnabled { return }
    if p.amClient == nil       { return } // not configured
    active, err := p.amClient.ActiveFingerprints(ctx)
    if err != nil {
        slog.Warn("poller: AM reconcile skipped, fetch failed", "err", err)
        return
    }
    if len(active) == 0 {
        slog.Warn("poller: AM reconcile skipped, empty active alert set")
        return
    }

    open, err := p.store.ListOpen()
    if err != nil { return }

    for _, t := range open {
        if t.Source != ticket.SourceAlertManager { continue }
        if t.AlertFingerprint == ""               { continue } // pre-Phase-2
        switch t.Status {
        case ticket.StatusOpen, ticket.StatusAnalyzing, ticket.StatusFixProposed:
        default:
            continue
        }
        if _, stillFiring := active[t.AlertFingerprint]; stillFiring {
            continue
        }
        if time.Since(t.UpdatedAt) < p.AMReconcileMinAge {
            continue // age gate against transient flap windows
        }
        reason := fmt.Sprintf(
            "Auto-resolved by AM reconcile (fingerprint=%s, last_seen_active=%s)",
            t.AlertFingerprint, t.UpdatedAt.Format(time.RFC3339),
        )
        resolved, err := p.store.ResolveByIDFromStatus(t.ID, t.Status, reason)
        if err != nil {
            slog.Warn("poller: AM reconcile resolve failed", "ticket", t.ID, "err", err)
            continue
        }
        if !resolved {
            slog.Debug("poller: AM reconcile no-op, ticket advanced concurrently", "id", t.ID)
            continue
        }
        slog.Info("poller: AM reconcile resolved",
            "ticket", t.ID, "fingerprint", t.AlertFingerprint,
            "status", t.Status, "tenant", t.Tenant, "service", t.Service)
    }
}
```

## Alternatives

### (a) Per-fingerprint two-pass confirmation

Track each fingerprint's "missing for N consecutive cycles" in
in-memory state; resolve only at N >= 2. More precise but adds state
that complicates restart semantics (fresh restart = N reset to 0,
delaying resolution by 5 min). Rejected for v1: the
`AM_RECONCILE_MIN_AGE` (15m default) age gate accomplishes the same
goal — wait long enough that flap windows are bridged — without any
per-ticket state.

### (b) Match on labels instead of fingerprint

Rebuild a fingerprint locally from the labels we already store in
`Evidence`. Avoids the schema migration. Rejected: AM's fingerprint
algorithm is implementation-specific (sorted label hash with a
specific separator); reimplementing it in Go invites schema drift on
AM upgrades. Trusting AM's own field is more robust.

### (c) Subscribe to AM webhook stream instead of polling AM

AlertManager already pushes resolved events via webhook. The reason
this proposal exists is precisely that those pushes are sometimes
missed. Polling is the recovery mechanism, not the primary path.
Rejected as duplication.

### (d) Reuse the same `pollDegraded` HTTP client for AM

The existing client targets mctl-api with mctl-api-specific auth
headers. Building a separate `AlertManagerClient` with no auth and
its own timeout is simpler than overloading the existing client.

## Platform impact

- **Database:** one new TEXT column + one new index. Migration via
  `ensureColumn` is in-code, idempotent, runs at process start,
  works on SQLite and Postgres. No backfill, no downtime. Index
  cardinality matches alert count (~hundreds).
- **API:** no changes to mctl-agent's incoming surface. The webhook
  struct adds one optional field that is a pure addition (Go's
  default JSON decoder accepts new fields).
- **Network:** one outbound HTTP GET per poll cycle (default 5 min)
  to AM. Response payload is currently ~10 KB. Under normal load
  this is negligible compared to the existing mctl-api roundtrips.
- **Memory / CPU:** O(N) map of fingerprints in active set per cycle
  (~hundreds of entries). Loop is O(M) over open tickets.
- **Observability:** three new structured log lines —
  `AM reconcile skipped, fetch failed`,
  `AM reconcile skipped, empty active alert set`,
  `AM reconcile resolved`. No Prometheus metrics yet
  (`prometheus/client_golang` not wired in mctl-agent; separate
  proposal).
- **Configuration:** four new optional env vars with sensible
  defaults validated against the cluster on 2026-05-06.
- **Backwards compatibility:**
  - Pre-Phase-2 tickets have no fingerprint and are skipped by AM
    reconcile; Phase 1 TTL and Phase 3 orphan pruning continue to
    cover them.
  - Phase 1 and Phase 3 paths are not modified.
  - Setting `AM_RECONCILE_ENABLED=false` returns the agent to the
    pre-Phase-2 behaviour for the new pass without affecting the
    other passes.
- **Failure modes:**
  - AM unreachable → no-op (logged) → no resolutions, ever.
  - AM returns wrong-shape JSON → parse error → no-op.
  - AM returns empty array → no-op (could be partial outage).
  - AM returns a fingerprint we never saw on the webhook side →
    we still skip (we only check our own tickets' fingerprints
    against the active set).
