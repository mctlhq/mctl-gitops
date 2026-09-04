# Design: issue-487-audit-per-account-send-enabled-false-in

## Current state

**Schema.** `internal/db/db.go` defines `telegram_accounts` with
`send_enabled INTEGER NOT NULL DEFAULT 0` (SQLite, line 323) /
`send_enabled BOOLEAN NOT NULL DEFAULT FALSE` (Postgres, line 421), and
`audit_logs` with `tool_name`, `status`, `created_at`
(lines 332-342 / 430-444). `internal/db/store_save_session_test.go`
(`TestSaveSession_SendEnabledDefaultFalse`) pins the false default at the
`Store.SaveSession` level.

**Gate.** `internal/mcp/tools.go`:
- `evaluateSendGateBeforeAccount` (line 1569) settles the identity-level
  conditions (auth present, not the demo reviewer, `ALLOW_SEND`, the
  `telegram:messages:send` scope) without touching the DB.
- `evaluateSendGate` (line 1546) calls it first, then, if undecided, reads
  `store.IsSendEnabled` (`internal/db/store.go:743`) and calls
  `evaluateSendGateAccountFlag` (line 1596), which returns the exact string
  `"per-account send_enabled=false — contact the operator to enable real
  sends for your account"` when the flag is off.
- `toolSendMessage` (line 342) calls `evaluateSendGate`, and on denial calls
  `s.audit(ctx, id, "send_message:draft", ...)` (line 398) before building a
  dry-run `telegram.SendResult` via `telegram.SendMessage(ctx, nil, peer,
  text, false, dryReason, nil, 0)` (`internal/telegram/send.go:37-50`). The
  dry-run branch never reaches the real Telegram API.
- `toolGetMySendStatus` (line 849, shipped in #488) reports the three gate
  booleans (`server_allow_send`, `has_send_scope`, `send_enabled`) plus
  `can_send`/`reason` by calling `evaluateSendGateBeforeAccount` and, when
  undecided, reading `GetActiveAccount` once and calling
  `evaluateSendGateAccountFlag` on that single snapshot. This is the
  self-service diagnosis surface item 3 of the issue asked for; it already
  exists.

**Admin surface.** `list_telegram_identities` and `set_account_send`
(`internal/mcp/tools.go`, both behind `requireScope(id, "admin:users")`) are
the only tools that could enumerate accounts and their `send_enabled` state,
but `admin:users` is granted purely from `TG_LOGIN_ADMINS` membership
(`internal/oauth/scopes.go`, comment at line 7) — a Telegram-identity-based
allowlist, unrelated to whether the caller has infrastructure/DB access. The
issue's reporter hit exactly this wall in production. `ListIdentities`
(`internal/db/store.go:346`) additionally does not currently select
`send_enabled` at all — it only reports `HasSession`/`AccessTier`, so even
with the scope, `list_telegram_identities` could not answer the issue's
question today.

**Existing operator precedent.** `docs/runbook.md` already documents raw SQL
against `telegram_accounts` and `audit_logs` for on-call diagnostics, e.g.
(around line 1233):
```sql
SELECT user_id, mode, revoked_at, last_used_at
FROM telegram_accounts WHERE mode = 'local';

SELECT call_path, COUNT(*) FROM audit_logs
WHERE created_at >= NOW() - INTERVAL '1 hour'
GROUP BY call_path;
```
This establishes that "operator runs a documented SQL query against
production" is an accepted, already-used pattern in this codebase for
one-off diagnostics that do not justify a new MCP tool.

## Proposed solution

Two independent pieces, matching the issue's two open tasks:

**1. Audit (task 1) — a documented SQL query, not a new tool.**
Add a new runbook section to `docs/runbook.md`, next to the existing
`telegram_accounts` / `audit_logs` queries, with:
```sql
-- Accounts with an active session that have never opted into real sends.
SELECT ta.user_id, ta.telegram_user_id, ta.username, ta.connected_at,
       ta.last_used_at
  FROM telegram_accounts ta
 WHERE ta.send_enabled = FALSE
   AND ta.revoked_at IS NULL
 ORDER BY ta.last_used_at DESC NULLS LAST;

-- Of those, which ones tried to send recently and got a silent dry-run.
SELECT al.user_id, COUNT(*) AS draft_attempts,
       MIN(al.created_at) AS first_attempt, MAX(al.created_at) AS last_attempt
  FROM audit_logs al
  JOIN telegram_accounts ta ON ta.user_id = al.user_id
 WHERE al.tool_name = 'send_message:draft'
   AND ta.send_enabled = FALSE
   AND ta.revoked_at IS NULL
   AND al.created_at >= NOW() - INTERVAL '7 days'  -- adjust window as needed
 GROUP BY al.user_id
 ORDER BY draft_attempts DESC;
```
This directly answers the issue's task 1 ("count disabled+active accounts,
cross-reference with recent `send_message:draft` rows") without requiring
`admin:users` scope on any particular Telegram identity — it needs only the
DB access an operator running the runbook already has, matching the
precedent above. This is documentation-only; no code or schema changes are
needed, since both columns and the `send_message:draft` audit action already
exist and are written today.

**2. Active nudge (task 2) — a hint in the dry-run result, gated to the
specific cause.**
Change is localized to `internal/mcp/tools.go` and `internal/telegram/send.go`:

- Extract the account-flag-off message currently inlined in
  `evaluateSendGateAccountFlag` into a package-level constant, e.g.
  `const reasonSendDisabled = "per-account send_enabled=false — contact the
  operator to enable real sends for your account"`, and have
  `evaluateSendGateAccountFlag` return it. This turns "was denial caused
  specifically by the per-account flag, as opposed to `ALLOW_SEND` or the
  OAuth scope" into an exact, non-fragile comparison against one constant
  defined once, rather than re-deriving the condition or comparing against a
  string literal duplicated at the call site.
- Add a `Hint string `json:"hint,omitempty"`` field to
  `telegram.SendResult` (`internal/telegram/send.go:15-28`), populated only
  in the dry-run branch of `SendMessage` when the caller passes a non-empty
  hint argument (extend the function signature or set it in `toolSendMessage`
  after the call, whichever keeps `internal/telegram` free of MCP-layer
  concerns — `internal/telegram` currently has no knowledge of `/manage` or
  scopes, so setting `result.Hint` in `toolSendMessage` after
  `telegram.SendMessage` returns keeps that separation intact).
- In `toolSendMessage` (line 374-401), after computing `dryReason`, compare
  it against `reasonSendDisabled`. When it matches, set:
  `"Your account has never opted into real sends. Turn it on from /manage,
  or call get_my_send_status to confirm this is the reason."`
  For every other `dryReason` (`ALLOW_SEND=false`, missing scope, reviewer
  account, rate limit), leave `Hint` empty — none of those are fixed by
  `/manage`, and a nudge naming the wrong fix would be actively misleading.
- No change to `evaluateSendGate`, `evaluateSendGateBeforeAccount`,
  `evaluateSendGateAccountFlag`'s boolean return, or the `s.audit(...,
  "send_message:draft", ...)` call — the gate's authority and the audit trail
  are unchanged; this is presentation-only, added after the verdict is
  already final.

This keeps the two tasks decoupled: the audit is a read-only, no-deploy
runbook addition usable immediately in production today; the nudge is a
small, testable code change that reduces how many future accounts end up
undiscovered in this state, without touching the gate that decides whether a
send is real.

## Alternatives

1. **New `admin:users`-scoped MCP tool (e.g. `audit_send_enabled`) that runs
   the aggregate query server-side.** Rejected: the issue's own blocker is
   that the reporter's production connector identity lacks `admin:users`,
   which is granted purely via `TG_LOGIN_ADMINS`. A new tool behind the same
   scope would hit the identical wall for the same caller and does not save
   an operator who already has DB access anything a documented query
   doesn't. It would also add a maintained code path (with tests, output
   schema, docs) for what is described in the issue as a one-off count, not
   a recurring operational need.
2. **Auto-enable `send_enabled=true` for accounts with repeated
   `send_message:draft` attempts, instead of a passive hint.** Rejected: the
   corrected issue text explicitly reframes `send_enabled=false` as the
   deliberate default state, not a bug to route around. Silently flipping it
   based on usage pattern would bypass the intentional opt-in gate (the
   browser checkbox / `/manage`) that exists specifically so a user
   consciously accepts that messages will be sent for real, and would surprise
   a user who was intentionally previewing.
3. **Push a proactive notification (Telegram DM, email) to affected users
   instead of an in-result hint.** Rejected for this proposal: `send_message`
   already returns to the caller synchronously on every attempt, so the
   cheapest and most reliable delivery point for "you are not really sending"
   is the response the caller is already reading, per the second acceptance
   criterion. A proactive channel adds delivery-failure and audit-log-noise
   surface (`docs/runbook.md`'s existing DM/notification playbooks show this
   is already a source of operational friction) for a message that can be
   said synchronously instead. Recorded as out of scope, not rejected
   permanently — a good follow-up once/if the hint alone proves insufficient.

## Platform impact

- **Migrations:** none. `send_enabled` and `audit_logs.tool_name` already
  exist in both the SQLite and Postgres schemas
  (`internal/db/db.go`); the runbook query only reads them.
- **Backward compatibility:** `SendResult.Hint` is additive
  (`omitempty`), so existing callers parsing `sent`/`mode`/`dry_reason` are
  unaffected; only new, empty-when-absent JSON appears for the specific
  denial cause this proposal targets. `evaluateSendGateAccountFlag`'s
  existing return values (`bool`, `string`) are unchanged in shape and value
  — only where the string literal lives changes.
- **Resource impact:** negligible. The nudge is a string comparison and
  assignment on an already-computed value, on the already-slow-path (dry-run,
  no Telegram API call). The audit query is a manual, operator-run,
  ad hoc SELECT, not a new scheduled job or endpoint.
- **Risks + mitigations:**
  - *Risk:* the hint text drifts from `reasonSendDisabled` if someone edits
    one but not the other. *Mitigation:* extracting the message into one
    named constant used by both the gate and the comparison (rather than two
    independent string literals) makes drift a compile-time-visible
    single-source change; add a unit test asserting
    `evaluateSendGateAccountFlag`'s reason equals the constant the hint logic
    checks against, so a future edit to one without the other fails a test
    instead of silently diverging.
  - *Risk:* someone reads the hint condition as "if dry_reason contains
    'send_enabled'" and loosens it to a substring match, which could
    misfire if `ALLOW_SEND`'s message is ever reworded to also mention
    "send_enabled". *Mitigation:* use exact equality against the shared
    constant, not a substring/contains check, and cover it with a test
    exercising all four `dryReason` causes (reviewer, `ALLOW_SEND`, missing
    scope, account flag) asserting `Hint` is empty for the first three and
    populated only for the fourth.
  - *Risk:* the runbook query's audit window (`INTERVAL '7 days'` in the
    example) undercounts a slow-burn case (someone tries once a month).
    *Mitigation:* documented as an adjustable parameter in the runbook text,
    not a fixed constant; the requirements record this as an explicit open
    question rather than a silently chosen default.
  - *Risk:* the audit query is Postgres-flavored (`NOW() - INTERVAL`,
    `NULLS LAST`) and the runbook is written primarily for the production
    (Postgres) deployment, per the schema split in `internal/db/db.go`. Not a
    risk for the stated audit (issue explicitly says "production"), but
    worth noting in the runbook text so nobody pastes it unmodified against a
    local SQLite dev DB.
