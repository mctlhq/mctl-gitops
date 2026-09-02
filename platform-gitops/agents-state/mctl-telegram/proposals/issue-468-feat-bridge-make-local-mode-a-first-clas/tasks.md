# Tasks: issue-468-feat-bridge-make-local-mode-a-first-clas

- [ ] 1. Schema: make `telegram_accounts.session_encrypted` nullable — add the Postgres
  `ALTER TABLE telegram_accounts ALTER COLUMN session_encrypted DROP NOT NULL` to
  `Migrate()` in `internal/db/db.go` (guarded by `if pg`, alongside the existing
  `github_login` drop-not-null precedent), and drop `NOT NULL` from `session_encrypted` in
  `sqliteSchema()`'s `CREATE TABLE telegram_accounts`. — DoD: `go run ./cmd/server` (or the
  test suite's `Migrate` calls) succeed against both a fresh and an existing Postgres
  database; an existing SQLite/Postgres row with a populated blob is unaffected; a manual
  `INSERT INTO telegram_accounts (..., session_encrypted, ...) VALUES (..., NULL, ...)`
  succeeds on both dialects.

- [ ] 2. Store: narrow `GetAccountMode`'s query to `WHERE user_id = $1 ORDER BY
  connected_at DESC LIMIT 1` (drop `AND revoked_at IS NULL`) in `internal/db/store.go`.
  (depends on 1, so a local-only row with `session_encrypted = NULL` can exist to test
  against, though the query change itself does not touch that column) — DoD: existing
  `GetAccountMode` behavior for hosted accounts (fresh, disconnected, never-connected) is
  unchanged (test T2 below), and a `mode = 'local'` row survives `revoked_at` being set by
  any path (test T3, T4).

- [ ] 3. Store: add `ProvisionLocalAccount(ctx, userID, tgID int64, displayName, username
  string) error` to `internal/db/store.go` — one transaction: refuse (return a sentinel
  error, e.g. `ErrAccountAlreadyActive`) if `EXISTS(SELECT 1 FROM telegram_accounts WHERE
  user_id = $1 AND revoked_at IS NULL)`, else `INSERT ... (session_encrypted, mode,
  send_enabled) VALUES (NULL, 'local', FALSE)` leaving `last_used_at`/`expires_at` NULL.
  (depends on 1) — DoD: unit test inserts a row for a brand-new user id and asserts
  `mode='local'`, `session_encrypted IS NULL`; a second call for the same user with an
  existing active row returns the sentinel error and inserts nothing.

- [ ] 4. MCP tool: add `provision_local_account` in `internal/mcp/tools.go`, mirroring
  `toolSetAccountMode`'s shape — `admin:users` scope, `telegram_id` required, optional
  `display_name`/`username`; resolve/create the `users` row via
  `Store.EnsureUserByTelegramID`, then call `ProvisionLocalAccount`; audit every exit
  (refuse and success) via `s.audit`, matching `toolSetAccountMode`'s pattern. Register the
  tool alongside the other admin tools. (depends on 3) — DoD: calling the tool for a
  Telegram id with no prior `users`/`telegram_accounts` row succeeds and returns
  `{telegram_id, mode:"local", ok:true}`; calling it again for the same id refuses with a
  message pointing at `set_account_mode` for migrating an existing account.

- [ ] 5. MCP tool: remove the `IsModeExempt` refusal for `mode == "local"` from
  `toolSetAccountMode` (`internal/mcp/tools.go:1064-1069`) and update its tool description
  (currently explains the now-obsolete `SESSION_TTL_EXEMPT_TG_IDS` requirement,
  `tools.go:1018-1030`). (depends on 6, so the refusal is only removed once the sweeper no
  longer needs it) — DoD: `set_account_mode(mode="local")` for a telegram id with an active
  hosted session succeeds without needing that id on `SESSION_TTL_EXEMPT_TG_IDS`.

- [ ] 6. Sweeper: add `AND mode <> 'local'` to `SweepIdleSessions` and
  `SweepAbsoluteSessions` in `internal/db/store.go` (and, for consistency, the deprecated
  combined `SweepExpiredSessions`). — DoD: see tests T5-T8 below; `go vet` / existing
  sweeper tests in `internal/db/store_ttl_test.go` still pass unmodified.

- [ ] 7. Docs: update `internal/web/security.html`'s `session_encrypted` row/paragraph
  (`security.html:77,121`) and `internal/bridge/DESIGN.md`'s "Trust-model notes" and
  "Correctness gaps" sections to state that `session_encrypted` is `NULL` for accounts
  provisioned via `provision_local_account`, and that a sealed blob still exists for
  accounts migrated via `set_account_mode` (clearing it is out of scope). Also update
  `internal/bridge/DESIGN.md`'s "Remaining gaps" items 5 ("No self-serve enablement...
  there is a GetAccountMode reader and no SetAccountMode writer" — already stale, now also
  needs the new provisioning tool noted) and "Correctness gaps" 1/2 (the two bugs this
  proposal fixes). (depends on 1-6, must land in the same release per the issue) — DoD:
  `go test ./internal/web/...` (security_test.go) still passes against the updated copy;
  a human reviewer confirms no remaining claim contradicts the schema.

## Tests

- [ ] T1. `TestProvisionLocalAccount_CreatesSessionlessRow` — provisioning a brand-new
  Telegram id inserts a row with `mode='local'` and `session_encrypted IS NULL`.
- [ ] T2. `TestProvisionLocalAccount_RefusesExistingActiveAccount` — provisioning a
  Telegram id that already has an active `telegram_accounts` row (hosted or local) returns
  the sentinel error and leaves the existing row untouched.
- [ ] T3. `TestGetAccountMode_HostedBehaviorUnchanged` — table test covering: no rows ->
  `"hosted"`; only a revoked hosted row -> `"hosted"`; a revoked hosted row followed by a
  fresh hosted `SaveSession` -> `"hosted"` (the new row wins `ORDER BY connected_at`).
  Pins that narrowing the query in task 2 does not change any existing hosted-path result.
- [ ] T4. `TestGetAccountMode_SurvivesRevocationWhenLocal` — seed a row with `mode='local'`,
  then set `revoked_at` directly (simulating disconnect or a sweep), and assert
  `GetAccountMode` still returns `"local"`. This is the direct test of acceptance
  criterion 4.
- [ ] T5. `TestBridgeHandler_AcceptsProvisionedLocalAccount` (in
  `internal/bridge/server_test.go`) — an account created only via `ProvisionLocalAccount`
  (no hosted login ever performed) is accepted by `NewBridgeHandler` and a subsequent
  audited tool call records `call_path='local'`.
- [ ] T6. `TestSweepIdleSessionsSkipsLocalMode` — a `mode='local'` row, stale past the idle
  TTL, with `SESSION_TTL_EXEMPT_TG_IDS` (i.e. `s.ttlExempt`) **unset/empty**, survives
  `SweepIdleSessions`. This is the acceptance-criteria test proving the exemption list is
  no longer load-bearing for local accounts.
- [ ] T7 (mutation guard). `TestSweepIdleSessionsTwoSided_HostedVsLocal` — one `mode='local'`
  row and one `mode='hosted'` row, both equally stale past the idle TTL, no TTL exemption
  configured for either: assert exactly 1 row revoked (the hosted one) and that it is the
  hosted `telegram_user_id`, not the local one. Explicitly written so that changing the
  sweeper's `mode <> 'local'` predicate to `mode = 'local'` (or deleting it) flips which
  row survives and fails this test — unlike a test that only asserts "hosted gets swept,"
  which passes on both the fixed and the broken predicate.
- [ ] T8. `TestSweepAbsoluteSessionsSkipsLocalMode` — same shape as T6/T7 for the absolute
  sweep, covering a migrated local account whose original `expires_at` has elapsed.
- [ ] T9. `TestSetAccountMode_NoLongerRequiresTTLExemption` — `set_account_mode(mode=
  "local")` succeeds for a telegram id with an active hosted session and an empty
  `ttlExempt` set (previously refused via `IsModeExempt`).

## Rollback

- Each task is additive or narrows a single query predicate; no destructive migration is
  involved (dropping `NOT NULL` is reversible by re-adding the constraint if every row
  happens to still be non-NULL, though that would defeat the point).
- If `GetAccountMode`'s narrowed query (task 2) misbehaves in production, revert that one
  query change (re-add `AND revoked_at IS NULL`) — this instantly restores the prior
  (buggy but familiar) behavior without touching schema or the sweeper.
- If the sweeper's `mode <> 'local'` predicate (task 6) is suspected of over-exempting
  rows, it can be reverted independently of tasks 1-5 (schema and provisioning stay safe
  either way; the accounts most affected would simply need
  `SESSION_TTL_EXEMPT_TG_IDS` again, the exact status quo ante).
- `provision_local_account` (task 4) is a new, additively-registered tool; disabling it
  (removing its registration) does not affect any existing account, since nothing else
  calls `ProvisionLocalAccount`.
- The schema change (task 1) is not rolled back once any row has `session_encrypted =
  NULL` — re-adding `NOT NULL` at that point would fail until every such row is either
  deleted or backfilled with a placeholder blob. If rollback of the whole feature is ever
  needed, provisioned local-only rows should be hard-deleted (`HardDeleteAccount`) or
  migrated to hosted (a fresh login) before the constraint is reinstated.
