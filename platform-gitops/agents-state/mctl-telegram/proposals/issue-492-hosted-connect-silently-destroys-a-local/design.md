# Design: issue-492-hosted-connect-silently-destroys-a-local

## Current state

`telegram_accounts.mode` distinguishes `'hosted'` (server holds the MTProto
session) from `'local'` (Local Bridge: MTProto runs on the user's own
machine, `tg.mctl.ai` relays only) — `internal/db/store.go:274-279`. The
column defaults to `'hosted'` (`internal/db/db.go:123-124`, and the two
`CREATE TABLE` definitions at `internal/db/db.go:328` and `:426`).

Three code paths write to `telegram_accounts` in ways relevant here:

1. **`Store.ProvisionLocalAccount`** (`internal/db/store.go:846-864`) — the
   #481-#484 self-service activation entry point. It inserts a row with
   `session_encrypted = NULL`, `mode = 'local'`, guarded by a single
   `INSERT ... SELECT ... WHERE NOT EXISTS (SELECT 1 FROM telegram_accounts
   WHERE user_id = $1 AND revoked_at IS NULL)`. If any active row already
   exists (hosted or local), the insert affects zero rows and the call
   returns `ErrAccountAlreadyActive` (`store.go:818-822`). This is the #482
   guard the issue references — it protects local activation from
   clobbering an existing account, in either mode.

2. **`Store.SaveSession`** (`internal/db/store.go:431-469`) — the funnel for
   every hosted MTProto login. Called from:
   - `internal/oauth/enable_access.go:203`, inside the background login
     goroutine (`bgCtx`) that `handleEnableStart`/`handleEnableCode`/
     `handleEnablePassword` poll (`internal/oauth/enable_access.go:150-216`),
     itself reached from the `/telegram/connect` -> `/oauth/authorize` ->
     `handleTelegramCallback` chain (`internal/web/connect.go`,
     `internal/oauth/server.go:991` onward) for both ordinary MCP client
     sign-in and the `mctl_self_connect` self-connect landing page
     (`internal/oauth/server.go:1112-1170`, `ConnectClientID` at
     `server.go:446`).
   - `cmd/login/main.go:212`, the operator-run interactive login CLI
     (`CONTRIBUTING.md`/`CLAUDE.md`: "interactive Telegram login CLI"),
     which opens the same production database directly and is unaffected by
     any of the HTTP-layer flow logic.
   - (`cmd/local/main.go:212` also calls `SaveSession`, but against a
     separate local SQLite store opened on the user's own machine by the
     Local Bridge daemon CLI, not the hosted database — out of scope, not a
     caller this fix needs to reach.)

   `SaveSession` does, unconditionally, in one transaction: revoke every row
   for the user with `revoked_at IS NULL`, then insert a new row that omits
   `mode` — so it takes the `'hosted'` default — with the newly sealed
   session blob.

3. **`Store.SetAccountMode`** (`internal/db/store.go:783-793`) — the only
   currently-guarded way to move `local -> hosted`: an admin-only MCP tool
   (`internal/mcp/tools.go:1139-1214`, `admin:users` scope) that runs
   `UPDATE telegram_accounts SET mode = $2 WHERE` `actionableAccount`
   (`store.go:816`, `id = (`current row`) AND (revoked_at IS NULL OR mode =
   'local')`). It only flips the `mode` label; it does not touch
   `session_encrypted` or `local_bridge_devices`.

**The gap:** nothing between the browser/CLI entry points and `SaveSession`
ever reads `mode`. `handleTelegramCallback`'s pre-`enable_access` shortcut
(`internal/oauth/server.go:1122-1146`) calls `Store.CheckSessionValid`
(`store.go:952-997`), which — deliberately, per the Migrate backfill comment
at `internal/db/db.go:226-234` ("Keep exempt identities out of the
backfill") — never sets `expires_at`/`last_used_at` on local rows, so a
long-lived, untouched local row usually reads as "valid" and the user never
reaches `enable_access` at all for that case. That is incidental protection,
not a guarantee: it depends on `CheckSessionValid` treating the row as
valid, and it has at least one concrete gap the issue's "at any time" framing
correctly points at — a race between self-service activation and an
in-flight hosted login for the same `users.id`. `ProvisionLocalAccount`'s
own guard only protects the *creation* direction; nothing stops
`SaveSession` from running to completion after the local row already exists.
The operator CLI (`cmd/login/main.go`) does not go through
`handleTelegramCallback` at all, so it has no such incidental protection
either. No existing test (`internal/oauth/server_test.go`,
`internal/db/store_test.go`, `internal/db/local_account_test.go`,
`internal/db/local_account_revoked_test.go`) exercises `SaveSession` against
an active `mode='local'` row — confirming this path is genuinely untested,
matching the issue's claim.

## Proposed solution

Guard `Store.SaveSession` itself, per the issue's own reasoning: it is the
single funnel, so guarding it protects every current and future caller
(`enable_access`, the operator CLI, anything else that reaches the hosted
store) without having to duplicate the check in each handler.

1. **New sentinel error**, alongside `ErrAccountAlreadyActive`
   (`internal/db/store.go:818-822`):

   ```go
   // ErrAccountModeConflict is returned by SaveSession when the user's
   // current active account is mode='local'. A hosted login must not
   // silently revoke a Local Bridge account and replace it with a
   // server-side session; the caller must switch modes explicitly via
   // set_account_mode first.
   var ErrAccountModeConflict = errors.New("account is in local mode; switch to hosted mode before connecting")
   ```

2. **`SaveSession` reads the current active row's mode before mutating
   anything**, inside the existing transaction
   (`internal/db/store.go:436-440`):

   ```go
   var mode string
   err = tx.QueryRowContext(ctx,
       `SELECT mode FROM telegram_accounts
        WHERE user_id = $1 AND revoked_at IS NULL
        ORDER BY connected_at DESC, id DESC LIMIT 1`,
       userID,
   ).Scan(&mode)
   if err != nil && !errors.Is(err, sql.ErrNoRows) {
       return fmt.Errorf("check account mode: %w", err)
   }
   if mode == ModeLocal {
       return ErrAccountModeConflict
   }
   ```

   This uses the same "current active row" selection `CheckSessionValid`
   and `GetAccountMode` already use (`ORDER BY connected_at DESC, id DESC
   LIMIT 1`, `store.go:959-961`, `1205-1207`) so all three agree on which
   row is "the" active account. On `ErrAccountModeConflict`, the deferred
   `tx.Rollback()` (already present, `store.go:440`) fires, so nothing is
   revoked and nothing is inserted — `session_encrypted` and `revoked_at`
   on the local row are untouched, satisfying the first two acceptance
   criteria directly. `sql.ErrNoRows` (no active row at all) falls through
   to the existing revoke-then-insert behavior unchanged, since there is
   nothing local to protect.

3. **Surface the refusal as a specific message** in the two callers that
   render it to a human:

   - `internal/oauth/enable_access.go:203-206`: the wrapping
     (`fmt.Errorf("save session: %w", serr)`) already preserves
     `errors.Is`, so no change is needed there. Extend `friendlyErr` and
     `shortReason` (`enable_access.go:659-716`) with one new case each:

     ```go
     // in friendlyErr, alongside the DeadlineExceeded/tgerr cases:
     if errors.Is(err, db.ErrAccountModeConflict) {
         return "this account runs Local Bridge — its Telegram session lives on your own machine. Switch it back to hosted mode first, then reconnect."
     }
     // in shortReason:
     if errors.Is(err, db.ErrAccountModeConflict) {
         return "local_mode_active"
     }
     ```

     This reaches the user on whichever step page is polled next
     (`handleEnableCode`/`handleEnablePassword` around `enable_access.go:421-435,
     524-528, 598-602`), through the exact same `friendlyErr(lf.err)` /
     `shortReason(lf.err)` path already used for every other login failure
     — answering the issue's "what should `enable_access` do when it
     reaches this state mid-flow" question: nothing structurally new, it is
     just another `lf.err` value the existing polling/rendering plumbing
     already knows how to show, audited via the existing
     `s.store.LogToolCall(..., "connect:failed:"+shortReason(lf.err), ...)`
     call.

   - `cmd/login/main.go:212-214`: already wraps and calls `die(...)`, which
     prints the error and exits non-zero; `ErrAccountModeConflict`'s message
     is operator-readable as-is, no code change required beyond the store
     change itself.

4. **No change to `handleTelegramCallback`'s `CheckSessionValid` shortcut**
   (`internal/oauth/server.go:1122-1146`). It is not the enforcement point
   — `SaveSession` is — so it is left alone. This keeps the change minimal
   and localized to the store layer plus two message-mapping additions.

5. **No change to `SetAccountMode`, `ProvisionLocalAccount`, or
   `local_bridge_devices`.** The admin-gated local -> hosted path continues
   to work exactly as today; this proposal only removes the *unintentional*
   path.

## Alternatives

- **Guard only the `enable_access` handler (check `GetAccountMode` before
  starting the phone-entry wizard).** Rejected: this is exactly what the
  issue warns against — "guarding the handler alone leaves the store able
  to do it." It would miss `cmd/login/main.go` and any future caller of
  `SaveSession`, and it would not close the self-service-activation race
  (mode could still flip to local *after* the handler's check but *before*
  `SaveSession` runs, since the two operations are not atomic together
  unless the guard lives inside `SaveSession`'s own transaction).

- **Have `SaveSession` accept an explicit `expectedMode` parameter from each
  caller instead of reading current state.** Rejected: pushes the
  responsibility for correctness back onto every caller (the opposite of
  "single funnel"), and none of the three real callers has a reason to want
  anything other than "refuse if local" — there is no legitimate caller that
  should be allowed to silently overwrite a local account today.

- **Auto-convert instead of refuse: have `SaveSession` flip the existing
  local row to hosted and seal the session into it, in place, instead of
  revoking-and-replacing.** Rejected: this is precisely the silent,
  unconsented mode switch the issue is about, just implemented differently.
  The issue is explicit that `set_account_mode` should stay the only
  sanctioned way to move local -> hosted; auto-converting would remove the
  human decision point entirely rather than gate it.

## Platform impact

- **Migrations:** none. No schema change; `ErrAccountModeConflict` is a Go
  sentinel error, and the guard is a `SELECT` already covered by the
  existing transaction and existing `mode` column.
- **Backward compatibility:** behavior is unchanged for every account whose
  active row is `mode='hosted'` or has no active row — i.e., every account
  that does not use Local Bridge sees no change at all. Only the specific
  local-active-row case changes, from "silently destroyed" to "refused with
  an explanation," which is the acceptance criterion the issue asks for.
- **Resource impact:** negligible — one extra indexed `SELECT` (`user_id`,
  `revoked_at IS NULL`, ordered by `connected_at, id`) inside a transaction
  that already does two writes against the same table; no new table scan
  pattern beyond what `CheckSessionValid`/`GetAccountMode` already do
  routinely.
- **Risks + mitigations:**
  - *Risk:* a legitimate hosted reconnect for a user who is not actually
    using Local Bridge gets refused because of a stale/incorrect `mode`
    value. Mitigation: `mode` is only ever set to `'local'` by
    `ProvisionLocalAccount` or an explicit admin `set_account_mode` call —
    both deliberate actions — so a `'local'` value reflects real intent,
    not drift.
  - *Risk (residual, documented rather than solved here):* a narrow race
    between `ProvisionLocalAccount` committing and a `SaveSession` call for
    the same user that already passed its own mode read, both under
    default read-committed isolation. This mirrors a pre-existing exposure
    `ProvisionLocalAccount`'s own `WHERE NOT EXISTS` guard already has
    against a concurrent `SaveSession`. Not introduced by this change;
    tightening both together (e.g. `SELECT ... FOR UPDATE` where the
    backend supports it) is left as optional follow-up, per the open
    questions in requirements.md.
  - *Risk:* `enable_access`'s background goroutine runs the new check under
    `bgCtx`, detached from the original request context
    (`enable_access.go:203`, `context.WithoutCancel`-style pattern used
    elsewhere in this file, e.g. `store.go:983`). The refusal still commits
    synchronously inside `SaveSession`'s own transaction before returning,
    so there is no dangling background write to worry about — the goroutine
    either fully completes the refusal (no writes) or fully completes the
    save (both writes), same as today.
