# Audit per-account send_enabled=false in production and add an active nudge for silent dry-run

## Context

`internal/db/db.go` inserts every new `telegram_accounts` row with
`send_enabled` defaulting to false (SQLite: `send_enabled INTEGER NOT NULL
DEFAULT 0`; Postgres: `send_enabled BOOLEAN NOT NULL DEFAULT FALSE`), and
`internal/db/store_save_session_test.go`
(`TestSaveSession_SendEnabledDefaultFalse`) locks that in. The flag is turned
on only by the opt-in checkbox in the browser connect flow or later on
`/manage` (`internal/web/manage.go`). Because of this, `send_message`
(`internal/mcp/tools.go`, `toolSendMessage`) silently falls back to a
draft/dry-run preview (`sent: false`, `dry_reason: "per-account
send_enabled=false ..."`) for any account that never opted in — this is normal,
expected default state, not evidence that someone revoked access.

The issue (corrected 2026-09-03) no longer asks "who turned this off"; it asks
two things instead:

1. How many production accounts with an active session are stuck in this
   default-disabled, dry-run-only state, and, of those, how many show recent
   `send_message:draft` audit rows — i.e. someone is actively trying to send
   and has no idea it silently isn't happening.
2. Whether repeated `send_message:draft` activity from a disabled account
   deserves an active nudge pointing at `/manage`, instead of relying on the
   caller to notice the `dry_reason` field or to already know about
   `get_my_send_status` (shipped in #488).

The person who filed the issue could not run this audit themselves: the
production MCP connector's identity lacks the `admin:users` scope, so both
`list_telegram_identities` and `set_account_send`
(`internal/mcp/tools.go`, guarded by `requireScope(id, "admin:users")`) refuse
with "identity missing scope admin:users". `admin:users` is granted only via
`TG_LOGIN_ADMINS` membership (see `internal/oauth/scopes.go`), so this is a
config/identity gap, not a bug in the gate itself. Operators already run
direct SQL against `telegram_accounts` and `audit_logs` for other
runbook diagnostics (`docs/runbook.md`, e.g. the Local Bridge section's
`SELECT user_id, mode, revoked_at, last_used_at FROM telegram_accounts ...`
and `SELECT call_path, COUNT(*) FROM audit_logs ... GROUP BY call_path`), so
this proposal follows that established, no-new-tool pattern for the one-off
audit, and adds a small code change for the recurring nudge.

Item 3 from the issue ("give a non-admin caller a way to learn their own send
state") is already delivered by `get_my_send_status`
(`internal/mcp/tools.go`, `toolGetMySendStatus`, shipped in #488) and is out
of scope here.

## User stories

- AS an operator I WANT a documented, repeatable query for counting
  disabled-but-active accounts and cross-referencing recent
  `send_message:draft` audit rows SO THAT I can answer "how many users are
  unknowingly in dry-run" without needing `admin:users` scope on any
  particular MCP identity.
- AS a user whose account has `send_enabled=false` I WANT a hint in the
  `send_message` dry-run result when I keep trying to send SO THAT I discover
  I am not actually sending without having to parse `dry_reason` or already
  know about `get_my_send_status`.
- AS a maintainer I WANT the nudge logic covered by tests and to leave the
  gate's authoritative behavior (still draft, never a real send) unchanged SO
  THAT this proposal cannot accidentally turn dry-run into a real send path.

## Acceptance criteria (EARS)

- WHEN an operator runs the documented audit query against the production
  database THE SYSTEM SHALL report, for each `telegram_accounts` row with
  `send_enabled = false` and an active session (`revoked_at IS NULL`), whether
  it has at least one `audit_logs` row with `tool_name = 'send_message:draft'`
  in a specified recent window.
- WHEN `send_message` (`internal/mcp/tools.go`) returns a dry-run preview
  because `evaluateSendGateAccountFlag` failed specifically on the
  per-account `send_enabled` condition (not on `ALLOW_SEND` or the OAuth
  scope) THE SYSTEM SHALL include a one-line, non-alarming hint in the result
  pointing the caller at `/manage` to opt in.
- IF the dry-run is caused by `ALLOW_SEND=false` or a missing
  `telegram:messages:send` scope THEN THE SYSTEM SHALL NOT show the
  `/manage` nudge, because opting in on `/manage` would not fix either of
  those conditions.
- WHILE the send gate is evaluating a request THE SYSTEM SHALL continue to
  treat `send_enabled=false` as an unconditional block on real sends —
  the nudge is presentation only and SHALL NOT alter `canSend`,
  `evaluateSendGate`, or any gate condition.
- WHEN the nudge is added to the dry-run result THE SYSTEM SHALL keep the
  existing `SendResult` JSON fields unchanged in meaning (only an additive
  field/text), so existing callers parsing `sent`/`dry_reason` are unaffected.
- WHERE the audit query is documented THE SYSTEM SHALL place it in
  `docs/runbook.md` alongside the existing `telegram_accounts` /
  `audit_logs` operator queries, following the same format (SQL block plus a
  short interpretation note).

## Out of scope

- Building a new `admin:users`-scoped MCP tool to run this audit
  programmatically. The issue's own blocker (no connector identity has
  `admin:users` in production) would apply equally to a new tool; a
  documented SQL query available to anyone with production DB/read access
  (the same access level the runbook already assumes) sidesteps that.
- Granting `admin:users` / adding Telegram IDs to `TG_LOGIN_ADMINS` for any
  specific identity — that is an operational/config decision for whoever
  owns the production deployment, not a code change.
- Changing the default value of `send_enabled` or auto-enabling it for any
  account. The corrected issue text is explicit that `false` is the intended
  default, not a bug.
- `get_my_send_status` itself — already shipped in #488.
- Proactive, out-of-band notification (email/Telegram DM) to affected users.
  The acceptance criteria only cover a nudge inside the tool result the
  caller already receives.
- Rate-limiting or deduplicating the nudge text across repeated calls; it is
  static per-response, not a stateful "you've been told N times" counter.

## Open questions

- The issue asks about "repeated" `send_message:draft` rows as the trigger
  for a nudge, suggesting a threshold (e.g. 3+ in 24h) rather than every
  single dry-run. This proposal shows the nudge on every dry-run caused by
  `send_enabled=false`, since a stateful repeat-counter would need a new
  query per send and a definition of "repeated" the issue does not supply.
  If a threshold is later wanted, it can be layered on top of the
  `evaluateSendGateAccountFlag` check point identified in the design without
  changing the gate itself.
- No specific audit time window ("recent") is given in the issue. This
  proposal's runbook query parameterizes the window (documented as a
  `days`-style interval) rather than hardcoding one, and suggests 7 and 30
  days as the two values an operator would plausibly want; the exact window
  used for any given audit run is an operator judgment call, not fixed by
  this proposal.
- Whether the `/manage` hint text should mention `get_my_send_status` by name
  (self-service diagnosis) versus only the opt-in checkbox (direct fix). This
  proposal's design favors mentioning both briefly, since a caller who has
  already checked `get_my_send_status` and understood the cause does not need
  to be told about it a second time, but one who has not benefits from the
  pointer.
