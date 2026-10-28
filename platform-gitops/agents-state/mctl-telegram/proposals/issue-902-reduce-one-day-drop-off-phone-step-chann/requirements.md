# Reduce one-day drop-off: phone step, channel refusals, client setup after connect

## Context

Production funnel data (issue #902) shows that of 75 external sign-ups, 40 were
active on exactly one day and 22 of those never made a tool call. The users who
dropped out stopped at four points: right after Telegram sign-in, before they
entered a phone number (8 users); in code or 2FA entry (8, tracked in #900); on
`identity_mismatch` (2, related to #749); and after `connect:success` without
ever adding the connector to an AI client (4). Among the 18 one-day users who did
make tool calls, three got 40 consecutive `refused` errors on broadcast channels
and one got 16 `CHANNEL_INVALID` errors on `search_messages`. The model kept
retrying, because nothing told it to stop or what to use instead.

This proposal covers the three tasks that are not tracked elsewhere: (1) explain
the phone-number step on its screen, (3) make the broadcast-channel refusal
actionable and mark broadcast channels in `list_dialogs`, and (4) show setup
steps for each client on the success page, plus one bot reminder when no tool
call arrives within 24 hours. Task 2 belongs to #900 and #749.

## User stories

- AS a new user who just signed in with Telegram I WANT to understand why a phone number is needed, what happens to it and to the session, and how to disconnect later SO THAT I am willing to enter it.
- AS an AI model calling the MCP tools I WANT `list_dialogs` to tell me which dialogs are broadcast channels whose content cannot be read SO THAT I do not pick them.
- AS an AI model that hit a broadcast-channel refusal I WANT the error to say clearly that retrying will not help and what to use instead SO THAT I stop retrying and switch to a supported peer.
- AS a user who has just connected my Telegram account I WANT concrete setup steps for Claude, ChatGPT and other MCP clients SO THAT I can actually use the connector.
- AS a connected user who has not used the connector yet I WANT at most one reminder from the login bot, sent only when my notification preferences allow it, SO THAT I am nudged once and never spammed.
- AS the operator I WANT to measure each step of the funnel SO THAT I can check whether the one-day share drops after release.

## Acceptance criteria (EARS)

### Task 1: phone-number step

- WHEN the phone-number screen (`enablePhoneTemplate`) is rendered, in wizard mode or not, THE SYSTEM SHALL show a short explanation that: Telegram sign-in proves identity only, and a Telegram user session (login code sent to the number) is needed to read messages; the number is passed to Telegram to request the code and is not stored after login; the session is stored encrypted and appears in Telegram's Active Sessions; and the user can disconnect at any time from the manage page, with the `disconnect_telegram_account` tool, or by ending the session in Telegram.
- WHEN the phone-number screen is rendered THE SYSTEM SHALL link to `/privacy` and `/security`.
- WHILE the phone-number screen is shown THE SYSTEM SHALL keep its form fields, action URL and `send_optin` behaviour unchanged.
- WHEN the phone-number screen is rendered THE SYSTEM SHALL keep the strict CSP and add no external resource and no inline script.
- WHEN an operator runs the funnel query documented in `docs/runbook.md` THE SYSTEM SHALL support computing the share of users with a `connect:oidc_callback` row who later have a `connect:phone_submitted` row, using only `audit_logs` (`tool_name`, `user_id`, `created_at`).

### Task 3: broadcast-channel refusal

- WHEN `list_dialogs` returns a channel dialog that is not positively known to be a megagroup THE SYSTEM SHALL set `"broadcast": true` on that entry.
- WHEN `list_dialogs` returns a user, a legacy chat or a megagroup THE SYSTEM SHALL omit the `broadcast` field.
- WHEN `get_messages`, `get_unread_messages`, `search_messages` or `get_media` refuses a broadcast channel THE SYSTEM SHALL return an error text that (a) says the refusal is permanent for that peer and must not be retried with this or any other read tool or any other id form, (b) names what still works: `list_dialogs` metadata, and reading DMs and groups, including `get_unread_messages` without `peer`, and (c) says that `list_dialogs` marks such peers with `broadcast: true`.
- WHEN a broadcast-channel refusal is returned THE SYSTEM SHALL keep the audit reason `refused` (`ReasonRefused`) and the `errors.Is(err, telegram.ErrBroadcastContent)` contract.
- WHEN an MTProto call fails with `CHANNEL_INVALID` THE SYSTEM SHALL return an action text that says to stop retrying the same id, to pass the id exactly as `list_dialogs` returns it, and that entries marked `broadcast: true` cannot be read.
- WHEN the `list_dialogs` output schema or tool descriptions change THE SYSTEM SHALL ship the regenerated `docs/tool-descriptors*.json` and a `docs/product-updates/*.yaml` entry, so that the product-update release gate passes.

### Task 4: client setup after connect

- WHEN the self-hosted connect wizard's success page (`internal/web/connect.go` `connectSuccessTemplate`) is rendered THE SYSTEM SHALL show the MCP URL and short per-client setup steps for Claude (web/desktop connector settings), ChatGPT (connectors / developer mode) and "other MCP clients" (generic remote MCP URL + OAuth).
- WHEN the external-client OAuth interstitial (`internal/oauth/enable_access_page.go` `connectSuccessTemplate`) is rendered THE SYSTEM SHALL tell the user to send a first request in that client, for example "list my recent Telegram chats", without delaying the existing auto-redirect.
- WHEN a user has a `connect:success` audit row at least 24 hours old, no audit row with a tool name outside the `connect:` prefix after that success, an active (non-revoked) session, no prior onboarding reminder, and a resolved `onboarding` preference of `subscribed` THE SYSTEM SHALL send exactly one reminder through the login bot containing the MCP URL and a link to the setup instructions.
- IF the user's bot reachability is `unreachable`/blocked THEN THE SYSTEM SHALL NOT attempt the send and SHALL record the reminder as skipped.
- IF the user's `connect:success` is older than the reminder look-back window (default 7 days) THEN THE SYSTEM SHALL NOT send a reminder, so that the first deploy does not reach dormant users.
- IF the user is an admin, a lookup admin, a broadcast operator or the demo reviewer THEN THE SYSTEM SHALL NOT send a reminder.
- WHEN a reminder send is attempted THE SYSTEM SHALL record the outcome through `RecordBotReachability` and persist the reminder row before or atomically with the send, so that a restart or a second tick never sends twice.
- WHILE `TELEGRAM_LOGIN_BOT_TOKEN` is unset or `ONBOARDING_REMINDER_ENABLED` is not `true` THE SYSTEM SHALL NOT start the reminder loop.
- WHEN the manage page notification section is rendered THE SYSTEM SHALL list the new `onboarding` category so the user can unsubscribe.
- WHEN a reminder is sent THE SYSTEM SHALL write no phone number, message body or bot token to logs, and SHALL log only the internal user id and the outcome.

## Out of scope

- Code and 2FA error handling (digit cleanup, retries on `PHONE_CODE_INVALID` / `PASSWORD_HASH_INVALID`, `AUTH_RESTART`, code-screen copy): issue #900.
- `failed:identity_mismatch`: issue #749.
- Reading broadcast channel posts (blocked by the sponsored-messages requirement, issue #851).
- Local Bridge daemon `list_dialogs` output (`cmd/local`): the bridge returns its own payload. The `broadcast` flag is added only to the hosted path in this proposal.
- A per-session "only refuse loudly once" counter for broadcast refusals. The refusal text is made definitive instead (see design Alternatives).
- Re-measuring the funnel two weeks after release. That is an operator activity; this proposal only documents the query.
- Any change to `BOT_RECEIVER_ENABLED` or to inbound bot handling.

## Open questions

- Notification category for the reminder. The proposal adds a new `onboarding` category, classified `operational` and subscribed by default, which the user can turn off on the manage page. If the operator considers a usage nudge to be marketing, it should instead default to `unsubscribed` (like `product_updates`). That would make the reminder reach almost nobody, because product updates stay off until the user saves a choice.
- Bot reachability for users who never pressed /start. Production has `BOT_RECEIVER_ENABLED` absent, so inbound /start is not recorded, and the code does not show whether the Telegram OIDC sign-in grants the bot write access. Some reminders may fail with "cannot initiate". Those failures are recorded as unreachable and never retried. The reminder's real reach can only be measured after release.
- Which flow the 4 "success, no tool call" users took. The external-client flow (claude.ai/chatgpt.com) has by construction already added the connector. The flow that lacks client setup is the self-hosted wizard at `/telegram/connect`. The proposal changes both pages, with the main content on the wizard page.
- Exact current ChatGPT and Claude menu paths for adding a custom connector change over time. The copy should link to `/docs` sections that are kept current instead of hard-coding long click paths in Go templates.
