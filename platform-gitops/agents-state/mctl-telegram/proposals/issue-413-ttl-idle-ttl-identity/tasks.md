# Tasks: issue-413-ttl-idle-ttl-identity

- [ ] 1. Add `Store.ttlExemptClause(argIdx int) (string, []any)` helper in
      `internal/db/store.go`, next to `WithAbsoluteTTLExempt`/
      `ReconcileTTLExemptions`. Sorts `s.ttlExempt` keys and returns a
      `"($N,$N+1,...)"` fragment plus matching args, or `("", nil)` when the
      exempt set is empty. — DoD: helper compiles, has a doc comment
      explaining the sort-for-stable-SQL rationale (mirrors
      `ReconcileTTLExemptions`'s existing sort), and is unit-testable in
      isolation (e.g. asserting the fragment text for a 2-id set and the
      empty-set case).

- [ ] 2. Update `Store.SweepIdleSessions` (depends on 1) to splice
      `AND telegram_user_id NOT IN (...)` into the `UPDATE` when
      `ttlExemptClause` returns a non-empty fragment, appending its args
      after the existing `now`/`idleCutoff` args. — DoD: with
      `SESSION_TTL_EXEMPT_TG_IDS` unset, generated SQL and behavior are
      byte-identical to today (verify via existing
      `TestSweepIdleSessions`/`TestSweepExpiredSessions_RevokesIdleAndAbsolute`
      still passing unmodified); with an exempt id set, a row for that id is
      never revoked by this method regardless of `last_used_at` age.

- [ ] 3. Update `Store.CheckSessionValid`'s idle branch (independent of 1/2)
      to add `!s.ttlExempt[tgUserID.Int64]` to the idle-expiry condition at
      `store.go:849`. — DoD: `TestCheckSessionValid_IdleExpiryRevokes` still
      passes unmodified (non-exempt path unchanged); a new exempt-idle case
      (task 6) passes.

- [ ] 4. Update `Store.ListIdentities`'s `HasSession` subquery (depends on 1)
      to OR in `ta.telegram_user_id IN (...)` alongside the existing
      `last_used_at` freshness check, using the same `ttlExemptClause`
      fragment/args, appended after the existing `now`/`idleCutoff` bind
      args. — DoD: with no exempt ids, query text and results are unchanged
      from today; with an exempt id whose `last_used_at` is stale,
      `ListIdentities` reports `HasSession=true` for that row (given
      `revoked_at IS NULL` and `telegram_user_id IS NOT NULL`, matching what
      `CheckSessionValid` now accepts per task 3).

- [ ] 5. Update doc comments: `internal/config/config.go`'s
      `SessionTTLExemptTGIDs` comment (drop "The 30-day idle TTL still
      applies to them"; state the exemption now covers both TTLs) and
      `WithAbsoluteTTLExempt`'s comment in `internal/db/store.go` (stop
      describing it as absolute-only; keep the method name per
      requirements.md's Open Questions). — DoD: no remaining comment in the
      touched files claims the idle TTL still applies to exempt identities.

## Tests

- [ ] T1. Rewrite `TestIdleTTLStillAppliesToExempt`
      (`internal/db/store_ttl_test.go:422-450`) into a test asserting the
      opposite: seed an exempt identity (`210408407`) with `last_used_at` 40
      days stale and `expires_at = NULL`, call `SweepIdleSessions`, assert 0
      rows revoked and the row's `revoked_at` stays NULL. Rename to reflect
      the new invariant (e.g. `TestSweepIdleSessionsSkipsExempt`, mirroring
      `TestSweepAbsoluteSessionsSkipsExempt`'s naming).

- [ ] T2. Add a two-sided `SweepIdleSessions` test: one exempt identity and
      one non-exempt identity, both seeded with `last_used_at` 40 days stale.
      Assert `SweepIdleSessions` returns exactly 1 and only the non-exempt
      row ends up revoked. (Depends on task 2.)

- [ ] T3. Add `TestCheckSessionValidAcceptsExemptIdle`: exempt identity,
      `last_used_at` 40 days stale, `expires_at` still in the future (or
      NULL) — `CheckSessionValid` must return `nil` (no error), mirroring
      `TestCheckSessionValidAcceptsExempt`'s structure for the absolute side.
      Also add the negative control inline or as a second case: same
      staleness, non-exempt identity, must still return `ErrSessionExpired` /
      `ReasonIdle` (already covered by
      `TestCheckSessionValid_IdleExpiryRevokes`, but re-assert alongside the
      exempt case for the "two Store instances, same clock" style regression
      guard). (Depends on task 3.)

- [ ] T4. Add a `ListIdentities` test proving `HasSession=true` for an exempt
      identity with a stale `last_used_at` and non-revoked, finalised row,
      and `HasSession=false` for the same staleness on a non-exempt identity.
      Locate/create alongside existing `ListIdentities` coverage (check
      `internal/db/store_test.go` first for an existing table; extend it if
      present). (Depends on task 4.)

- [ ] T5. Run the full `internal/db` package test suite
      (`go test ./internal/db/...`) plus `go vet ./...` and
      `golangci-lint run` (per this repo's CLAUDE.md conventions) to confirm
      no regression in the absolute-TTL exemption tests
      (`TestReconcileTTLExemptions*`, `TestSweepAbsoluteSessionsSkipsExempt`,
      `TestMigrateLeavesExemptRowsNull`, `TestCheckSessionValidAcceptsExempt`,
      `TestSaveSessionExemptIdentityHasNoDeadline`) — none of those should
      need any changes, since this proposal only touches the idle path.

## Rollback

- The change is confined to `internal/db/store.go` (three method bodies plus
  one new private helper) and doc comments in `internal/config/config.go`;
  no schema/migration is introduced. Revert is a plain `git revert` of the
  merge commit — no data cleanup, no down-migration, no config change
  required on any tenant.
- If a regression is suspected in production before a revert can land: the
  feature is opt-in via `SESSION_TTL_EXEMPT_TG_IDS`. Unsetting the env var
  for the affected deployment (or removing the specific id from the list)
  immediately restores full idle+absolute TTL enforcement for that identity
  on the next `CheckSessionValid` call / sweeper tick — no redeploy needed,
  since `Migrate`'s backfill and `SweepIdleSessions`/`CheckSessionValid`
  already re-evaluate the live config-derived `s.ttlExempt` set on every
  check (per requirements.md's "IF removed from the list" criterion).
- No new metrics/alerts are introduced; existing
  `mctl_sessions_revoked_total{reason="idle_expiry"}` continues to work
  unchanged — it will simply stop incrementing for exempt identities, which
  is the intended effect and is easy to spot-check against
  `SESSION_TTL_EXEMPT_TG_IDS`'s configured ids if the rollback needs
  verification.
