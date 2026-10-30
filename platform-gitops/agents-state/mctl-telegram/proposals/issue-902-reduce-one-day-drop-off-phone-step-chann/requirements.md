# Reduce one-day drop-off: phone step, channel refusals, client setup after connect

## Context

Production funnel data (issue #902) shows that of 75 external sign-ups, 40 were
active on exactly one day and 22 of those never made a tool call. The users who
dropped out stopped at four points: right after Telegram sign-in, before they
entered a phone number (8 users); in code or 2FA entry (8, tracked in #900); on
`identity_mismatch` (2, related to #749); and after `connect:success` without
ever making a tool call (4). Among the 18 one-day users who did make tool
calls, three got 40 consecutive `refused` errors on broadcast channels and one
got 16 `CHANNEL_INVALID` errors on `search_messages`. The model kept retrying,
because nothing told it to stop or what to use instead.

### Changed after this proposal was first written (amendment, 2026-10-28)

- **0.98.0 (#905) reads broadcast channels again.** Channel posts are returned
  by `get_messages`, `get_unread_messages`, `search_messages` and `get_media`,
  with Telegram sponsored messages attached. The `refused` path now runs only
  while the `BROADCAST_CONTENT_ENABLED` kill switch is off. The 40 refusals in
  the funnel data predate this release.
- **0.98.1 (#908) closed #900** (forgiving code and 2FA entry).
- **The reminder is split out.** The original tasks 10-14 (onboarding
  notification category, `onboarding_reminders` table, reminder loop, config,
  enabling PR) move to #912. They add storage, a
  background loop and two product decisions (the category's default and when to
  enable it), and they should not hold back the copy and error-text changes
  below.

This proposal now covers: (1) explaining the phone-number step on its screen
and documenting the funnel query, (3) making `CHANNEL_INVALID` and the
kill-switch refusal tell the model to stop retrying, and (4) per-client setup
steps on the wizard success page plus a neutral first-request hint on the OAuth
interstitial. Task 2 belongs to #900 (done) and #749.

## User stories

- AS a new user who just signed in with Telegram I WANT to understand why a phone number is needed, what happens to it and to the session, and how to disconnect later SO THAT I am willing to enter it.
- AS an AI model that got `CHANNEL_INVALID` I WANT the error to say that retrying the same id will not help and what to do instead SO THAT I stop retrying.
- AS an AI model that hit a broadcast-channel refusal while the kill switch is off I WANT the error to say the refusal will not change on retry SO THAT I switch to a supported peer.
- AS a user who has just connected my Telegram account through the self-hosted wizard I WANT concrete setup steps for Claude, ChatGPT and other MCP clients SO THAT I can actually use the connector.
- AS a user returning to my AI client after OAuth I WANT a suggested first request and a pointer to setup help SO THAT I know what to try next.
- AS the operator I WANT to measure each step of the funnel SO THAT I can check whether the one-day share drops after release.

## Acceptance criteria (EARS)

### Task 1: phone-number step

- WHEN the phone-number screen (`enablePhoneTemplate`) is rendered, in wizard mode or not, THE SYSTEM SHALL show a short explanation that: Telegram sign-in proves identity only, and a Telegram user session (login code sent to the number) is needed to read messages; what this service does and does not retain about the number, worded exactly as far as the retention check in tasks.md task 1 proves and no further; that the session is stored encrypted and appears in Telegram's Active Sessions; and that the user can disconnect at any time from the manage page, with the `disconnect_telegram_account` tool, or by ending the session in Telegram.
- WHEN the phone-number screen is rendered THE SYSTEM SHALL link to `/privacy` and `/security`.
- IF the retention check finds the number, or data derived from it, kept anywhere (database column, encrypted session blob, audit row, log line, metric label, error text) THEN the copy SHALL say what is kept instead of claiming it is not kept, and the PR SHALL say whether `/privacy` needs the same correction.
- WHILE the phone-number screen is shown THE SYSTEM SHALL keep its form fields, action URL and `send_optin` behaviour unchanged.
- WHEN the phone-number screen is rendered THE SYSTEM SHALL keep the strict CSP and add no external resource and no inline script.
- WHEN an operator runs the funnel query documented in `docs/runbook.md` THE SYSTEM SHALL support computing the share of users with a `connect:oidc_callback` row who later have a `connect:phone_submitted` row, using only `audit_logs` (`tool_name`, `user_id`, `created_at`).

### Task 3: retry guidance on channel errors

- WHEN an MTProto call fails with `CHANNEL_INVALID` THE SYSTEM SHALL return an action text that says to stop retrying the same id and to pass the id exactly as `list_dialogs` returns it.
- WHILE `BROADCAST_CONTENT_ENABLED` is off, WHEN `get_messages`, `get_unread_messages`, `search_messages` or `get_media` refuses a broadcast channel THE SYSTEM SHALL return an error text that (a) says the refusal will not change on retry, with this or any other read tool or id form, and (b) names what still works: `list_dialogs` metadata, and reading private chats and groups, including `get_unread_messages` without `peer`.
- WHEN a broadcast-channel refusal is returned THE SYSTEM SHALL keep the audit reason `refused` (`ReasonRefused`) and the `errors.Is(err, telegram.ErrBroadcastContent)` contract.
- THE SYSTEM SHALL NOT add a field to `list_dialogs` that claims a dialog's content cannot be read. With the switch on, channel content is readable; and a channel whose type could not be observed is not known to be a broadcast channel.
- IF a changed text is part of a tool descriptor or the product-update gate requires it THEN THE SYSTEM SHALL ship the regenerated `docs/tool-descriptors*.json` and a `docs/product-updates/*.yaml` entry.

### Task 4: client setup after connect

- WHEN the self-hosted connect wizard's success page (`internal/web/connect.go` `connectSuccessTemplate`) is rendered THE SYSTEM SHALL show the MCP URL and short per-client setup steps for Claude, ChatGPT and "other MCP clients" (generic remote MCP URL + OAuth), each linking to a `/docs` anchor that holds the current click path.
- WHEN the external-client OAuth interstitial (`internal/oauth/enable_access_page.go` `connectSuccessTemplate`) is rendered THE SYSTEM SHALL suggest a first request in that client, for example "list my recent Telegram chats", and link to the setup help in `/docs`, without telling the user to add a connector (in this flow the client has already added it) and without delaying the existing auto-redirect.

## Out of scope

- Code and 2FA error handling: issue #900, shipped in 0.98.1.
- `failed:identity_mismatch`: issue #749.
- The onboarding reminder (bot message after 24 hours without a tool call): split out to #912. It needs two product decisions first: whether a new `onboarding` category is subscribed by default, and the enablement criteria. It also needs a measurement of which flow the "success, no tool call" users took, because the reminder text depends on it.
- A `broadcast` or channel-kind field in `list_dialogs`. Not needed while channels are readable. If it is ever added, it must report only an observed type (broadcast or megagroup) and an explicit unknown, never default unknown to broadcast.
- Local Bridge daemon output (`cmd/local`).
- A per-session "only refuse loudly once" counter for broadcast refusals.
- Re-measuring the funnel two weeks after release. That is an operator activity; this proposal only documents the query.

## Open questions

- Which flow the 4 "success, no tool call" users took. The external-client flow (claude.ai/chatgpt.com) has by construction already added the connector, so its users may have had a client-side problem rather than a missing setup step. The runbook query in task 3 should let the operator split them by flow, if the audit rows allow it; if they do not, the PR says so.
- Exact current ChatGPT and Claude menu paths for adding a custom connector change over time. The copy links to `/docs` sections that are kept current instead of hard-coding long click paths in Go templates.
