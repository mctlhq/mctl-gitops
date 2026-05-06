# Tasks: incident-auto-cleanup-phase2

- [ ] 1. Add `AlertFingerprint` field to `Ticket` and migrate the
  `tickets` table — DoD: `internal/ticket/ticket.go` adds
  `AlertFingerprint string \`json:"alert_fingerprint,omitempty"\``;
  `internal/ticket/store.go` extends `migrate()` with idempotent
  `ensureColumn(... "alert_fingerprint", "TEXT")` and an
  index-creation helper covering `idx_tickets_alert_fingerprint`;
  `Create`, `Update`, `Get`, `ListOpen`, `ListByStatus`, and any
  other read/write paths SELECT/INSERT/UPDATE the new column;
  existing rows default to NULL/empty; both SQLite and Postgres
  paths handled (re-run `migrate()` on the same DB twice — second
  call must be a no-op); `go vet ./...` clean; `go test
  ./internal/ticket/... -count=1` passes including any new test
  asserting the column round-trips.

- [ ] 2. Persist fingerprint at ticket creation and duplicate-touch
  (depends on 1) — DoD: `internal/monitor/alerthandler.go` decodes
  `Fingerprint` on the inner `alert` struct; on a new ticket the
  field is set in `store.Create`; on a duplicate touch the persisted
  value is updated to the latest observed fingerprint; existing
  alerthandler tests pass; one new test
  `TestAlertHandlerPersistsFingerprint` asserts a webhook with a
  non-empty fingerprint round-trips to `store.Get(id).AlertFingerprint`.

- [ ] 3. Add the AlertManager client (depends on nothing; can ship in
  parallel with 1/2) — DoD: a new file
  `internal/monitor/alertmanager_client.go` defines
  `AlertManagerClient{BaseURL, Timeout, HTTP *http.Client}` and
  `(c *AlertManagerClient) ActiveFingerprints(ctx) (map[string]struct{}, error)`;
  the client targets `BaseURL + "/api/v2/alerts?active=true&silenced=false"`
  with the configured timeout, sets `User-Agent`, and returns a set
  containing only fingerprints whose `status.state == "active"`;
  errors at any stage (transport, non-2xx, JSON decode) return
  `(nil, err)` — never partial results; new
  `internal/monitor/alertmanager_client_test.go` covers: 200 with
  three alerts → returns three; 200 with empty array → returns empty
  set; non-2xx → error; malformed JSON → error; context-deadline →
  error; `go test ./internal/monitor/... -count=1` is green.

- [ ] 4. Add the four AM reconcile env vars to `Config` (depends on
  3) — DoD: `internal/config/config.go` declares
  `AlertManagerURL string` (default
  `http://vmalertmanager-monitoring-victoria-metrics-k8s-stack.monitoring.svc:9093`),
  `AMReconcileEnabled bool` (default `true`),
  `AMReconcileTimeout time.Duration` (default `10s`), and
  `AMReconcileMinAge time.Duration` (default `15m`); each is parsed
  from its respective env var with the same helper used elsewhere;
  malformed durations / booleans cause `Load()` to return an error.

- [ ] 5. Add `reconcileWithAlertManager` pass and wire into `poll()`
  (depends on 1, 3, 4) — DoD: `internal/monitor/poller.go` defines
  `(*Poller).reconcileWithAlertManager(ctx context.Context)` per the
  spec in `design.md`; `(*Poller).poll()` calls it after
  `pruneOrphans(state)`; `Poller` gains `amClient *AlertManagerClient`,
  `AMReconcileEnabled bool`, `AMReconcileMinAge time.Duration`;
  `cmd/agent/main.go` constructs the client from config and assigns
  these fields next to existing poller field assignments; the pass
  short-circuits when:
    - `AMReconcileEnabled` is false,
    - `amClient` is nil,
    - the AM call returns an error,
    - the active set is empty (`slog.Warn` line emitted),
    - the ticket's source is not `SourceAlertManager`,
    - the ticket has no fingerprint,
    - the ticket's status is terminal,
    - the ticket's age is below `AMReconcileMinAge`,
    - the ticket's fingerprint is in the active set.
  Successful resolution writes the reason `Auto-resolved by AM
  reconcile (fingerprint=<X>, last_seen_active=<UpdatedAt RFC3339>)`
  via `ResolveByIDFromStatus` and emits a `slog.Info "poller: AM
  reconcile resolved"` line.

- [ ] 6. Unit tests for `reconcileWithAlertManager` (depends on 5) —
  DoD: new tests in `internal/monitor/poller_test.go`, each
  constructing a `Poller` whose `amClient.HTTP` is wired to a
  `httptest.NewServer` returning controlled JSON:
  - `TestAMReconcileResolvesNonFiringTicket` — fingerprint absent
    from AM response, age past 15m → resolved with reason substring
    `Auto-resolved by AM reconcile`.
  - `TestAMReconcileKeepsActiveTicket` — fingerprint present in AM
    response → no resolution.
  - `TestAMReconcileSkipsBelowMinAge` — fingerprint absent, age 5m
    (below 15m default) → no resolution.
  - `TestAMReconcileSkipsEmptyActiveSet` — AM returns `[]` → no
    resolution; assert `slog.Warn` was emitted.
  - `TestAMReconcileSkipsOnAMError` — AM returns 500 → no
    resolution.
  - `TestAMReconcileSkipsTicketsWithoutFingerprint` — ticket has
    `AlertFingerprint == ""` → never considered for resolution
    regardless of AM state.
  - `TestAMReconcileSkipsNonAlertManagerSource` — ticket with
    `Source = SourcePolling` is skipped.
  - `TestAMReconcileSkipsWhenDisabled` — set
    `p.AMReconcileEnabled = false` → no resolution and no AM HTTP
    call (verify via httptest server hit count).
  All tests run via `go test ./internal/monitor/... -count=1`.

- [ ] 7. Negative-regression coverage for Phase 1 + Phase 3 (depends
  on 5) — DoD: existing tests
  (`TestPollerResolvesStaleAnalyzingTicket`,
  `TestPrunesOrphanTicketAfterGracePeriod`,
  `TestSkipsOrphanPruneOnEmptyInventory`,
  `TestSkipsOrphanPruneForGitHubWebhookSource`, etc.) pass without
  modification; the new `reconcileWithAlertManager` call in `poll()`
  does not perturb any test that does not configure
  `amClient` (zero-value means the new pass short-circuits).

## Tests

- [ ] T1. `go test ./... -race -v -count=1` is green on the PR branch.
- [ ] T2. Manual sanity: build the binary; set
  `ALERTMANAGER_URL=http://vmalertmanager-monitoring-victoria-metrics-k8s-stack.monitoring.svc:9093 AM_RECONCILE_MIN_AGE=30s POLL_INTERVAL=15s`;
  send a webhook with a known fingerprint to create a ticket; wait
  past 30s; ensure the ticket is still active by confirming AM has
  the fingerprint in `/api/v2/alerts`; then mute/silence the alert
  in AM (or wait for it to clear); observe the ticket auto-resolve
  on the next cycle and the `slog.Info "poller: AM reconcile
  resolved"` line. Record the log line in the PR description.
- [ ] T3. With `AM_RECONCILE_ENABLED=false`, behaviour matches main:
  Phase 1 + Phase 3 passes still run; no AM call is made.

## Rollback

1. Revert the changes to `internal/config/config.go`,
   `internal/monitor/poller.go`,
   `internal/monitor/alerthandler.go`,
   `internal/ticket/ticket.go`,
   `internal/ticket/store.go`, and `cmd/agent/main.go`. Delete
   `internal/monitor/alertmanager_client.go` (and its test).
2. The schema migration (the new `alert_fingerprint` column +
   index) is benign — leaving it in the DB after a code revert has
   no impact since no other code reads or writes it. If a clean
   rollback is desired the column can be dropped manually
   (`ALTER TABLE tickets DROP COLUMN alert_fingerprint`); not
   required.
3. The new env vars have no on-disk state.
4. Tickets that were resolved by AM reconcile during the rollout
   remain `Resolved` — they are not re-opened. This is acceptable:
   the resolution reflects "alert no longer firing in AM"; if the
   alert genuinely re-fires, AM will trigger a fresh ticket via the
   existing webhook path.
