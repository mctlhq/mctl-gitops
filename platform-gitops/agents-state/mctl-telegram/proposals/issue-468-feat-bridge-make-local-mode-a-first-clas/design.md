# Design: issue-468-feat-bridge-make-local-mode-a-first-clas

## Current state

`telegram_accounts` is one table serving both hosted and local accounts
(`internal/db/db.go:295-309` SQLite, `:356-368` Postgres):

```
session_encrypted BLOB/BYTEA NOT NULL   -- every dialect, no exceptions
mode              TEXT NOT NULL DEFAULT 'hosted'
revoked_at        DATETIME/TIMESTAMPTZ  -- nullable; "this row is no longer the active one"
```

Everything that reads "which account/mode is active" filters on
`WHERE user_id = $1 AND revoked_at IS NULL ORDER BY connected_at DESC LIMIT 1` — see
`GetAccountMode`, `GetActiveAccount`, `IsSendEnabled`, `CheckSessionValid`,
`LoadSessionWithID` (`internal/db/store.go`). `GetAccountMode` additionally treats
`sql.ErrNoRows` (no matching row) as `"hosted"` (`store.go:1126-1128`).

Local Bridge dispatch already lives beside, not inside, that hosted path:
`internal/mcp/tools.go` checks `s.Store.GetAccountMode(ctx, id.UserID)` per tool call and,
when `"local"`, calls `s.bridgeCall(...)` directly — it never calls `Pool.Borrow` or
`CheckSessionValid` (confirmed at `tools.go:212-214, 276-283, 403-409, 493-500, 685-687,
1626+, 1682+, 1742+, 1798+, 1872+`). `NewBridgeHandler` (`internal/bridge/server.go:65-75`)
gates the daemon websocket the same way: `GetAccountMode != "local"` -> HTTP 400.

Three write paths can flip `revoked_at` on a row without knowing or caring what `mode` it
carries:

1. `SweepIdleSessions` / `SweepAbsoluteSessions` (`store.go:965-1011`) — revoke any row past
   the idle/absolute TTL, gated only by `s.ttlExempt` (populated from
   `SESSION_TTL_EXEMPT_TG_IDS`, `internal/config/config.go:133-138`). Bridge calls never
   stamp `last_used_at` (only `Pool.Borrow` does, via `MarkLastUsed`), so a local account's
   row goes idle-stale by design and gets revoked here unless its Telegram id is on the
   exemption list.
2. `RevokeActiveSession` (`store.go:613-627`) — called by `disconnect_telegram_account`
   (`tools.go:749`), `POST /api/account/disconnect` (`internal/web/account.go:91,95`), and
   the manage-UI disconnect form (`internal/web/manage.go:70,74`).
3. `CheckSessionValid` itself revokes on idle/absolute expiry or an unauthorized mid-login
   row (`store.go:879-923`) — reachable only through `Pool.Borrow`, i.e. only for accounts
   currently dispatching as hosted, so it cannot touch a local-mode row today. Included
   here only because it shares the same revoke path and matters if mode ever changes back.

Once any of these sets `revoked_at`, `GetAccountMode`'s `WHERE revoked_at IS NULL` filter
stops matching that row, `sql.ErrNoRows` fires, and the function returns `"hosted"` — the
account silently reverts. `NewBridgeHandler` then rejects the daemon with no signal to the
user or an operator beyond a generic HTTP 400 on the daemon's own reconnect attempt.

Provisioning today is a single admin path, `set_account_mode`
(`internal/mcp/tools.go:1007-1094`, backed by `Store.SetAccountMode`,
`store.go:773-790`): an `UPDATE ... SET mode = $2 WHERE user_id = $1 AND revoked_at IS
NULL`. It requires a pre-existing active row (i.e. a completed hosted login, because that
is the only thing that inserts one with `session_encrypted` populated —
`SaveSession`, `store.go:439-477`), and it currently hard-refuses `mode = "local"` unless
`s.Store.IsModeExempt(tgID)` is true (`tools.go:1064-1069`), which is the operational patch
for problem (1) above — every Local Bridge user must be a GitOps PR away, and a pod
restart, before they can be switched to local mode.

`/security` (`internal/web/security.html:121`) and `internal/bridge/DESIGN.md`
("Trust-model notes") both currently describe the local-mode privacy guarantee in terms
that assume `session_encrypted` can be `NULL` — it cannot, today.

## Proposed solution

### 1. Schema: `session_encrypted` becomes nullable

Postgres (production dialect): add to `Migrate()` in `internal/db/db.go`, alongside the
existing idempotent `ALTER TABLE users ALTER COLUMN github_login DROP NOT NULL`
(`db.go:198-204`, same pattern):

```go
if pg {
    if _, err := dbConn.ExecContext(ctx,
        `ALTER TABLE telegram_accounts ALTER COLUMN session_encrypted DROP NOT NULL`,
    ); err != nil {
        return fmt.Errorf("drop not null on telegram_accounts.session_encrypted: %w", err)
    }
}
```

SQLite cannot alter a column constraint in place; per the existing precedent for
`github_login`, this only matters for local dev/tests, so `sqliteSchema()`'s `CREATE TABLE`
(`db.go:301`) drops `NOT NULL` directly — it only affects freshly created databases, and
SQLite is never the production dialect (`CLAUDE.md`: "SQLite (local dev) or Postgres
(production)"). No data rewrite; existing rows keep their non-NULL blobs untouched.

### 2. `GetAccountMode` stops gating on `revoked_at`

Mode is a property of the account row, not of whether its embedded hosted session is
still considered fresh. Change the query in `GetAccountMode`
(`internal/db/store.go:1118-1133`) to drop the `revoked_at IS NULL` predicate:

```sql
SELECT mode FROM telegram_accounts
 WHERE user_id = $1
 ORDER BY connected_at DESC LIMIT 1
```

This is a narrow, deliberate change scoped to this one reader:

- For a genuinely new user (zero rows), `sql.ErrNoRows` still fires and the function still
  returns `"hosted"` — no behavior change.
- For a hosted account whose row is later revoked (disconnect, TTL sweep) with no
  reconnect, this now returns `"hosted"` directly off the (revoked) row's `mode` column
  instead of via the `ErrNoRows` fallback — same value, no observable change.
- For an account whose row has `mode = 'local'` (provisioned or migrated), this now
  returns `"local"` regardless of `revoked_at`, which is exactly acceptance criterion 4:
  revoking the hosted session of a migrated local account must not make `/bridge` start
  rejecting its daemon.
- A fresh hosted login (`SaveSession`) always inserts a *new* row with the latest
  `connected_at` and the default `mode = 'hosted'`, so it always wins `ORDER BY
  connected_at DESC LIMIT 1` over any older revoked row for the same user — reconnecting
  to hosted after being local still works exactly as before.

No other reader changes. `CheckSessionValid`, `LoadSessionWithID`, `IsSendEnabled`,
`GetActiveAccount` keep filtering on `revoked_at IS NULL` — they answer "does this user
have a currently-trusted hosted session," which is a hosted-path-only question that local
dispatch never asks (it only ever calls `GetAccountMode`, confirmed above).

### 3. Provisioning: a new admin tool that creates a local-only row

Add `Store.ProvisionLocalAccount(ctx, userID, tgID int64, displayName, username string)
error`, in the same family as `SaveSession`/`SetAccountMode`:

```sql
-- refuse if an active row already exists (existing account -> use set_account_mode)
SELECT EXISTS(SELECT 1 FROM telegram_accounts WHERE user_id = $1 AND revoked_at IS NULL)
-- if not exists:
INSERT INTO telegram_accounts
  (user_id, telegram_user_id, display_name, username, session_encrypted, mode, send_enabled)
VALUES ($1, $2, $3, $4, NULL, 'local', FALSE)
```

Both statements run in one transaction (mirrors `SaveSession`'s tx pattern,
`store.go:444-476`) so the existence check and insert cannot race. `expires_at` and
`last_used_at` are left `NULL` — there is no server-held session to expire, and the mode
filter in the sweeper (below) is the actual guard, not the TTL columns.

Wire it as a new MCP admin tool, `provision_local_account`, mirroring
`toolSetAccountMode`'s shape (`tools.go:1007-1094`): `admin:users` scope, `telegram_id`
required, optional `display_name`/`username`. Unlike `set_account_mode` it must first
resolve or create the `users` row for that Telegram id — call
`Store.EnsureUserByTelegramID` (`store.go:191-239`, already idempotent and race-safe) since
provisioning is explicitly meant to work for a Telegram id that has never signed in via the
OAuth widget. Audit every exit the same way `toolSetAccountMode` does (refuse and success
both call `s.audit`).

`set_account_mode` keeps its existing job (flipping an existing hosted row to `local` and
back) but drops the `IsModeExempt` refusal (`tools.go:1064-1069`) and its backing
`Store.IsModeExempt` check for the `mode == "local"` case — that refusal existed solely to
prevent step 4's problem, which step 4 now fixes at the source. `IsModeExempt` and
`ttlExempt` stay in `Store` unchanged: they still gate `SESSION_TTL_EXEMPT_TG_IDS`'s
legitimate remaining use for long-lived hosted operator/service identities
(`config.go:133-137`).

### 4. Sweeper: exclude local-mode rows by construction

This is the change the issue flags as the dangerous one, because `SweepIdleSessions`
revokes live sessions and a wrong predicate fails silently (a revoked local row just reads
as hosted, per problem (2) above, now problem (1) above with local-mode's actual desired
symptom being "still works" — so failing to add the filter is a silent regression too).
Add a `mode <> 'local'` predicate, same shape as the existing `ttlExemptClause`
composition, to `SweepIdleSessions` (`store.go:965-987`):

```sql
UPDATE telegram_accounts
   SET revoked_at = $1
 WHERE revoked_at IS NULL
   AND mode <> 'local'
   AND last_used_at IS NOT NULL
   AND last_used_at < $2
   [AND telegram_user_id NOT IN (...)]   -- existing ttlExemptClause, now redundant for
                                          -- local accounts but still correct
```

Apply the same `mode <> 'local'` predicate to `SweepAbsoluteSessions`
(`store.go:993-1011`) for consistency — a migrated account's `expires_at` still carries the
90-day deadline stamped by its original `SaveSession` call, and leaving the absolute sweep
unfiltered would let it revoke the row later even after this fix (flagged in Open
Questions since the issue's acceptance criteria name only the idle sweep). Leave the
deprecated combined `SweepExpiredSessions` (`store.go:935-959`) with the same treatment for
consistency, though nothing in the current sweeper goroutine (`internal/sweeper/sweeper.go`
calls only `SweepIdleSessions`/`SweepAbsoluteSessions`, not the deprecated combined one)
calls it in production.

### 5. Documentation: `/security` and `internal/bridge/DESIGN.md`

Update `internal/web/security.html`'s `session_encrypted` row and surrounding trust-model
paragraph (currently corrected to say the column is never `NULL`, `security.html:121`) to
state the accurate, now-true-for-some-accounts claim: `NULL` for accounts provisioned as
local-only via `provision_local_account`; a sealed (but unused) blob still exists for
accounts migrated from hosted via `set_account_mode`, and clearing that blob is explicitly
out of scope for this change. Mirror the same distinction in `internal/bridge/DESIGN.md`'s
"Trust-model notes" and "Remaining gaps -> Correctness gaps" sections (both already
describe the current broken behavior in detail and are the natural place to record the
fix and the residual caveat for migrated accounts).

## Alternatives

1. **Keep one row, add a `session_present` boolean instead of allowing `NULL`.** Rejected:
   it duplicates information `session_encrypted IS NULL` already expresses once nullable,
   adds a second column that can drift out of sync with the blob, and does not remove the
   `NOT NULL` constraint that is the actual blocker for provisioning — it just relocates
   the same fact into a second column.
2. **Split local accounts into a separate table (e.g. `local_bridge_accounts`) instead of
   reusing `telegram_accounts`.** Rejected for this pass: every existing reader
   (`GetAccountMode`, `GetActiveAccount`, `IsSendEnabled`, audit joins, `ListIdentities`)
   already keys off `telegram_accounts`, and duplicating that surface into a second table
   doubles the join/branch logic in `internal/mcp/tools.go` for no behavioral gain — the
   issue's own framing ("a first-class row", not "a first-class table") matches keeping one
   table with a nullable session column. Worth revisiting only if local accounts grow
   enough independent columns that the shared table becomes awkward, which is not the case
   today (they need exactly the columns already there minus one now-optional one).
3. **Fix consequence 3 by making `RevokeActiveSession` mode-aware (skip local rows)
   instead of changing `GetAccountMode`.** Rejected: `RevokeActiveSession` is also the
   idle/absolute-expiry path and the explicit disconnect path; special-casing it to no-op
   for `mode = 'local'` would silently swallow a user's explicit
   `disconnect_telegram_account` call for a migrated local account (it would appear to
   succeed while leaving the row untouched) and would need the same mode-awareness
   duplicated at every call site anyway (steps 4's sweeper fix already needs its own
   `mode <> 'local'` predicate regardless). Changing what `GetAccountMode` reads is a
   single, honest fix at the one place mode is actually decided.
4. **Retire `SESSION_TTL_EXEMPT_TG_IDS` entirely as part of this change.** Rejected: the
   config comment (`config.go:133-137`) documents a second, legitimate use — long-lived
   hosted operator/service identities that must never require interactive reconnect. That
   use is unrelated to Local Bridge and out of this issue's stated scope; only local
   accounts' dependency on the list is removed here.

## Platform impact

- **Migrations**: one additive `ALTER TABLE ... ALTER COLUMN session_encrypted DROP NOT
  NULL` on Postgres, applied idempotently inside the existing `Migrate()` on every boot
  (same pattern as the `users.github_login` nullability change already in the codebase).
  No data rewrite, no downtime — dropping a `NOT NULL` constraint is a fast metadata-only
  change in Postgres. SQLite schema change only affects freshly created databases
  (local dev / tests).
- **Backward compatibility**: existing hosted rows are untouched (`session_encrypted`
  stays populated); existing local rows created via `set_account_mode` are untouched
  (they keep their sealed blob, which is fine — the "not in scope" section explicitly
  defers clearing those). `GetAccountMode`'s narrowed predicate is backward compatible
  for every existing hosted-account behavior, as shown case-by-case above.
- **Resource impact**: negligible — one nullable column, one new `INSERT`-shaped admin
  tool, two `WHERE` clauses gaining one predicate each.
- **Risk**: the sweeper predicate change (step 4) is the one the issue explicitly calls
  dangerous, because a wrong predicate fails silently (a revoked local row just reads as
  the wrong-but-plausible `"hosted"`, not an error). Mitigation: a mutation-style test
  (see tasks.md T-sweeper-mutation) that fails if the `mode <> 'local'` predicate is
  removed or inverted, plus the two-sided pattern already used for `ttlExemptClause`
  (`TestSweepIdleSessionsTwoSided`) — one local-mode row and one hosted row, both equally
  stale, asserting exactly the hosted one gets revoked.
- **Risk**: `GetAccountMode` losing its `revoked_at IS NULL` filter is a behavior change on
  a function called from the hot path of every MCP tool dispatch. Mitigation: the four
  case analyses above are each covered by a dedicated unit test (tasks.md), and the change
  is a strict narrowing of when the function returns something *other* than the safe
  default (`"hosted"`) — it can only start returning `"local"` in cases that previously,
  incorrectly, returned `"hosted"`.
- **Rollout ordering**: schema change (additive, safe to ship first) -> store/sweeper logic
  -> admin tool -> docs, in one release per the issue's own note that docs "must land in
  the same release as the behaviour, not before it" (a doc claiming `NULL` support before
  the column allows `NULL` would be false in the other direction).
