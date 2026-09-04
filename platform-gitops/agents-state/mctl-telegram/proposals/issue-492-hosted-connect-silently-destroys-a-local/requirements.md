# Make Store.SaveSession refuse to overwrite an active local-mode account

## Context
The Local Bridge self-service chain (#479, #481-#484) rests on one invariant:
a `mode='local'` `telegram_accounts` row never carries a server-side MTProto
session — `session_encrypted` stays `NULL` for its whole life, because the
session lives on the user's own machine and `tg.mctl.ai` only relays. #484's
Definition of Done makes `session_encrypted IS NULL` an explicit acceptance
criterion for local-mode accounts.

Nothing in the code enforces that invariant against the hosted login path.
`Store.SaveSession` (`internal/db/store.go:431-469`) is the single funnel
every hosted-session write goes through: the browser `/telegram/connect` ->
`enable_access` wizard (`internal/oauth/enable_access.go:203`) and the
operator CLI (`cmd/login/main.go:212`) both call it after a completed
MTProto phone/SMS/2FA login. `SaveSession` unconditionally revokes every
currently-active row for the user (`UPDATE ... SET revoked_at = ...
WHERE user_id = $1 AND revoked_at IS NULL`) and inserts a new row that omits
`mode`, so it takes the column default `'hosted'` (`internal/db/db.go:123-124`,
`internal/db/db.go:328,426`) and carries a non-NULL sealed session.

If a user's currently-active row is `mode='local'` (created via
`Store.ProvisionLocalAccount`, `internal/db/store.go:846-864`, part of the
#481-#484 self-service activation flow) and a hosted login for the same
`users.id` reaches `SaveSession`, that local row is silently revoked and
replaced by a hosted row with a live server-side session. The
`local_bridge_devices` row registered against that user
(`internal/db/db.go:384-394`) is left pointing at a user whose active
account is no longer the local one it was registered against.

`Store.ProvisionLocalAccount` already refuses to create a local account over
an active row of any mode (the #482 guard, `WHERE NOT EXISTS (... revoked_at
IS NULL)`). The reverse direction has no equivalent guard: nothing stops a
hosted login from running over an active local row. The only sanctioned way
to move local -> hosted is the admin-gated `set_account_mode` MCP tool
(`internal/mcp/tools.go:1139-1214`, `internal/db/store.go:783-793`), which
flips the `mode` column in place without touching `session_encrypted` or
revoking anything. `SaveSession` bypasses that gate entirely.

## User stories
- AS a user who has activated Local Bridge for my account, I WANT the hosted
  connect flow to refuse to silently take over my account SO THAT my MTProto
  session cannot end up stored on the server without my explicit action.
- AS an operator running the interactive login CLI, I WANT the same
  protection to apply regardless of which code path invokes session save SO
  THAT no caller of the shared store layer can bypass the invariant.
- AS a user who is told the hosted connect flow was refused, I WANT a clear
  explanation and the correct next step SO THAT I understand how to
  intentionally switch my account back to hosted mode.

## Acceptance criteria (EARS)
- WHILE a user's current active `telegram_accounts` row has `mode='local'`,
  THE SYSTEM SHALL refuse any call to `Store.SaveSession` for that user with
  a distinguishable, typed error, and SHALL NOT revoke the local row or
  insert a replacement row.
- WHEN `Store.SaveSession` refuses because the active row is `mode='local'`,
  THE SYSTEM SHALL leave `telegram_accounts.session_encrypted` for that row
  exactly as it was (`NULL`) and SHALL leave `revoked_at` `NULL`.
- WHEN the browser `enable_access` flow's background login goroutine
  receives the local-mode-conflict error from `SaveSession`
  (`internal/oauth/enable_access.go:203`), THE SYSTEM SHALL surface a
  specific, human-readable explanation ("this account runs Local Bridge;
  switch it back to hosted first") on the next polled step page, instead of
  the generic "save session" failure text.
- WHEN the operator CLI (`cmd/login/main.go:212`) hits the same refusal, THE
  SYSTEM SHALL report the same typed error text on exit rather than a
  generic failure.
- IF a user's current active row is `mode='hosted'` (or there is no active
  row at all), THEN THE SYSTEM SHALL continue to allow `SaveSession` to
  revoke-and-replace exactly as it does today — this proposal changes
  behavior only for an active local row.
- WHILE the admin-gated `set_account_mode` tool is used to move an account
  from `local` to `hosted`, THE SYSTEM SHALL continue to allow that
  transition unchanged — it remains the only sanctioned way to make this
  switch.
- WHERE a caller other than `enable_access` or `cmd/login` invokes
  `Store.SaveSession` directly against the hosted database (present or
  future), THE SYSTEM SHALL apply the same refusal, because the guard lives
  in the shared store funnel rather than in any one handler.

## Out of scope
- Changing what `set_account_mode` does to `session_encrypted` or
  `local_bridge_devices` on an explicit local -> hosted switch. Today
  `SetAccountMode` (`internal/db/store.go:783-793`) only flips the `mode`
  column and leaves `session_encrypted` (`NULL` on a local row) and
  `local_bridge_devices` untouched; that is a pre-existing gap unrelated to
  the silent-overwrite bug this proposal closes, and is called out as an
  open question below rather than fixed here.
- Automatically revoking or cleaning up `local_bridge_devices` rows as part
  of this fix. Since the fix prevents the silent local -> hosted transition
  outright, the specific orphaning scenario in the issue (a device row left
  pointing at a no-longer-local account) can no longer happen via
  `SaveSession`; device-row lifecycle on an intentional `set_account_mode`
  switch is separate follow-up work.
- Rewriting `enable_access`'s architecture (background goroutine + polling
  steps, `uidLoginMutex` serialization). This proposal only adds a new
  branch to the existing error-rendering path (`friendlyErr`/`shortReason`,
  `internal/oauth/enable_access.go:659-716`).
- The #490 issue (revoked device can never be re-registered) — related but
  independent, not addressed here.
- Extending #484's E2E test suite beyond what is needed to cover this
  specific regression; the general "assert `session_encrypted IS NULL` after
  every step" hardening for #484's own E2E run is tracked there, though this
  proposal's own tests exercise the same assertion at the unit/integration
  level for the exact path being fixed.

## Open questions
- Whether `local -> hosted` via `set_account_mode` should also revoke
  `local_bridge_devices` rows, versus leaving them for the user/operator to
  clean up. The issue raises this explicitly as unresolved ("Leaving live
  device rows attached to a now-hosted account is its own inconsistency")
  but does not mandate an answer. Most reasonable interpretation: leave it
  out of scope here (see above) since it is orthogonal to the silent
  overwrite this proposal closes, and file it as separate follow-up.
- Whether `SetAccountMode`'s local -> hosted transition should also require
  (or produce) a non-NULL `session_encrypted`, given a `mode='hosted'` row
  with `session_encrypted IS NULL` is unusable for any MTProto call. Not
  introduced by this proposal (the gap pre-exists it), flagged for a
  separate proposal.
- Whether the residual narrow race — a `ProvisionLocalAccount` call
  committing concurrently with a `SaveSession` call already past its
  local-mode read, for the same user, both within their default read-committed
  transactions — needs stronger isolation (e.g. `SELECT ... FOR UPDATE` on
  Postgres) to close completely. `ProvisionLocalAccount` itself has the same
  class of exposure today via its own `WHERE NOT EXISTS` guard. Most
  reasonable interpretation: accept this as a documented, pre-existing class
  of risk rather than solving general cross-flow concurrency in this
  proposal; call it out in design.md and revisit only if it is observed in
  practice.
