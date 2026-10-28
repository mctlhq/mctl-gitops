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

### Broadcast-channel refusal
- `internal/telegram/broadcast_content.go`: `ErrBroadcastContent`, `broadcastContentError.Error()` ("peer %q is a broadcast channel: MCTL Assistant does not read channel posts, so get_messages, ... refuse it. The channel stays listed in list_dialogs ..."), and `refuseBroadcastPeer`, which passes a channel only when `channels.getChannels` reports `Megagroup`.
- `internal/mcp/tools.go` `borrowErrResult` (l.2282) maps it to `ReasonRefused` and `toolErr("%s: %v", tool, err)`. `internal/mcp/media_tools.go:123` does the same for media.
- `internal/telegram/dialogs.go` `Dialog{ID, Type, Title, Username, UnreadCount, LastMessageDate}`. `dialogFromPeer` emits `Type: "channel"` for every `PeerChannel`, megagroup or broadcast alike, so the model cannot tell them apart before it calls a read tool.
- `internal/mcp/errorcatalog.go` `CHANNEL_INVALID` action: "Call list_dialogs and pass the id exactly as returned there ..." It does not say to stop retrying.
- Tool surface changes are gated: `internal/mcp/descriptors.go` generates `docs/tool-descriptors*.json`, and `internal/productupdate/gate.go` with `cmd/productupdates` requires a `docs/product-updates/*.yaml` entry for schema changes (example: `search-messages-date-range.yaml`).

### Success pages
- External OAuth clients (claude.ai, chatgpt.com, ...): `internal/oauth/server.go` `issueAuthCode` renders `connectSuccessPage` (`enable_access_page.go` l.250) with "Telegram connected. Returning you to {{.AppName}}..." and a 1.2 s auto-redirect. The connector is already added in that client.
- Self-hosted wizard (`/telegram/connect`, `AUTH_MODE=local-jwt`): `internal/web/connect.go` `connectSuccessTemplate` (l.452) shows the MCP URL and Claude-only instructions ("open the Claude.ai connector settings and add the MCP URL"), notification choice and the login-bot start link. ChatGPT and other clients are not covered.

### Bot notifications and preferences
- `internal/db/notification_prefs.go`: closed category set `product_updates` (marketing, default unsubscribed), `maintenance` and `security` (operational, default subscribed). `ResolveNotificationPrefs` / `ResolvePrefState` apply defaults. Labels are in `internal/web/manage_notifications.go` (l.207).
- Bot reachability: the `client_bot_reachability` table (`internal/db/db.go` l.880 SQLite, l.1207 Postgres), `Store.RecordBotReachability` and `GetBotReachability` in `internal/db/reachability.go`, and the classification in `internal/notify/classify.go`.
- Senders: `internal/botapi.Client.SendMessage` (used by `internal/broadcast/worker.go`) and `internal/digest` (its own `sendTelegramMessage`). Background loops are started in `cmd/server/main.go` (`sweeper.*`, `digest.StartDailyDigest` l.1068, broadcast worker l.1082). The deployment is single-replica, and `digest` documents "Single-replica only — there is no leader election".
- Schema changes are additive `CREATE TABLE IF NOT EXISTS` statements in `internal/db/db.go`, one list for each dialect.

### Deployed state checked
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: tenant `labs`, image tag `0.96.0`, `AUTH_MODE: local-jwt` (so the `/telegram/connect` wizard and its success page are mounted), `OAUTH_ISSUER_URL: https://tg.mctl.ai`, `OAUTH_ALLOWED_IMPLICIT_HOSTS` includes claude.ai, claude.com, chatgpt.com, antigravity.google, cursor.com and town.com, `TELEGRAM_LOGIN_BOT_USERNAME: "MCTL_AI_bot"`, `TELEGRAM_LOGIN_BOT_TOKEN` from a secret, `BOT_RECEIVER_ENABLED` deliberately absent (comment l.181), and a single replica (l.243, l.679).
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml` exists. Not read in detail.
- mctl MCP tools (service status/logs) were not called. The proposal needs no runtime fact beyond the gitops values above. The funnel numbers come from the issue, not from a query run here.

## Proposed solution

### 1. Phone-number screen copy (`internal/oauth/enable_access_page.go`)
Add a static block to `enablePhoneTemplate`, shown in both wizard and non-wizard modes, between the intro paragraph and the form:

- **Why a phone number?** "Signing in with Telegram only told us who you are. Reading your chats needs a Telegram user session, which Telegram creates only after a login code is sent to your number."
- **What happens to it:** "Your number goes to Telegram to request the code. We do not keep it after login. The session is stored encrypted (AES-256-GCM) and shows up in Telegram as 'MCTL Assistant' under Active Sessions."
- **How to disconnect:** "At any time: on the manage page (`/telegram/connect/manage`), by asking your assistant to run `disconnect_telegram_account`, or by ending the session in Telegram (Settings > Devices)."
- Links: `/privacy`, `/security`.

Implement it as a `<details open>` or plain `<ul>` with no JS, so the CSP is unchanged. Before writing "we do not keep it", verify that `enableSession.phone` is held only in the in-memory enable session (`s.enables`) and is never written to `telegram_accounts` (the privacy page says the same). If the verification fails, the copy must say what is retained instead.

Funnel measurement: add a "Connect funnel" subsection to `docs/runbook.md` with the portable SQL: the share of distinct `user_id` with `connect:oidc_callback` that later have `connect:phone_submitted`, and the share of users whose last row is `connect:success` with no non-`connect:` row after it. No code is needed, because the rows already exist.

### 2. Broadcast refusal and dialog marking

**a. `telegram.Dialog`** gains `Broadcast bool \`json:"broadcast,omitempty"\``. In `dialogFromPeer`'s `*tg.PeerChannel` case, set `Broadcast = !(ch != nil && ch.Megagroup)`. This mirrors `refuseBroadcastPeer`, which refuses anything not positively a megagroup, so the flag and the refusal can never disagree. Users, chats and megagroups omit the field, so existing consumers see no change.

**b. Refusal text** (`broadcastContentError.Error()`), rewritten to be definitive:

> peer "X" is a broadcast channel. MCTL Assistant never reads channel posts, so this refusal is permanent: do not retry it with get_messages, get_unread_messages, search_messages or get_media, or with another id form. list_dialogs marks these peers with "broadcast": true. What works: list_dialogs (name, unread_count), and reading private chats and groups, including get_unread_messages without peer.

Keep the `%q` peer, `Is()` and the `ReasonRefused` mapping. Update the tool descriptions in `internal/mcp/tools.go` (l.260, l.518, l.3038) and `media_tools.go` l.65 to mention the `broadcast` flag, and add one sentence to the `list_dialogs` description: "Entries with broadcast: true are channels whose posts cannot be read; do not pass them to read tools."

**c. `CHANNEL_INVALID` catalog action** (`internal/mcp/errorcatalog.go`): append "Do not retry the same id. If list_dialogs marks the peer broadcast: true, its content cannot be read at all."

**d. Gate artifacts:** regenerate `docs/tool-descriptors*.json` with the repo's existing generator (`cmd/tooldiff` / the descriptors test's update mode) and add `docs/product-updates/list-dialogs-broadcast-flag.yaml` (`kind: changed_behavior`, `tools: [list_dialogs, get_messages, get_unread_messages, search_messages, get_media]`, `changes: [{tool: list_dialogs, change: schema}, ...text]`, `delivery: next_digest`, `status` set by the reviewer).

### 3. Success pages and the 24 h reminder

**a. Wizard success page** (`internal/web/connect.go` `connectSuccessTemplate`): replace the Claude-only paragraph with a "Add the connector to your AI client" section. It keeps the MCP URL in `.url` and adds three short ordered lists: Claude (Settings > Connectors > Add custom connector, paste URL, sign in), ChatGPT (Settings > Connectors / developer mode > add MCP server URL), and Other MCP clients (add a remote MCP server with this URL; the client handles OAuth). It ends with "Then ask: 'list my recent Telegram chats'", and each list links to the matching `/docs` anchor so the click paths can be maintained in one place. `connectSuccessData` stays as is (`ClaudeURL`, `MCPURL`, `LoginBotStartURL`), plus an optional `ChatGPTURL` constant.

**b. OAuth interstitial** (`internal/oauth/enable_access_page.go` `connectSuccessTemplate`): add one line, "Back in {{.AppName}}, try: 'list my recent Telegram chats'." The redirect timing is unchanged.

**c. Onboarding reminder**
- **Category:** add `CategoryOnboarding NotificationCategory = "onboarding"` to the closed set in `internal/db/notification_prefs.go`, operational and subscribed by default. Update `defaultPref`, the classification in `store.go` l.694, and the labels in `internal/web/manage_notifications.go`. This category does not use `product_updates`, which defaults to off and is marketing.
- **Storage:** a new table, `onboarding_reminders(user_id PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, connect_success_at, status TEXT /* claimed|sent|skipped|failed */, reason TEXT, updated_at)`, added to both dialect lists in `internal/db/db.go`. The primary key makes "at most one reminder per user" a database invariant.
- **Store methods** in a new file, `internal/db/onboarding_reminder.go`:
  - `ListOnboardingReminderCandidates(ctx, now, minAge, maxAge, limit)` selects users whose latest `connect:success` row falls in `[now-maxAge, now-minAge]`, with no later `audit_logs` row whose `tool_name NOT LIKE 'connect:%'`, an active `telegram_accounts` row, and no `onboarding_reminders` row. It returns `user_id`, `telegram_login_id`, the explicit prefs and reachability, with a fixed number of queries and the same portable style as `LastConnectStepFor`.
  - `ClaimOnboardingReminder(ctx, userID, successAt)` does `INSERT ... ON CONFLICT DO NOTHING` and returns whether it claimed.
  - `FinishOnboardingReminder(ctx, userID, status, reason)`.
- **Loop:** a new package, `internal/onboarding` (`reminder.go`), with `Reminder{Store, Sender botapi-like, Exclude set, MCPURL, DocsURL, now}` and `Tick(ctx)`. For each candidate it:
  1. skips excluded ids (admins, lookup admins, broadcast operators, demo reviewer from config);
  2. resolves the preference with `db.ResolvePrefState(CategoryOnboarding, prefs)` and skips if unsubscribed;
  3. skips if reachability is unreachable;
  4. claims; if the claim fails, it skips;
  5. sends a short plain-text message;
  6. calls `RecordBotReachability(..., source "onboarding_reminder")` with the `notify` classification;
  7. finishes with `sent` or `failed` (no retry).

  Claiming before sending means a crash can lose a reminder but never duplicate one. `Run(ctx, interval)` ticks every 15 minutes.
- **Wiring** (`cmd/server/main.go`): start the loop only when `cfg.OnboardingReminderEnabled && cfg.TelegramLoginBotToken != ""`. The new config lives in `internal/config`: `ONBOARDING_REMINDER_ENABLED` (default false), `ONBOARDING_REMINDER_AFTER` (default 24h), `ONBOARDING_REMINDER_MAX_AGE` (default 7d). A gitops PR turns it on after the code ships.
- **Message text** (no personal data): "Your Telegram account is connected to MCTL Assistant, but no AI client has used it yet. Add <MCP URL> as a connector in Claude, ChatGPT or another MCP client: <docs URL>. You can turn these reminders off at <manage URL>."
- **Logging:** only `user_id` and the outcome. If the reminder introduces new sensitive fields, add them to `internal/audit/redact.go`.

## Alternatives

1. **Hide broadcast channels from `list_dialogs` entirely.** This prevents the model from picking them, but users ask about their channels' unread counts, and the #851 decision deliberately keeps name and unread count visible. The flag gives the same steering without removing data. Rejected.
2. **Stateful "refuse once, then short-circuit" per session.** The server would remember refused peers per identity and return a terser error, or a rate-limit error, on repeats. It adds in-memory state across a pool and replicas, and a terser error carries less guidance. The model retries because the text does not say "permanent". A definitive text plus the dialog flag fixes the cause. Rejected for now. It can be revisited if the re-measured funnel still shows retry storms.
3. **Reuse `owner_notifications` (Saved Messages via the user's own MTProto session) for the reminder.** This reaches every connected user regardless of bot reachability, but it writes into the user's own account through their session, an action they never authorised for notifications. The issue also explicitly asks for the bot. Rejected.
4. **Reminder via the existing broadcast campaign system.** Campaigns are operator-approved, hash-pinned bulk sends with an audience selector, so a per-user, time-triggered message does not fit the approve-then-send model and would need an operator approval every day. Rejected in favour of a small dedicated loop that reuses `botapi`, prefs and reachability.

## Platform impact

- **Migrations:** two additive `CREATE TABLE IF NOT EXISTS` statements (SQLite and Postgres) for `onboarding_reminders`. No change to existing tables. The `onboarding` preference category needs no migration because rows are written only on explicit decisions.
- **Backward compatibility:** `broadcast` is `omitempty` and additive in the `list_dialogs` output schema. The refusal and `CHANNEL_INVALID` texts change. Clients matching on the old exact string would break, but the only stable contract is `ReasonRefused` and `errors.Is`, and tests that assert on the substring must be updated. The tool-surface change requires a product-update feed entry, so the release gate passes.
- **Resources:** one extra query batch every 15 minutes, bounded by `limit` and by the 7-day window, and at most one Bot API call per newly connected user. Negligible.
- **Replicas:** the loop is safe on several replicas because of the claim primary key. The deployment is single-replica anyway.
- **Risks and mitigations:**
  - Reminder perceived as spam: one per user ever, its own category that can be unsubscribed, a 7-day look-back (no backfill of dormant users), default-off flag until the gitops PR.
  - Bot cannot initiate a chat: recorded as unreachable and never retried.
  - Phone-step copy promises something untrue: verify retention in code before merging (task DoD).
  - Excluded operator ids wrongly reminded: explicit exclusion set, plus a test.
