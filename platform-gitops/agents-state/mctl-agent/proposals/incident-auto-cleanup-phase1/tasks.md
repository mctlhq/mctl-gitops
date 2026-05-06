# Tasks: incident-auto-cleanup-phase1

- [ ] 1. Add two duration fields to `Config` and parse them from env — DoD:
  `internal/config/config.go` declares `AutoResolveAnalyzingAfter` and
  `AutoResolveFixProposedAfter` (both `time.Duration`); both are parsed
  near the existing `AUTO_RESOLVE_STALE_AFTER` block (~line 103-108) using
  the same helper; defaults are 48h and 168h respectively; malformed
  values cause `Load()` to return an error matching the existing pattern;
  `go vet ./...` is clean.

- [ ] 2. Refactor eligibility into helper methods (depends on 1) — DoD:
  the `Type` allow-list (`poller.go:182-189`) is exposed as
  `(p *Poller) eligibleType(t ticket.Type) bool` and the `Source`
  allow-list (`poller.go:196-200`) as `(p *Poller) eligibleSource(s
  ticket.Source) bool`; the existing `resolveStale` calls these helpers
  for `StatusOpen` with no behaviour change; existing tests
  (`TestPollerResolvesStaleOpenTicket` and any others touching these
  paths) continue to pass without modification.

- [ ] 3. Extend `resolveStale()` to cover `StatusAnalyzing` and
  `StatusFixProposed` (depends on 2) — DoD: the function uses the
  threshold table described in `design.md`; tickets in the two new
  statuses past their cutoff are resolved via `store.ResolveByID` with
  reason `Auto-resolved by stale TTL GC (status=<X>, age=<Y>, threshold=<Z>)`;
  tickets in `StatusFixApplied`, `StatusResolved`, `StatusSuppressed`
  continue to be skipped; the eligibility filters from task 2 are applied
  uniformly across all three resolved statuses; a `slog.Info` line with
  fields `ticket, status, age, threshold` is emitted for each resolution.

- [ ] 4. Unit tests for the new behaviour (depends on 3) — DoD: three new
  tests in `internal/monitor/poller_test.go`, each using the existing
  `backdate()` helper at `poller_test.go:27` to set `updated_at`:
  - `TestPollerResolvesStaleAnalyzingTicket` — backdates an analyzing
    ticket past 48h, asserts it transitions to resolved and the analysis
    field contains the GC reason string.
  - `TestPollerResolvesStaleFixProposedTicket` — analogous for
    `StatusFixProposed` past 168h.
  - `TestPollerKeepsRecentAnalyzingTicket` — backdates only 24h; asserts
    the ticket remains in `analyzing` (no resolution).
  All tests run via `go test ./internal/monitor/... -v` and pass.

- [ ] 5. Negative-regression tests for the existing `StatusOpen` path
  (depends on 3) — DoD: existing tests covering the
  `AUTO_RESOLVE_STALE_AFTER` flow (e.g. `TestPollerResolvesStaleOpenTicket`)
  pass without modification; if any existing test relies on the literal
  shape of the resolved-reason string, update it to the new format AND
  document the change in the PR description; no test is silently disabled
  or skipped.

## Tests

- [ ] T1. `go test ./... -race -v` is green on the PR branch.
- [ ] T2. Manual sanity: build the binary, set
  `AUTO_RESOLVE_ANALYZING_AFTER=1m AUTO_RESOLVE_FIX_PROPOSED_AFTER=1m
  POLL_INTERVAL=10s`, seed one analyzing and one fix_proposed ticket via
  the test helper, observe both resolve within the next poll cycle. The
  PR description records the log lines emitted as proof.
- [ ] T3. With both new envs unset, behaviour matches main: only
  `StatusOpen` tickets past 24h are resolved. Verified by running the
  existing test suite without modifications.

## Rollback

1. Revert the changes to `internal/config/config.go` and
   `internal/monitor/poller.go`.
2. The two new env vars are optional and have no on-disk state; removing
   them from any Helm values that may have been set is sufficient and
   does not require a chart bump.
3. No DB migration is involved, so rollback is purely a code revert plus
   a redeploy.
4. After rollback, tickets in `StatusAnalyzing` and `StatusFixProposed`
   that were auto-resolved during the rollout remain `Resolved` — they
   are not re-opened. This is acceptable because resolution simply
   reflects "no longer firing"; if the underlying alert fires again,
   AlertManager will create a fresh incident.
