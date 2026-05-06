# Design: incident-auto-cleanup-phase3

## Current state

After Phase 1 (mctl-agent 1.8.0), the poller cycle in `internal/monitor/poller.go`
runs two sequential passes per tick:

```go
func (p *Poller) poll() {
    state := p.pollDegraded()
    p.resolveStale(state)
}
```

`pollDegraded()` (lines 100-167) calls `p.client.ListServices()` and
iterates the returned `[]Service` to detect ArgoCD Degraded/Missing
health. It builds a `refreshState` struct that tells `resolveStale()`
which `(tenant, service)` pairs failed their refresh — those are
skipped from the ArgoCDDegraded GC pass to avoid resolving on a
telemetry gap.

Crucially, `pollDegraded()` already has the **complete service inventory**
in its local `services` variable, but it discards everything except the
failure map. The current `refreshState` struct exposes:

```go
type refreshState struct {
    allUnknown     bool
    failedServices map[string]bool
}
```

(approximately — see `poller.go:75-90`).

`resolveStale()` (line 243) iterates `store.ListOpen()` — which returns
all non-terminal tickets — and applies per-status TTL thresholds.

`mctlclient` (`internal/mctlclient/client.go:100-113`) defines
`ListServices()` as an unauthenticated read of the mctl-api
`/api/v1/services` endpoint, returning `[]mctlclient.Service` with
`Team` and `App` fields plus image/revision metadata. mctl-api itself
is the source of truth for "what is deployed where" — it queries the
ArgoCD Application list and presents that as services.

## Proposed solution

### Part 1: Extend `refreshState` with the known-services set

Add one field that captures the service inventory:

```go
type refreshState struct {
    allUnknown      bool
    failedServices  map[string]bool
    knownServices   map[string]bool   // key: "tenant/service"
}
```

`pollDegraded()` populates `knownServices` while it iterates the
`services` slice it already owns — no new HTTP call, no new structure,
just a second map fed from the same loop:

```go
known := make(map[string]bool, len(services))
for _, svc := range services {
    if svc.Team == "" || svc.App == "" {
        continue
    }
    known[svc.Team+"/"+svc.App] = true
    // ... existing pollDegraded logic stays unchanged ...
}
return refreshState{allUnknown: false, failedServices: failed, knownServices: known}
```

When `ListServices()` itself fails (`allUnknown: true`), `knownServices`
remains nil — that signal alone is enough to short-circuit the new
pass.

### Part 2: Add `pruneOrphans()` and wire it into the cycle

A new method on `Poller`:

```go
func (p *Poller) pruneOrphans(state refreshState) {
    if p.OrphanAfter <= 0 {
        return // operator-disabled
    }
    if state.allUnknown {
        return // service inventory is stale; never resolve on absence alone
    }

    open, err := p.store.ListOpen()
    if err != nil {
        slog.Error("poller: failed to list tickets for orphan pruning", "error", err)
        return
    }

    for _, t := range open {
        // Only non-terminal statuses we actually want to clean.
        switch t.Status {
        case ticket.StatusOpen, ticket.StatusAnalyzing, ticket.StatusFixProposed:
        default:
            continue
        }
        // Manual tickets are operator-owned; never orphan-prune them.
        if t.Source == ticket.SourceManual {
            continue
        }
        if state.knownServices[t.Tenant+"/"+t.Service] {
            continue
        }
        if time.Since(t.UpdatedAt) < p.OrphanAfter {
            continue
        }

        reason := "Auto-resolved: service does not exist (likely synthetic / orphaned alert)"
        resolved, err := p.store.ResolveByIDFromStatus(t.ID, t.Status, reason)
        if err != nil {
            slog.Warn("poller: orphan prune failed", "ticket", t.ID, "err", err)
            continue
        }
        if !resolved {
            slog.Debug("poller: orphan prune no-op, ticket advanced concurrently", "id", t.ID)
            continue
        }
        slog.Info("poller: orphan-pruned",
            "ticket", t.ID, "tenant", t.Tenant, "service", t.Service,
            "status", t.Status, "age", time.Since(t.UpdatedAt).Round(time.Hour))
    }
}
```

Wire into the cycle, after stale-TTL:

```go
func (p *Poller) poll() {
    state := p.pollDegraded()
    p.resolveStale(state)
    p.pruneOrphans(state)
}
```

### Part 3: Config

Add one duration field to `Config` (`internal/config/config.go`)
following the Phase 1 pattern:

```go
AutoResolveOrphanAfter time.Duration // env: AUTO_RESOLVE_ORPHAN_AFTER, default 1h, <=0 disables
```

Wire it through to `Poller.OrphanAfter` in `cmd/agent/main.go` next to
the existing `StaleAfter / AnalyzingAfter / FixProposedAfter`
assignments.

## Alternatives

### (a) Separate `ListServices()` call inside `pruneOrphans()`

Decoupled but pays one extra HTTP roundtrip per cycle and risks two
calls observing different inventory snapshots (unlikely in practice but
meaningless extra surface area). Rejected: reuse is cleaner.

### (b) Resolve immediately on first observation (no grace period)

Setting `AUTO_RESOLVE_ORPHAN_AFTER=0` to mean "instant" would let us
catch synthetic alerts within a single poll cycle. Rejected: at 0
duration we cannot distinguish "service was just created and the
tenant inventory has not yet refreshed in mctl-api" from "service does
not exist". A 1h grace covers the common race; operators who want
faster cleanup can set 5m or 10m as their environment dictates. Using
0 to mean "instant" would also collide with the convention
established in Phase 1 where `<= 0` disables the pass.

### (c) Skip the manual-source guard

A `SourceManual` ticket is created via `Pipeline.TriggerAnalysis` (e.g.
from MCP for an investigation). It typically does name a real service,
but if an operator typo'd a tenant/service it would still be valid to
let the operator clean up rather than auto-resolve. Rejected as a
behaviour change against operator intent — Phase 1 already special-cases
`SourceManual` and Phase 3 should be consistent.

### (d) Drive orphan pruning from mctl-api side

mctl-api could enumerate open incidents and call `mctl_resolve_incident`
for orphans. Rejected: mctl-agent owns the incidents store; routing the
write through mctl-api adds a network hop and authorization layer for
no benefit. The agent already has the inventory it needs locally.

## Platform impact

- **Database:** none. Reuses `tickets.status`, `tickets.updated_at`, the
  existing `ResolveByIDFromStatus` write path, and `store.ListOpen()`
  (already consulted twice per cycle today by stale-TTL — adding a
  third lookup is a few rows in the ticket store, negligible).
- **API:** none. No new HTTP routes, no new mctl-api calls.
- **Network:** none. Reuses the `ListServices()` result already fetched
  by `pollDegraded()`.
- **Memory / CPU:** the new `knownServices` map adds O(N) entries where
  N is the number of deployed services across all tenants — currently
  ~30. Pruning loop is O(M) where M is the open-ticket count.
- **Observability:** one new structured log entry `poller: orphan-pruned`
  with fields `ticket, tenant, service, status, age`.
- **Configuration:** one new optional env var with sensible default
  (1h); existing deployments continue to work without operator action.
- **Backwards compatibility:** does not touch any Phase 1 code paths;
  Phase 1 tests remain valid as-is.
