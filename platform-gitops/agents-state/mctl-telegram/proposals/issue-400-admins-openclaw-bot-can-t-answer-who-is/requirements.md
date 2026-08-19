# Add a scoped, session-less admin:users tier so the admins/openclaw bot can look up Telegram identities

## Context

The OpenClaw agent that answers in the `mctl_admins` Telegram chat has no tool
that can resolve "who is Telegram user `8883561385`". `mctl-telegram` already
implements exactly that lookup as two admin-only MCP tools —
`list_telegram_identities` and `get_user_audit_log`
(`internal/mcp/tools.go:871`, `:1010`, both gated on the `admin:users`
scope) — but the `admins` tenant's OpenClaw config only wires up the `mctl`
and `github` MCP servers, not `mctl-telegram`. When the underlying model has
no tool for the request it either hallucinates a call or the run fails, and
the failure is swallowed into a generic error string by
`mctl-openclaw`'s `agent-runner-execution.ts`.

The blocking reason this isn't "just add an MCP server to values.yaml" is
`mctl-telegram`'s OAuth grant model: `internal/oauth/server.go` only supports
`authorization_code` (a real Telegram Login Widget sign-in) and
`refresh_token` — there is no service-account / client-credentials grant
(`internal/oauth/server.go:1359-1366`). Any token wired into the bot is
therefore always bound to one concrete Telegram account via
`ResolveScopes(ctx, tgID)` (`internal/oauth/server.go:666`). Today that
function only knows two privileged shapes: the `admins` env allowlist, which
bundles `admin:users` together with the *full* `telegram:*` messaging scope
set (dialogs read, messages read/send/pin) for that account's own session,
or the `clients` tier, which has `telegram:*` but not `admin:users`. There is
no tier that grants `admin:users` on its own. Reusing a real admin's personal
token would hand the bot that admin's live messages; even a brand-new
"empty" dedicated account, once added to `TG_LOGIN_ADMINS`, still gets a
working MTProto session with real read/send/pin capability it does not need
for the "who is this client" use case — `list_telegram_identities` and
`get_user_audit_log` are both pure `s.Store` reads (`ListIdentities`,
`ListAuditFor` via `UserIDByTelegramID`) that never touch the caller's own
Telegram session at all.

This proposal adds a narrower, purpose-built tier — `admin:users` only, no
`telegram:*` messaging scopes, no MTProto session provisioning — so a
dedicated lookup-only service account can be wired into `admins/openclaw`
with a token that is provably incapable of reading or sending real Telegram
messages, closing the gap without relying on "the account happens to be
empty" as the only safety net.

## User stories

- AS an operator answering in `mctl_admins` I WANT the bot to look up a
  Telegram user's identity and access tier from a digest entry SO THAT I can
  answer "who is this client" without manually querying the database.
- AS a platform admin provisioning the lookup bot's credentials I WANT a
  Telegram account that can only call `admin:users` tools SO THAT a leaked or
  misused token cannot read or send real Telegram messages.
- AS a security reviewer I WANT the `admin:users`-only tier to be enforced by
  the OAuth scope grant, not by convention ("this account has no personal
  chats") SO THAT the guarantee holds even if the dedicated account later
  accumulates real conversations.

## Acceptance criteria (EARS)

- WHEN a Telegram id is present in the new lookup-admin allowlist AND is not
  also present in the full-admin (`TG_LOGIN_ADMINS`) allowlist THE SYSTEM
  SHALL resolve its scopes to exactly `["admin:users"]` and its groups to a
  distinct group name (not `platform-admins`/`admins`), granting none of
  `telegram:dialogs:read`, `telegram:messages:read`,
  `telegram:messages:send`, `telegram:messages:pin`.
- WHEN a Telegram id is present in both the lookup-admin and full-admin
  allowlists THE SYSTEM SHALL resolve it via the existing full-admin branch
  (full `telegram:*` plus `admin:users`) — full admin takes precedence, so
  listing an id in both is a safe no-op, not a downgrade.
- WHEN a lookup-admin-only identity completes the Telegram Login Widget sign-in
  THE SYSTEM SHALL issue the authorization code directly, without offering
  the phone/SMS/2FA `enable_access` MTProto provisioning flow, because the
  granted scope set has no use for a session.
- WHEN `list_telegram_identities` or `get_user_audit_log` is called with an
  identity carrying only the `admin:users` scope THE SYSTEM SHALL serve the
  request exactly as it does today for a full admin (no behavior change to
  the tool handlers — they already gate on scope, not on tier/group).
- IF a lookup-admin-only identity calls any `telegram:*`-scoped tool (e.g.
  `list_dialogs`, `send_message`) THEN THE SYSTEM SHALL reject it with the
  existing missing-scope error (`requireScope`, `internal/mcp/tools.go:1196`)
  — unchanged, since no `telegram:*` scope was ever granted.
- WHILE the lookup-admin allowlist is empty (unset env var) THE SYSTEM SHALL
  behave exactly as it does today — this is strictly additive, no change to
  existing admin/client/none resolution.
- WHEN the `admins/openclaw` MCP config is updated to add `mctl-telegram` as
  a server using the dedicated lookup account's refresh token THE SYSTEM
  SHALL expose `list_telegram_identities` and `get_user_audit_log` to that
  agent (this step lives in `mctl-gitops`, tracked as a follow-up task here
  since it is outside this repo).

## Out of scope

- The `mctl-gitops` change wiring the new MCP server into
  `services/admins/openclaw/values.yaml` — a config/ops change in another
  repo, not `mctl-telegram` code. Tracked as a dependent follow-up task.
- The `mctl-openclaw` classifier for "no matching tool" mentioned in the
  issue as item 3 (`agent-runner-execution.ts` catch, generic
  `GENERIC_EXTERNAL_RUN_FAILURE_TEXT`) — a separate platform-wide UX problem
  in a different repo, explicitly called out in the issue as not blocking
  items 1-2.
- Provisioning the actual dedicated Telegram phone number and running the
  one-time Login Widget sign-in — an operational/ops action, not code.
- Changing `EnsureUserByTelegramID(displayName="")` behavior in
  `internal/auth/localjwt/issuer.go:232` / `internal/oauth/server.go:1462` —
  explicitly called out in the issue as intentional and unrelated.
- Issue #399 (OAuth revoke) — explicitly unrelated per the issue.
- Any change to what `list_telegram_identities` / `get_user_audit_log`
  return — this proposal only changes how a caller can reach `admin:users`
  without also getting `telegram:*`, not the tools' behavior or output shape.
- A DB-backed (`users.access_tier`) version of the lookup-only tier. The
  existing `admins` tier is env-only (`TG_LOGIN_ADMINS`, not DB); this
  proposal follows that same precedent (env-only allowlist,
  `TG_LOGIN_LOOKUP_ADMINS`) for consistency and because it requires no
  migration. Making it DB-managed (like `set_telegram_access` does for the
  client tier) is left as a future enhancement if the platform wants
  runtime, no-redeploy grant/revoke for this tier too.

## Open questions

- Exact env var / scope / group naming: this proposal uses
  `TG_LOGIN_LOOKUP_ADMINS` and scope group `"admin-lookup"` as concrete
  placeholders. No naming convention for sub-tiers exists yet in the repo;
  the implementer should pick names consistent with the existing
  `TG_LOGIN_ADMINS`/`TG_LOGIN_CLIENTS`/`platform-admins`/`clients` style and
  may deviate from the placeholder names if a clearer one is found during
  implementation.
- Whether the platform ultimately wants the issue's literal ask (reuse the
  existing full-admin tier with a "clean" dedicated account, accepting a
  working MTProto session as the mitigated risk) instead of this narrower
  scoped tier. This proposal implements the stronger option grounded in what
  the two target tools actually touch (`s.Store`, no MTProto session) because
  it fully removes the "real human token" risk the issue itself calls out
  in Причина №2, rather than just shrinking its blast radius. If the
  narrower tier is rejected, tasks 1-4 in tasks.md are skippable and the
  operator can instead add the dedicated account straight to
  `TG_LOGIN_ADMINS` with no code change.
- Whether `list_telegram_identities`'s `access_tier` output field should
  eventually reflect env-sourced admin/lookup-admin status (it currently
  only reflects the DB `client`/`none` column, so an admin or lookup-admin
  row shows `"none"` even though the caller has elevated scopes). Not
  required for this proposal — flagging as a pre-existing gap noticed while
  reading `internal/mcp/tools.go:881` and `internal/db/store.go:249`.
