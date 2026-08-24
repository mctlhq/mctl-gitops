# Design: issue-413-ttl-idle-ttl-identity

## Current state

All of this lives in `internal/db/store.go` (`Store` type), backed by
`internal/config/config.go` (`SessionTTLExemptTGIDs`, parsed from
`SESSION_TTL_EXEMPT_TG_IDS` at `config.go:305`) and wired in
`cmd/server/main.go:99-108`.

- `Store.ttlExempt map[int64]bool` (`store.go:26`) holds the exempt Telegram
  ids, set once via `WithAbsoluteTTLExempt` (`store.go:59-69`) at boot, before
  any request handling starts. It is read-only after construction (per its
  doc comment).
- The absolute-TTL side is fully solved via `expires_at IS NULL`:
  - `SaveSession` (`store.go:388-426`) stamps `expires_at = NULL` at insert
    time when `s.ttlExempt[telegramUserID]` is true (`store.go:406-411`).
  - `ReconcileTTLExemptions` (`store.go:76-100`) converges existing rows onto
    the current list on every boot, clearing `expires_at` for ids newly on
    the list.
  - `Migrate` (`internal/db/db.go:56-90`) skips the `expires_at` backfill for
    ids in `ttlExemptTelegramIDs`, so an exempt row's NULL never gets
    transiently re-armed during a migration on another replica.
  - Readers (`CheckSessionValid` line 845, `SweepAbsoluteSessions` line
    920-921, `ListIdentities` line 316) all treat `expires_at IS NULL` as
    "never expires" — no reader needed to learn about the exempt list because
    NULL already meant that.
- The idle-TTL side has no such hook, because there is no NULL-equivalent
  "exempt" value for `last_used_at`: `MarkLastUsed` (`store.go:747-753`)
  overwrites it with `time.Now()` on every successful tool dispatch
  (`Pool.Borrow`), so any stand-in sentinel would be destroyed by the very
  next real use.
  - `SweepIdleSessions` (`store.go:889-908`): `UPDATE ... WHERE revoked_at IS
    NULL AND last_used_at IS NOT NULL AND last_used_at < $2` — no exempt
    awareness.
  - `CheckSessionValid` (`store.go:809-854`): the idle branch at
    `store.go:849-852` is `if lastUsed.Valid && now.Sub(lastUsed.Time) >
    idleSessionTTL { ... revoke ... return ReasonIdle }` — no exempt
    awareness, even though the same function already loads `tgUserID` from
    the row two lines earlier (`store.go:813,820`) for the unauthorized-row
    check.
  - `ListIdentities` (`store.go:307-382`): its `HasSession` subquery
    (`store.go:313-317`) ANDs `(ta.expires_at IS NULL OR ta.expires_at >
    $1)` with `(ta.last_used_at IS NULL OR ta.last_used_at > $2)` — the first
    clause already benefits from the NULL trick, the second does not.
  - `internal/config/config.go:126-129`'s doc comment on
    `SessionTTLExemptTGIDs` explicitly (and, per this issue, incorrectly)
    documents "The 30-day idle TTL still applies to them" as intended
    behavior.
  - `internal/db/store_ttl_test.go:422-450`, `TestIdleTTLStillAppliesToExempt`,
    pins exactly that behavior today: seeds an exempt identity with
    `last_used_at` 40 days old and asserts `SweepIdleSessions` revokes it.
- `internal/sweeper/sweeper.go:47-61` (`sweepOnce`) calls
  `store.SweepIdleSessions` and `store.SweepAbsoluteSessions` on an hourly
  ticker (`SessionSweeperInterval = time.Hour`, `sweeper.go:21`). Both are
  plain `*Store` methods with no exempt-list parameter — they close over
  `s.ttlExempt` already, so no call-site signature changes are needed
  anywhere that invokes them.

## Proposed solution

Give the idle-TTL path the same exempt awareness the absolute-TTL path has,
without reusing the NULL trick (which cannot work for a column that gets
overwritten on every use, per Context). Two different mechanisms fit the two
different query shapes already in the code, and both stay entirely inside
`internal/db/store.go`:

1. **`CheckSessionValid` — a Go-side guard, no SQL change.** The function
   already scans `tgUserID` from the row (`store.go:813-820`) for the
   unauthorized-row check. Add one condition to the idle branch:

   ```go
   if lastUsed.Valid && !s.ttlExempt[tgUserID.Int64] &&
       now.Sub(lastUsed.Time) > idleSessionTTL {
       _, _ = s.RevokeActiveSession(ctx, userID, "idle_expiry")
       return ReasonIdle, fmt.Errorf("%w: %s", ErrSessionExpired, ReasonIdle)
   }
   ```

   `tgUserID.Valid` is already guaranteed true at this point (the function
   returns earlier via `ErrSessionUnauthorized` when it is not), so
   `tgUserID.Int64` is safe to read directly. `s.ttlExempt` is a plain Go map
   lookup — no query shape change, no new params, and it composes for free
   with the existing absolute-TTL branch above it (unaffected).

2. **`SweepIdleSessions` and `ListIdentities` — a small dynamic SQL fragment,
   built once from `s.ttlExempt`.** Both are set-based queries (`UPDATE ...
   WHERE`, `SELECT ... EXISTS(...)`) with no single row to inspect in Go, so
   the exemption has to be expressed in the query itself, exactly as the
   issue proposes (`AND telegram_user_id NOT IN (<exempt>)`). Add one small
   private helper next to the existing exempt machinery:

   ```go
   // ttlExemptClause returns a SQL fragment ("" if no ids are exempt) plus its
   // bind args, so callers can splice "AND telegram_user_id NOT IN (...)" (or
   // the inverted "OR telegram_user_id IN (...)" form for ListIdentities) into
   // a query that already has argIdx-1 placeholders bound. Sorted so the
   // generated SQL text (and therefore the prepared-statement cache key) is
   // stable across calls, matching ReconcileTTLExemptions.
   func (s *Store) ttlExemptClause(argIdx int) (fragment string, args []any) {
       if len(s.ttlExempt) == 0 {
           return "", nil
       }
       ids := make([]int64, 0, len(s.ttlExempt))
       for id := range s.ttlExempt {
           ids = append(ids, id)
       }
       sort.Slice(ids, func(i, j int) bool { return ids[i] < ids[j] })
       placeholders := make([]string, len(ids))
       args = make([]any, len(ids))
       for i, id := range ids {
           placeholders[i] = fmt.Sprintf("$%d", argIdx+i)
           args[i] = id
       }
       return "(" + strings.Join(placeholders, ",") + ")", args
   }
   ```

   `SweepIdleSessions` becomes:

   ```go
   func (s *Store) SweepIdleSessions(ctx context.Context) (int64, error) {
       now := time.Now().UTC()
       idleCutoff := now.Add(-idleSessionTTL)
       query := `UPDATE telegram_accounts
                  SET revoked_at = $1
                WHERE revoked_at IS NULL
                  AND last_used_at IS NOT NULL
                  AND last_used_at < $2`
       args := []any{now, idleCutoff}
       if clause, exemptArgs := s.ttlExemptClause(3); clause != "" {
           query += " AND telegram_user_id NOT IN " + clause
           args = append(args, exemptArgs...)
       }
       res, err := s.DB.ExecContext(ctx, query, args...)
       // ... unchanged from here
   }
   ```

   `ListIdentities`'s `HasSession` subquery gets the mirrored `OR` form
   spliced into the existing `(ta.last_used_at IS NULL OR ta.last_used_at >
   $2 ...)` clause: `... OR ta.telegram_user_id IN (...)`, with the exempt
   args appended after `$2` in the outer `QueryContext` call.

   When `s.ttlExempt` is empty (the default — no operator has set
   `SESSION_TTL_EXEMPT_TG_IDS`), `ttlExemptClause` returns `""` and both
   queries are byte-for-byte what they are today: zero behavior change, zero
   overhead, for every deployment that does not use the feature.

3. **Doc/comment cleanup.** Update the `SessionTTLExemptTGIDs` comment in
   `internal/config/config.go:126-129` to say the exemption now covers both
   TTLs (delete the "30-day idle TTL still applies to them" sentence).
   Update `WithAbsoluteTTLExempt`'s doc comment (`store.go:52-58`) similarly —
   keep the method name (see Open Questions in requirements.md) but stop
   describing it as absolute-only.

4. **Test rewrite**, per the issue's own instruction:
   - Invert `TestIdleTTLStillAppliesToExempt`
     (`internal/db/store_ttl_test.go:422-450`) into
     `TestIdleTTLDoesNotApplyToExempt` (or similar): same seed, but now
     asserts `SweepIdleSessions` revokes 0 rows for the exempt identity.
   - Add the two-sided invariant test the issue asks for: one exempt identity
     and one non-exempt identity, both with `last_used_at` 40 days old;
     `SweepIdleSessions` must revoke exactly the non-exempt one. This mirrors
     the existing `TestSweepAbsoluteSessionsSkipsExempt`
     (`store_ttl_test.go:315-347`) pattern for the idle side.
   - Add `TestCheckSessionValidAcceptsExemptIdle` mirroring
     `TestCheckSessionValidAcceptsExempt` (`store_ttl_test.go:379-392`, which
     currently only proves the absolute side): exempt identity, stale
     `last_used_at`, `CheckSessionValid` must return `nil`.
   - Add a `ListIdentities` case proving `HasSession=true` for an exempt
     identity with a stale `last_used_at`, next to wherever `ListIdentities`
     is already tested (`internal/db/store_test.go` — confirm exact location
     during implementation; if no existing `ListIdentities` test file
     surfaces, add one following the file's existing test-table style).

## Alternatives

1. **Reuse the NULL trick for `last_used_at` (write NULL, treat NULL as "never
   idle").** Rejected per the issue's own analysis: `MarkLastUsed` stamps
   `last_used_at = now()` on every successful tool dispatch, so the very next
   real use of an exempt identity's session would silently re-arm the idle
   clock, making the exemption non-deterministic (works only until the
   identity is used once). The absolute side gets away with NULL because
   nothing ever writes `expires_at` outside of `SaveSession`/backfill/
   reconcile; `last_used_at` has no such invariant.

2. **Skip `MarkLastUsed` entirely for exempt identities**, so `last_used_at`
   stays whatever it was (e.g. NULL forever, or frozen at connect time), and
   NULL/frozen-old values gate on the existing `last_used_at IS NULL` clauses
   that already mean "never idle" in `SweepIdleSessions`,
   `CheckSessionValid`, and `ListIdentities`. Rejected: `last_used_at`
   is also the operational signal the sweeper logs and operators read to
   tell whether an identity is actually alive (`CountActiveSessions`,
   `store.go:934+`, keys off recent `last_used_at`); freezing it for exempt
   rows would make a genuinely-dead exempt session look identical to a live
   one in every dashboard/log, which trades one invisible failure mode
   (silent idle revoke) for another (silent staleness with no signal at
   all). It also does not match the issue's explicit proposal ("провести
   исключение через сам запрос"), which asks for a real predicate, not a
   suppressed write.

3. **Move the exempt set into the database (a `ttl_exempt` column or a
   companion table) instead of a config-driven, boot-time Go map.** Rejected
   as out of scope: `WithAbsoluteTTLExempt`/`ReconcileTTLExemptions` already
   establish config-as-source-of-truth with DB convergence for the absolute
   side, and the issue does not ask to change that model — only to make the
   idle path respect the same in-memory set the absolute path already
   respects. Introducing a second source of truth would be a strictly larger
   change with its own migration and race-condition surface (see
   `TestMigrateLeavesExemptRowsNull`'s multi-replica concerns), unrelated to
   the bug being fixed here.

4. **Have the sweeper goroutine (`internal/sweeper/sweeper.go`) filter exempt
   ids itself, rather than pushing the predicate into `Store`'s SQL.**
   Rejected: `sweeper.Sessions` has no access to `Store.ttlExempt` (it is an
   unexported field) and no reason to — `CheckSessionValid` also needs the
   same exemption and is called from `telegram.ClientPool.Borrow`, entirely
   outside the sweeper. Keeping the predicate inside `Store` methods is the
   only way both call paths agree, which is exactly the invariant the issue
   asks for.

## Platform impact

- **Migrations:** none. No schema change — the exemption is a query-time
  predicate over existing columns (`telegram_user_id`, `last_used_at`), same
  as the issue proposes.
- **Backward compatibility:** fully backward compatible.
  `SESSION_TTL_EXEMPT_TG_IDS` unset (the default for every tenant that has
  not opted in) means `s.ttlExempt` is empty, `ttlExemptClause` returns `""`,
  and every touched query is textually identical to today's. For tenants that
  already set the env var, this is a strict widening of what "exempt" means —
  no exempt identity that was surviving today stops surviving; some that were
  being incorrectly revoked now correctly survive.
- **Resource impact:** negligible. `SweepIdleSessions` runs hourly
  (`SessionSweeperInterval`); the added `NOT IN (...)` clause has at most as
  many literals as `SessionTTLExemptTGIDs` has entries (operator/service
  identities — expected to be single digits). `CheckSessionValid`'s change is
  a map lookup on the request path, already O(1) and already reading
  `tgUserID` from the same row.
- **Risks + mitigations:**
  - *Risk:* an id present in `SESSION_TTL_EXEMPT_TG_IDS` but never actually
    finalised (`telegram_user_id` on the row stays NULL) could theoretically
    never hit the idle-exempt branch. Mitigation: not a new risk — such a row
    is already caught earlier by the `!tgUserID.Valid` /
    `ErrSessionUnauthorized` branch in `CheckSessionValid`
    (`store.go:833-844`) before the idle check is ever reached, and
    `SweepIdleSessions`/`ListIdentities` only match rows where
    `telegram_user_id` participates via the `NOT IN`/`IN` predicate at all
    when it is non-NULL and equals one of the exempt ids — behavior is
    unchanged for unfinalised rows either way.
  - *Risk:* forgetting to keep `SweepIdleSessions` and `ListIdentities` in
    sync in the future (issue #413 explicitly calls out that #410 got away
    without touching `ListIdentities` only because NULL semantics were
    already shared). Mitigation: both now go through the same
    `ttlExemptClause` helper, so a future change to the exempt predicate only
    needs to change one function; the two-sided test in item 4 above pins the
    agreement.
  - *Risk:* this does not remove `labs-mctl-telegram-demo-session-refresh` or
    `DEMO_REVIEWER_ENABLED`. Mitigation: explicitly out of scope per
    requirements.md — the CronJob does strictly more than this exemption
    (re-revoking already-revoked rows, resetting `send_enabled=false`), and
    removing it prematurely would regress those two behaviors. Follow-up
    proposal needed once/if that behavior is ported or consciously dropped.
