# Tasks: issue-492-hosted-connect-silently-destroys-a-local

- [ ] 1. Add `db.ErrAccountModeConflict` sentinel error in `internal/db/store.go`,
      next to `ErrAccountAlreadyActive` (around `store.go:818-822`), with a
      doc comment explaining it is returned by `SaveSession` when the active
      account is `mode='local'`.
      DoD: error defined, exported, documented; `go build ./...` passes.

- [ ] 2. Make `Store.SaveSession` (`internal/db/store.go:431-469`) read the
      current active row's `mode` inside the existing transaction, before
      the revoke/insert, using the same "current active row" selection
      `CheckSessionValid`/`GetAccountMode` use (`ORDER BY connected_at DESC,
      id DESC LIMIT 1`, `revoked_at IS NULL`). If `mode == db.ModeLocal`,
      return `db.ErrAccountModeConflict` without revoking or inserting
      anything (rely on the existing deferred `tx.Rollback()`). If no active
      row exists (`sql.ErrNoRows`), fall through to today's behavior
      unchanged. (depends on 1)
      DoD: `SaveSession` refuses cleanly for an active local row, leaves
      `session_encrypted`/`revoked_at` untouched on that row, and behaves
      exactly as before for hosted/no-active-row cases; existing
      `SaveSession` tests (`store_save_session_test.go`, `store_ttl_test.go`,
      `store_migration_test.go`, `clientpool_test.go`) still pass unmodified.

- [ ] 3. Extend `friendlyErr` and `shortReason` in
      `internal/oauth/enable_access.go:659-716` with a case for
      `errors.Is(err, db.ErrAccountModeConflict)`: a specific user-facing
      message ("this account runs Local Bridge ... switch it back to hosted
      mode first, then reconnect") and a specific short reason
      (`"local_mode_active"`) for the `connect:failed:` audit log entry.
      (depends on 2)
      DoD: a `SaveSession` call from the `enable_access` login goroutine
      that returns `ErrAccountModeConflict` renders the specific message on
      the next polled step page instead of the generic "save session:
      account is in local mode..." raw error text, and the audit log entry
      reads `connect:failed:local_mode_active`.

- [ ] 4. Confirm `cmd/login/main.go:212-214` needs no code change (it already
      wraps and prints via `die(...)`); add a one-line comment noting the
      operator now sees `ErrAccountModeConflict`'s message directly if the
      target account is local-mode. (depends on 2)
      DoD: comment added; no behavior change required, verified by reading
      the wrap path.

- [ ] 5. Verify (do not change) `internal/oauth/server.go`'s
      `handleTelegramCallback` `CheckSessionValid` shortcut
      (`server.go:1122-1146`) and `ProvisionLocalAccount`/`SetAccountMode`
      are unaffected — no code change expected here, this task is a
      read-through confirmation captured in the PR description.
      DoD: PR description explicitly notes these three were reviewed and
      intentionally left unchanged, with the one-line reason for each
      (matches design.md's "Proposed solution" items 4-5).

## Tests

- [ ] T1. New unit test in `internal/db` (e.g.
      `store_save_session_mode_test.go`): seed a `mode='local'` active row
      via `ProvisionLocalAccount` (or the `seedModedAccount` helper used in
      `local_account_revoked_test.go`), call `SaveSession` for the same
      `userID`, assert it returns an error satisfying
      `errors.Is(err, db.ErrAccountModeConflict)`, and assert the local
      row's `session_encrypted` is still `NULL` and `revoked_at` is still
      `NULL` afterward (query it back).

- [ ] T2. Companion unit test in the same file: seed a `mode='hosted'`
      active row (or no row at all), call `SaveSession`, assert it succeeds
      exactly as today (mirrors the existing assertions in
      `store_save_session_test.go`) — a regression guard proving the guard
      is scoped to `mode='local'` only.

- [ ] T3. Unit test for the race the issue calls out: a `mode='local'` row
      that is *revoked* (not active) must NOT block `SaveSession` — seed a
      revoked local row plus no active row, call `SaveSession`, assert it
      succeeds and inserts a fresh hosted row (revoked history must never
      wedge a user out of hosted login).

- [ ] T4. `internal/oauth` test alongside the existing `enable_access_test.go`
      patterns: drive the login goroutine path (using the test's existing
      `loginFn` stub injection, see `enable_access_test.go:103,132`) against
      a `uid` that already has an active `mode='local'` row, and assert the
      rendered step page contains the new specific message rather than a
      generic failure, and that `LogToolCall` was invoked with
      `"connect:failed:local_mode_active"`.

- [ ] T5. Regression test asserting `set_account_mode` (local -> hosted,
      `internal/mcp/tools_test.go`) is completely unaffected by this
      change — same inputs/outputs as before the fix. Guards against
      accidentally coupling the new guard to the admin tool's UPDATE path.

## Rollback

The change is additive and fully isolated to `internal/db/store.go` (one
new sentinel error, one new read + branch inside `SaveSession`'s existing
transaction) and `internal/oauth/enable_access.go` (two new `errors.Is`
branches in already-existing message-mapping functions). No schema
migration, no new table, no new column, no config flag.

To roll back: revert the commit(s) for tasks 1-3 (a plain `git revert`, or
redeploy the prior image tag via `mctl_rollback_service` — no gitops data
migration is involved either way). Rolling back restores the prior
behavior exactly (hosted login silently overwrites an active local
account) — there is no partial-rollback hazard because the fix does not
change what gets written to `telegram_accounts` in the cases it doesn't
refuse, only adds a new refusal branch for the local-active-row case.

If the fix is rolled back after having refused some logins in production,
no cleanup is needed: a refused `SaveSession` call never wrote anything, so
there is no data to reconcile — affected users simply retry `/telegram/connect`
and, post-rollback, get the old (unsafe) overwrite behavior again until the
fix is reapplied.
