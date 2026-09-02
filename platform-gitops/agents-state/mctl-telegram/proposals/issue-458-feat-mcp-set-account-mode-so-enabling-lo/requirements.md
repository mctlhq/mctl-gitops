# set_account_mode: admin MCP tool for Local Bridge mode

## Context
`telegram_accounts.mode` (`'hosted'` or `'local'`) decides whether a session runs server-side
MTProto or delegates to the user's Local Bridge daemon. `GetAccountMode` (`internal/db/store.go:1083`)
reads it, and `internal/bridge/server.go:65-73` enforces it — a daemon whose account is not
`mode='local'` gets HTTP 400 "account is in hosted mode". Nothing in the service writes the column.
The only writer today is an operator `UPDATE` shipped as a one-shot gitops `Job` (per the issue: a PR
to `mctl-gitops`, review, merge, an ArgoCD sync that needed a manual hard refresh per
mctlhq/mctl-gitops#970, then reading the Job's output to confirm) for what is, in database terms, a
single-row `UPDATE`. Treating a per-account runtime toggle as an infrastructure change is the wrong
shape: it is reviewed and lands on the deploy pipeline's schedule, and a completed one-shot `Job`
object cannot be re-run without renaming it because its pod template is immutable.

`toolSetAccountSend` (`internal/mcp/tools.go:951-1005`) is the established template for this class of
change: admin-scoped, resolves a Telegram id to the internal user id, writes one column on the active
`telegram_accounts` row, treats zero rows affected as a hard error rather than a silent success, and
audits the call. `set_account_mode` follows the same shape for the `mode` column, and additionally
must not silently create the 30-day idle-sweep time bomb the issue describes: `SweepIdleSessions`
(`internal/db/store.go:930-952`) revokes any active row whose `last_used_at` is stale, Local Bridge
calls never stamp `last_used_at` (only `Pool.Borrow` does, per `internal/telegram/clientpool.go:167`
and the issue's reference to `:460`), and a revoked row falls back to reporting `hosted` regardless of
its `mode` value (`GetAccountMode`'s `WHERE ... revoked_at IS NULL` plus its no-row default), so an
un-exempted local account silently reverts to hosted with a dead bridge after 30 days of otherwise
normal Local Bridge use.

## User stories
- AS an operator I WANT to flip an account between `hosted` and `local` mode with an MCP tool call
  SO THAT enabling Local Bridge for a pilot account is a runtime action instead of a gitops PR and
  ArgoCD sync.
- AS an operator I WANT the tool to fail loudly instead of reporting success when nothing was
  actually changed SO THAT I never tell a user "it's done" while their account is still in the wrong
  mode.
- AS an operator I WANT to be warned or blocked when I set `mode=local` for an account that is not
  exempt from the idle-session sweep SO THAT I don't silently arm a 30-day revert-to-hosted time bomb
  on an account with a live Local Bridge daemon.

## Acceptance criteria (EARS)
- WHEN an admin-scoped caller invokes `set_account_mode` with a valid `telegram_id` and `mode` of
  `"local"` or `"hosted"` for a Telegram id that has an active (non-revoked) `telegram_accounts` row
  THE SYSTEM SHALL update that row's `mode` column, audit-log the call, and return the new mode.
- IF the caller lacks the `admin:users` scope THEN THE SYSTEM SHALL reject the call before touching
  the database, matching `requireScope` in `toolSetAccess` and `toolSetAccountSend`.
- IF `mode` is anything other than `"local"` or `"hosted"` THEN THE SYSTEM SHALL reject the call with
  a validation error and SHALL NOT touch the database.
- IF `telegram_id` does not resolve to a known user (no `users` row, i.e. never signed in) THEN THE
  SYSTEM SHALL return an error naming the Telegram id and SHALL NOT report success.
- IF `telegram_id` resolves to a known user but that user has no active `telegram_accounts` row
  (never connected, or the row was revoked) THEN THE SYSTEM SHALL return an error explaining that the
  account must complete a hosted login first, rather than reporting a successful no-op update.
- IF `mode="local"` is requested for a `telegram_id` that is not present in the idle/absolute TTL
  exemption list (`SessionTTLExemptTGIDs` / `SESSION_TTL_EXEMPT_TG_IDS`, surfaced via
  `Store.ttlExempt`) THEN THE SYSTEM SHALL refuse the mode change and SHALL explain that the account
  will be auto-reverted to `hosted` by `SweepIdleSessions` after 30 days of Local Bridge-only use
  unless it is added to `SESSION_TTL_EXEMPT_TG_IDS` first.
- WHEN `set_account_mode` is called (success or failure) THE SYSTEM SHALL write an audit row via the
  same `s.audit(...)` mechanism used by `set_telegram_access` and `set_account_send`.
- WHILE the row being updated is not the caller's own account THE SYSTEM SHALL still require and
  enforce `admin:users`, matching every other cross-account admin tool in `internal/mcp/tools.go` —
  there is no self-serve path in this proposal.

## Out of scope
- Self-serve mode switching by the account owner (tracked separately in issue #138 — this proposal is
  deliberately the operator-only tool).
- Changing how `SESSION_TTL_EXEMPT_TG_IDS` is stored or applied (still a `SessionTTLExemptTGIDs`
  config value read from the environment at startup); this proposal only makes `set_account_mode`
  read that state and refuse an unsafe change, not replace the exemption mechanism with a
  database-backed one.
- Changing `SweepIdleSessions`, `CheckSessionValid`, or any other TTL/sweep behavior.
- A bulk/multi-account variant of the tool.
- Automatically stamping `last_used_at` from Local Bridge relay calls (that would remove the need for
  the exemption check entirely, but is a bigger behavioral change to the bridge relay path and not
  requested by the issue).

## Open questions
- Should the TTL-exemption check be a hard refusal or a warning that still lets the mode flip
  through? The issue says "at minimum it should refuse, or warn loudly" without picking one. This
  proposal picks hard refusal (see design.md Alternatives) because the exemption is edited in gitops
  regardless of this tool, so refusing costs the operator nothing they weren't already going to pay,
  and a warning is easy to miss in a one-line tool result versus a blocking error.
- Should there be an escape hatch (e.g. a `force` parameter) to bypass the exemption refusal for a
  short-lived pilot the operator knows will be re-checked soon? None is proposed here; if this
  becomes a real friction point, a follow-up can add one.
- Exact audit `detail` string content for this tool (the `s.audit` calls in `toolSetAccess` /
  `toolSetAccountSend` pass `""` for detail) — this proposal follows that precedent and passes `""`.
