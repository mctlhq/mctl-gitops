# Design: incident-auto-cleanup-phase1

## Current state

The stale-ticket GC lives in `internal/monitor/poller.go:224-274`,
`(*Poller).resolveStale()`. On every poll cycle (`POLL_INTERVAL`, default
5 minutes) it loops over `store.ListOpen()` and resolves any ticket that
satisfies all three conditions:

1. `t.Status == ticket.StatusOpen` (line 235).
2. `t.Type` is one of the heartbeat-eligible types (`poller.go:182-189`):
   `TypeArgoCDDegraded`, `TypePodCrashloop`, `TypeResourceLimit`,
   `TypeWorkflowFailed`, `TypeGeneric`, `TypeGitHubActionsFailed`.
3. `t.Source` is one of `SourceAlertManager`, `SourcePolling`,
   `SourceGitHubWebhook` (lines 196-200).

Tickets older than `AUTO_RESOLVE_STALE_AFTER` (`internal/config/config.go:103-108`,
default 24h) that satisfy all three are passed to `store.ResolveByID()`
with reason `auto-resolved (stale)`.

`store.ListOpen()` (`internal/ticket/store.go:259-260`) calls
`listByStatus(StatusOpen, StatusAnalyzing, StatusFixProposed,
StatusFixApplied)` — i.e. it already returns every non-terminal ticket.
The current loop simply skips everything that is not `StatusOpen`.

## Proposed solution

Replace the single status check at `poller.go:235` with a status-keyed
threshold table and a switch:

```go
thresholds := map[ticket.Status]time.Duration{
    ticket.StatusOpen:         p.cfg.AutoResolveStaleAfter,
    ticket.StatusAnalyzing:    p.cfg.AutoResolveAnalyzingAfter,
    ticket.StatusFixProposed:  p.cfg.AutoResolveFixProposedAfter,
}

for _, t := range tickets {
    cutoff, ok := thresholds[t.Status]
    if !ok {
        continue // FixApplied / Resolved / Suppressed — out of scope
    }
    if !p.eligibleType(t.Type) || !p.eligibleSource(t.Source) {
        continue
    }
    if time.Since(t.UpdatedAt) < cutoff {
        continue
    }

    age := time.Since(t.UpdatedAt).Round(time.Hour)
    reason := fmt.Sprintf(
        "Auto-resolved by stale TTL GC (status=%s, age=%s, threshold=%s)",
        t.Status, age, cutoff,
    )
    if err := p.store.ResolveByID(ctx, t.ID, reason); err != nil {
        slog.Warn("stale TTL resolve failed", "ticket", t.ID, "err", err)
        continue
    }
    slog.Info("stale TTL resolved",
        "ticket", t.ID, "status", t.Status, "age", age, "threshold", cutoff)
}
```

The eligibility helpers (`eligibleType`, `eligibleSource`) factor out the
existing maps at `poller.go:182-200` so the new code does not duplicate
them.

`AutoResolveStaleAfter` keeps its current semantics (24h default) so
operators that have tuned this env see no change. The two new fields use
defaults chosen for the failure modes observed in production:

| Field | Env var | Default | Rationale |
|-------|---------|---------|-----------|
| `AutoResolveAnalyzingAfter` | `AUTO_RESOLVE_ANALYZING_AFTER` | `48h` | Longer than open: skill pipeline + spec-writer + mentor digest needs time to handle hard cases. Two days is enough to confirm the agent gave up. |
| `AutoResolveFixProposedAfter` | `AUTO_RESOLVE_FIX_PROPOSED_AFTER` | `168h` | A week is generous and matches typical PR-shepherd cadence (cron `30 */2 * * *`). Beyond that the PR is almost certainly abandoned. |

Config wiring follows the existing pattern at `config.go:103-108`:

```go
AutoResolveAnalyzingAfter, err = parseDurationEnv(
    "AUTO_RESOLVE_ANALYZING_AFTER", 48*time.Hour,
)
if err != nil {
    return Config{}, err
}
AutoResolveFixProposedAfter, err = parseDurationEnv(
    "AUTO_RESOLVE_FIX_PROPOSED_AFTER", 168*time.Hour,
)
if err != nil {
    return Config{}, err
}
```

(uses the same helper `parseDurationEnv` that `AUTO_RESOLVE_STALE_AFTER`
uses — name may differ, see existing implementation; the implementer
should reuse whatever helper is already there).

The poller constructor receives the new fields via the existing `cfg`
parameter — no signature changes elsewhere.

## Alternatives

### (a) Single threshold for all non-terminal statuses

Treat `Open`, `Analyzing`, `FixProposed` identically with the existing
24h. Rejected: would resolve `analyzing` tickets that the skill pipeline
is legitimately still working on, and would resolve `fix_proposed`
tickets while their PR review is still in progress. The differing
operational meaning of each status warrants different cutoffs.

### (b) Resolve `fix_proposed` tickets by checking PR state on GitHub

Instead of a wall-clock threshold, query GitHub for the linked PR and
resolve only when the PR is closed without merging. Rejected for Phase 1:
adds GitHub API dependency, rate-limit handling, and a state machine that
is out of proportion to the goal. Phase 2 may revisit this once
`alert_fingerprint` reconciliation infrastructure is in place; for now,
the 7-day cutoff is a coarse but effective safety net.

### (c) Make `AUTO_RESOLVE_ANALYZING_AFTER = 0` mean "off"

Allow operators to disable the new pass entirely by setting the env to
zero. Considered but deferred: the `AUTO_RESOLVE_STALE_AFTER` env does
not have this semantics today, and introducing it inconsistently is more
confusing than helpful. If an operator wants to disable, they can set a
very large value (e.g. `9999h`) until a follow-up adds a uniform
opt-out flag.

## Platform impact

- **Database:** none. Reuses `tickets.status`, `tickets.updated_at`, and
  the existing `ResolveByID` write path.
- **API:** none. No new HTTP routes, no schema changes to the alert
  webhook.
- **Memory / CPU:** negligible. The existing GC already iterates over all
  non-terminal tickets on every cycle; the change adds two small switch
  branches and one log line per resolution.
- **Observability:** new structured log entry `stale TTL resolved` with
  fields `ticket`, `status`, `age`, `threshold` — operators can grep
  these to confirm cleanup behaviour. No new Prometheus metric (mctl-agent
  does not yet wire `prometheus/client_golang`; tracked separately).
- **Configuration:** two new optional env vars with sensible defaults;
  existing deployments continue to work without operator action. The
  Helm values for `mctl-agent` in `mctl-gitops/services/.../mctl-agent/`
  do **not** need to set these unless an operator wants to tune.
- **Backwards compatibility:** the existing `StatusOpen` behaviour is
  preserved exactly. Tickets in `StatusFixApplied`, `StatusResolved`,
  and `StatusSuppressed` continue to be skipped.
