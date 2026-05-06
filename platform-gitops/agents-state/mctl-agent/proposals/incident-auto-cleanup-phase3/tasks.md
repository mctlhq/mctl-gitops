# Tasks: incident-auto-cleanup-phase3

- [ ] 1. Add `AutoResolveOrphanAfter` to `Config` and parse it from env —
  DoD: `internal/config/config.go` declares
  `AutoResolveOrphanAfter time.Duration` next to the Phase 1 fields;
  parsed from `AUTO_RESOLVE_ORPHAN_AFTER` using the same helper as
  `AUTO_RESOLVE_STALE_AFTER`; default 1h; malformed values cause
  `Load()` to return an error matching the existing pattern;
  `go vet ./...` is clean.

- [ ] 2. Extend `refreshState` with `knownServices` (depends on 1) —
  DoD: `internal/monitor/poller.go` adds
  `knownServices map[string]bool` to `refreshState`; `pollDegraded()`
  populates it from the same `services` slice it already iterates,
  keying on `team+"/"+app`; the field stays nil when `allUnknown` is
  true; existing `pollDegraded` behaviour, `argoRefreshed`, and
  `failedServices` are unchanged; existing tests around `pollDegraded`
  keep passing without modification.

- [ ] 3. Implement `pruneOrphans(state refreshState)` (depends on 2) —
  DoD: a new method on `Poller` that:
  - Returns immediately if `p.OrphanAfter <= 0`.
  - Returns immediately if `state.allUnknown`.
  - Calls `store.ListOpen()` (errors logged at `slog.Error`, return
    early).
  - Iterates and skips: terminal statuses (`StatusFixApplied`,
    `StatusResolved`, `StatusSuppressed`); `SourceManual` tickets;
    tickets whose `(Tenant, Service)` IS in `state.knownServices`;
    tickets whose `time.Since(UpdatedAt)` is below `p.OrphanAfter`.
  - For remaining tickets, calls `store.ResolveByIDFromStatus(t.ID,
    t.Status, "Auto-resolved: service does not exist (likely synthetic /
    orphaned alert)")`; emits `slog.Info("poller: orphan-pruned", ...)`
    on success.

- [ ] 4. Wire `pruneOrphans` into the poll cycle (depends on 3) — DoD:
  `(*Poller).poll()` calls `p.pruneOrphans(state)` AFTER
  `p.resolveStale(state)`; `cmd/agent/main.go` assigns
  `p.OrphanAfter = cfg.AutoResolveOrphanAfter` next to the existing
  `p.StaleAfter / p.AnalyzingAfter / p.FixProposedAfter` lines.

- [ ] 5. Unit tests for the new behaviour (depends on 4) — DoD: four
  new tests in `internal/monitor/poller_test.go`, each using the
  existing `backdate()` helper and constructing a `Poller` with a
  fake/mock `mctlclient` that returns a controlled service list:
  - `TestPrunesOrphanTicketAfterGracePeriod` — backdate an
    Open/Analyzing/FixProposed ticket on a service NOT in the
    inventory past 1h; assert it transitions to resolved with the
    orphan reason in the analysis field.
  - `TestKeepsTicketWhoseServiceExists` — same setup but the service
    IS in the inventory; assert no resolution.
  - `TestSkipsOrphanPruneWhenInventoryUnknown` — set
    `state.allUnknown = true` (e.g. by making the fake client return
    an error from `ListServices`); assert no resolution even when
    backdated past 1h.
  - `TestSkipsManualOrphanTicket` — backdate a `SourceManual` ticket
    on a non-existent service; assert no resolution.
  All four pass under `go test ./internal/monitor/... -v -count=1`.

- [ ] 6. Negative-regression coverage for Phase 1 paths (depends on 4)
  — DoD: existing tests
  (`TestPollerResolvesStaleAnalyzingTicket`,
  `TestPollerResolvesStaleFixProposedTicket`, `TestPollerResolveStale*`,
  etc.) keep passing without modification; the new `pruneOrphans` call
  in `poll()` does not perturb any test that disables it via default
  `OrphanAfter == 0` (zero-value means disabled per task 3).

## Tests

- [ ] T1. `go test ./... -race -v -count=1` is green on the PR branch.
- [ ] T2. Manual sanity: build the binary; set
  `AUTO_RESOLVE_ORPHAN_AFTER=30s POLL_INTERVAL=10s`; create one ticket
  on a known service and one on `tenant=ovk service=does-not-exist`;
  observe the orphan resolve within ~30-40s and the real one stay
  open. Record the log line in the PR description as proof.
- [ ] T3. With `AUTO_RESOLVE_ORPHAN_AFTER` unset, behaviour matches
  main: only Phase 1 stale TTL passes run.

## Rollback

1. Revert the changes to `internal/config/config.go`,
   `internal/monitor/poller.go`, and `cmd/agent/main.go`.
2. The `AUTO_RESOLVE_ORPHAN_AFTER` env var is optional and has no
   on-disk state; removing it from any Helm values that may have been
   set is sufficient.
3. No DB migration is involved, so rollback is purely a code revert
   plus a redeploy.
4. Tickets that were orphan-resolved during the rollout remain
   `Resolved` — they are not re-opened. This is acceptable: orphan
   resolution simply reflects "no service exists for this alert
   target"; if the alert genuinely re-fires for a real service, a
   fresh ticket is created.
