# Client onboarding glue: `/start` reachability, manage-page reachability, explicit first-connect category choice

## Context

Issue mctlhq/mctl-telegram#679 is the `onboarding-integration` work item of the
`client-lifecycle` epic (mctlhq/.github#22). The owner fixed its scope on 2026-10-01
(issue comment "Owner decision, 2026-10-01: scoped onboarding follow-up (authoritative)").
This proposal implements exactly that scope and nothing else.

A read-only gap analysis of `main` at `f52bc11` found every base capability present and
tested:

- **Reachability.** `client_bot_reachability`, `internal/db/reachability.go`, and
  `internal/notify/classify.go`.
- **Category consent, separate from authentication.** `client_notification_prefs` and
  `internal/db/notification_prefs.go`. `product_updates` defaults to unsubscribed.
- **Safe broadcast (#439).** `internal/broadcast/`.
- **Product-update feed and digest (#440, #683).** `internal/productupdate/`.

What is missing is the glue that turns them into an onboarding path:

1. **Reachability is learned only from outbound deliveries.** It comes from the digest and the
   broadcast worker. The inbound login-bot receiver (`internal/bot/`, issue-619) runs with an
   empty handler registry, so a client who presses Start on the login bot stays `unknown`.
2. **The manage page does not tell the client** whether the bot can reach them, or how to
   start it.
3. **Nothing in the first-connect flow asks the client to make a category choice.** The
   success page links to "Manage your session" without saying a choice is needed, so
   `product_updates` silently stays at its default.

## User stories

- AS a client I WANT pressing Start on the login bot to be recognised SO THAT the notices I subscribe to can reach me.
- AS a client I WANT the manage page to show whether the bot can reach me, with a link to start it, SO THAT I know what to do next.
- AS a client I WANT to be asked explicitly which categories I want when I first connect SO THAT connecting my account never counts as agreeing to product updates.
- AS a broadcast operator I WANT the audience evaluation to keep relying on the same consent and reachability rows SO THAT onboarding gives no new send path.

## Acceptance criteria (EARS)

### `/start` records reachability, never consent

- WHEN the login-bot receiver accepts a `message` update whose first entity is a `bot_command` at offset 0 naming `/start` (bare, `@<bot>`-suffixed, or with a payload) THE SYSTEM SHALL classify the update as kind `start_command`, and SHALL keep only that classification: neither the message text nor the payload is held in any field, logged, or stored.
- WHEN a `start_command` update arrives from a known private chat THE SYSTEM SHALL record `client_bot_reachability.state = reachable`, `reason_code = bot_start`, `source = bot_start` for the user who owns that chat, inside the receiver's dispatch transaction.
- IF the chat is unknown, not private (id ≤ 0) or maps to more than one user THEN THE SYSTEM SHALL record nothing. The existing `KnownChatFunc` drop path, outcome `unknown_chat`, covers this.
- WHEN a `start_command` update is handled THE SYSTEM SHALL NOT change any notification preference and SHALL NOT send any message.
- WHEN any other `message` update arrives THE SYSTEM SHALL NOT dispatch it to any handler, write any row other than its own `bot_updates` bookkeeping, send any message, or invoke any model or action path. Kind `message` stays unregistered, so the update ends with the existing `no_handler` outcome.
- WHEN the same update is delivered twice THE SYSTEM SHALL handle it at most once (`DispatchOnce`), and a handler error SHALL roll back the reachability write together with the done mark.

### Manage page shows reachability and a `t.me` entry point

- WHEN a signed-in client opens `/telegram/connect/manage` THE SYSTEM SHALL render a bot-reachability block above the notification form, showing one of `unknown` (no row), `reachable`, or `blocked`. `cannot_initiate` is shown as "not started".
- WHERE `TELEGRAM_LOGIN_BOT_USERNAME` is configured and valid THE SYSTEM SHALL render a `https://t.me/<username>?start=onboarding` link in that block. WHERE it is unset or invalid THE SYSTEM SHALL render plain-text instructions and no link.
- WHILE the reachability state is not `reachable` THE SYSTEM SHALL show a note that the login bot cannot deliver the categories the client has enabled until the client starts the bot.
- WHEN the manage page renders THE SYSTEM SHALL NOT write any notification preference or reachability row. A reachability read failure SHALL hide the block without breaking the page or the disconnect controls.

### Explicit category choice on first connect

- WHEN `/telegram/connect/done` succeeds THE SYSTEM SHALL present an explicit "choose your notifications" step that links to `/telegram/connect/manage?onboarding=1#notifications`.
- WHILE the `product_updates` preference has never been saved (`ResolvedPref.Explicit == false`) THE SYSTEM SHALL show a prompt on the manage page asking the client to choose, and the `product_updates` checkbox SHALL be unchecked.
- IF a client authenticates or connects a Telegram session THEN THE SYSTEM SHALL NOT change any notification preference. Only an explicit save of the category form (or the existing REST/MCP setters) writes consent.
- WHEN a client saves `product_updates = subscribed` THE SYSTEM SHALL include that client in a `product_updates` broadcast audience, subject to the unchanged `broadcast.Evaluate` rules. Until then the client SHALL be skipped as `unsubscribed`.

### Safety and privacy

- THE SYSTEM SHALL leave `broadcast.Evaluate`, the broadcast worker, approval and audit unchanged.
- THE SYSTEM SHALL NOT log chat ids, phone numbers, message text or command payloads in the new code paths.

## Out of scope

- The `internal/lifecycle` package, `GET /api/account/lifecycle`, the MCP tool `get_my_onboarding_status`, and `IdentityRow.LifecycleStage`.
- Bot commands other than `/start` (`/subscribe`, `/settings`, `/stop`), consent changes through the bot, and any bot reply or welcome message.
- Callback-query handling (#571).
- Any operator-identity or OpenClaw-only lookup (#400 and mctl-gitops#1182 are retired).
- Changes to broadcast eligibility, approval, or digest generation; new notification categories.
- Probing reachability. `internal/notify` still forbids a message sent only to classify reachability.

## Rollout and closure

1. Merge and release the code. The receiver stays off: `BOT_RECEIVER_ENABLED` is not set in production today.
2. After that release is live, a **separate** mctl-gitops PR sets `BOT_RECEIVER_ENABLED` (and `TELEGRAM_LOGIN_BOT_USERNAME`) for `labs/mctl-telegram`.
3. Live proof: onboarding → `/start` → reachability `reachable` → explicit category preferences saved → a broadcast preview respects them. #679 closes only after this proof.

## Resolved questions

- **Is a `/start` the client sent acceptable evidence of reachability?** Yes, by the owner's decision. Telegram delivers it only from a user who has started (and not blocked) the bot. It is not a probe, because the client initiated it. Only `/start` counts; other inbound messages are not evidence in this change.
- **What does "decided" mean for consent?** An explicit save of `product_updates` in either direction. Operational categories keep their defaults.
- **Is the bot username configured or discovered?** Configured (`TELEGRAM_LOGIN_BOT_USERNAME`), to avoid a startup network dependency.
