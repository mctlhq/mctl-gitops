# Design: issue-902-reduce-one-day-drop-off-phone-step-chann

## Current state

### Connect funnel and audit steps
- `internal/oauth/server.go:1968` writes `connect:oidc_callback` after Telegram sign-in.
- `internal/oauth/enable_access.go` writes `connect:phone_submitted` (l.849), `connect:code_submitted`, `connect:2fa_submitted`, `connect:failed:<reason>` and `connect:success` (l.1149, in `finishEnable`), all through `s.store.LogToolCall(... db.ToolCall{Tool: "connect:..."})`. MCP tool calls are logged to the same `audit_logs` table under the bare tool name (e.g. `list_dialogs`, `send_message:blocked`). No call site uses a non-`connect:` prefix for anything other than MCP tools.
- `internal/db/connect_step.go` `LastConnectStepFor` already queries the last `connect:*` row per user for the daily digest (`internal/digest/digest.go`).

### Phone-number screen
- `internal/oauth/enable_access_page.go` `enablePhoneTemplate` (l.142-166) shows a 4-step wizard header in wizard mode, then one paragraph ("this server needs a Telegram session. Enter your phone number...") and a meta line ("The server stores an encrypted session blob — never your password."). It does not explain why a second step is needed after Telegram sign-in, does not say what happens to the number, and gives no disconnect path or link to `/privacy` or `/security`.
- `internal/web/privacy.html` already states that the phone number is not stored after interactive login (l.121). Disconnect options already exist: the manage page (`/telegram/connect/manage`, `internal/web/manage.go` `CanDisconnect`) and the `disconnect_telegram_account` tool (`internal/mcp/tools.go` l.830).
- Pages are rendered by `renderEnable` under a strict CSP with a per-request nonce only for the success page script.

### Broadcast-channel refusal (as of 0.98.1)
- 0.98.0 (#905) added the `BROADCAST_CONTENT_ENABLED` kill switch, on by default. With it on, channel posts are read and sponsored messages are attached; nothing is refused. With it off, `refuseBroadcastPeer` (`internal/telegram/broadcast_content.go`) refuses every channel that is not positively a megagroup, and `broadcastContentError.Error()` says "MCTL Assistant does not read channel posts ... The channel stays listed in list_dialogs". It does not say that retrying will not help.
- `internal/mcp/tools.go` `borrowErrResult` maps the refusal to `ReasonRefused`; `internal/mcp/media_tools.go` does the same for media.
- `internal/mcp/errorcatalog.go` `CHANNEL_INVALID` action: "Call list_dialogs and pass the id exactly as returned there ..." It does not say to stop retrying. `CHANNEL_INVALID` has been steady since July: the model passes channel ids that are not in the user's dialog list.
- Tool surface changes are gated: `internal/mcp/descriptors.go` generates `docs/tool-descriptors*.json`, and `internal/productupdate/gate.go` with `cmd/productupdates` requires a `docs/product-updates/*.yaml` entry for schema changes.

### Success pages
- External OAuth clients (claude.ai, chatgpt.com, ...): `internal/oauth/server.go` `issueAuthCode` renders `connectSuccessPage` (`enable_access_page.go` l.250) with "Telegram connected. Returning you to {{.AppName}}..." and a 1.2 s auto-redirect. The connector is already added in that client.
- Self-hosted wizard (`/telegram/connect`, `AUTH_MODE=local-jwt`): `internal/web/connect.go` `connectSuccessTemplate` (l.452) shows the MCP URL and Claude-only instructions ("open the Claude.ai connector settings and add the MCP URL"), notification choice and the login-bot start link. ChatGPT and other clients are not covered.

### Deployed state checked
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: tenant `labs`, image tag `0.96.0` at proposal time (0.98.1 by the amendment), `AUTH_MODE: local-jwt` (so the `/telegram/connect` wizard and its success page are mounted), `OAUTH_ISSUER_URL: https://tg.mctl.ai`, `OAUTH_ALLOWED_IMPLICIT_HOSTS` includes claude.ai, claude.com, chatgpt.com, antigravity.google, cursor.com and town.com, `TELEGRAM_LOGIN_BOT_USERNAME: "MCTL_AI_bot"`, `TELEGRAM_LOGIN_BOT_TOKEN` from a secret, `BOT_RECEIVER_ENABLED` deliberately absent (comment l.181), and a single replica (l.243, l.679).
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml` exists. Not read in detail.
- mctl MCP tools (service status/logs) were not called. The proposal needs no runtime fact beyond the gitops values above. The funnel numbers come from the issue, not from a query run here.

## Proposed solution

### 1. Phone-number screen copy (`internal/oauth/enable_access_page.go`)

**Retention check first.** Before writing the copy, trace the number end to end and record the result in the PR description, one line per place with the code reference:
- `enableSession` and `loginFlow` in `internal/oauth/enable_access.go`: in memory only, and dropped when?
- `internal/telegram/login.go`: is `PhoneNumber` passed anywhere beyond `auth.sendCode` / `auth.signIn`?
- `telegram_accounts` (`display_name`, `username`, `session_encrypted`) and `users`: is a phone column or a phone-bearing value written? Does the gotd session data stored in `session_encrypted` contain the number or the `tg.User` (which carries `Phone`)?
- `audit_logs`, the daily digest, `bot_updates`, metric labels.
- Log lines and error strings: does any `slog` call or wrapped error include the number, for example a Telegram RPC error that echoes it?

The copy states only what this check proves. "We do not keep your number" is allowed only if no place above keeps it; otherwise say what is kept and where. If the check contradicts `/privacy` (`internal/web/privacy.html`, l.121), fix the privacy page in the same PR or say why not. Also verify the other factual claims before using them: the session encryption scheme in `internal/crypto` (or wherever `session_encrypted` is sealed), and the name the session shows under Telegram's Active Sessions.

**Copy.** Add a static block to `enablePhoneTemplate`, shown in both wizard and non-wizard modes, between the intro paragraph and the form:
- **Why a phone number?** Telegram sign-in only told us who you are. Reading your chats needs a Telegram user session, which Telegram creates only after a login code is sent to your number.
- **What happens to it:** the number goes to Telegram to request the code; what this service keeps, per the check. The session is stored encrypted and shows up in Telegram under Active Sessions.
- **How to disconnect:** at any time, on the manage page (`/telegram/connect/manage`), by asking your assistant to run `disconnect_telegram_account`, or by ending the session in Telegram (Settings > Devices).
- Links: `/privacy`, `/security`.

Plain HTML (`<ul>` or `<details open>`), no JS, so the CSP is unchanged.

**Funnel measurement:** add a "Connect funnel" subsection to `docs/runbook.md` with portable SQL: the share of distinct `user_id` with `connect:oidc_callback` that later have `connect:phone_submitted`; the users whose last row is `connect:success` with no non-`connect:` row after it, split by connect flow if the audit rows or `oauth_refresh_tokens.client_name` allow it; and the one-day-active share. No code change, the rows already exist.

### 2. Retry guidance on channel errors

**a. `CHANNEL_INVALID` catalog action** (`internal/mcp/errorcatalog.go`): append "Retrying the same id will fail again. Call list_dialogs and use an id from that list; a channel that is not there cannot be read with this account."

**b. Kill-switch refusal text** (`broadcastContentError.Error()`), used only while `BROADCAST_CONTENT_ENABLED` is off, rewritten to be definitive:

> peer "X" is a broadcast channel, and reading channel posts is turned off on this server. Retrying will not change that: do not retry it with get_messages, get_unread_messages, search_messages or get_media, or with another id form. What works: list_dialogs (name, unread count), and reading private chats and groups, including get_unread_messages without peer.

Keep the `%q` peer, `Is()` and the `ReasonRefused` mapping. Do not mention a `broadcast` field in `list_dialogs`: none is added.

**c. Gate artifacts:** regenerate `docs/tool-descriptors*.json` only if a descriptor text changed, and add a `docs/product-updates/*.yaml` entry only if the gate requires one for these texts. The PR says which applied.

### 3. Success pages

**a. Wizard success page** (`internal/web/connect.go` `connectSuccessTemplate`): replace the Claude-only paragraph with an "Add the connector to your AI client" section. It keeps the MCP URL in `.url` and adds three short ordered lists: Claude, ChatGPT and other MCP clients (add a remote MCP server with this URL; the client handles OAuth). Each list links to the matching `/docs` anchor, which holds the current click path, so the Go template carries no long menu paths. It ends with "Then ask: 'list my recent Telegram chats'". Add the anchors in `internal/web/docs.html`.

**b. OAuth interstitial** (`internal/oauth/enable_access_page.go` `connectSuccessTemplate`): add one neutral line, "Back in {{.AppName}}, try a first request such as 'list my recent Telegram chats'. If the Telegram tools do not show up, see setup help" with a link to the `/docs` anchor. It does not tell the user to add a connector. The redirect timing is unchanged.

## Alternatives

1. **Add `broadcast: true` to `list_dialogs`** (the original task 4). Dropped by the amendment. With 0.98.0 channel content is readable, so a flag meaning "do not pass to read tools" would be wrong; and the original rule set it for any channel not positively a megagroup, which reports an unobserved type as a known one.
2. **Stateful "refuse once, then short-circuit" per session.** Adds in-memory state across a pool and replicas, and a terser error carries less guidance. Rejected; a definitive text fixes the cause.
3. **Ship the onboarding reminder in the same DevLoop** (the original tasks 10-14). Split out: it adds a table, a background loop and product decisions, and would delay the copy changes, whose effect can be measured on its own first.

## Platform impact

- **Migrations:** none.
- **Backward compatibility:** the `CHANNEL_INVALID` and kill-switch refusal texts change. The stable contract is `ReasonRefused` and `errors.Is`; tests that assert on the old substring are updated. No tool schema change.
- **Resources:** none.
- **Risks and mitigations:**
  - Phone-step copy promises something untrue: the retention check is a task with its result in the PR, and the copy is limited to what it proves.
  - Client click paths go stale: kept in `/docs` anchors, not in templates.
