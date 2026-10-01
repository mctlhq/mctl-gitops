# Integrate identity, consent, reachability and product communication into the client lifecycle

## Context

Issue mctlhq/mctl-telegram#679 is the `onboarding-integration` work item of the
`client-lifecycle` epic (mctlhq/.github#22). Its dependencies already shipped as
separate pieces. Identity capture and provenance are in `internal/db/identity_capture.go`
and `internal/db/identity_provenance.go`. Bot reachability is in `internal/db/reachability.go`
and `internal/notify/classify.go`. Category consent is in `internal/db/notification_prefs.go`.
Safe broadcast (#439) is in `internal/broadcast/`. Deterministic product-update evidence
(#440) is in `internal/productupdate/`. Each piece works by itself, but the client never sees
them as one onboarding path. Only the admin projection `db.IdentityRow` puts them together.
Two more gaps remain. Reachability is learned only from outbound deliveries (digest and
broadcast). The inbound login-bot receiver (`internal/bot/`, issue-619) is running, but no
handlers are registered in `cmd/server/main.go`, so a client who starts the bot is still
reported as `unknown`.

This proposal adds a generic client lifecycle. One pure derivation turns the existing facts
into an ordered onboarding checklist and a stage. Self-service surfaces (web manage page,
`/api/account`, MCP) show that checklist to the client, and admins see the stage in the
identity list. An inbound login-bot handler records reachability once the client has started
the bot. Consent stays separate from authentication. Broadcast authority stays behind the
#439 preview/approval/audit path. Per the issue's authoritative context, nothing here uses
an operator-identity or OpenClaw-only lookup account.

## User stories

- AS a client I WANT one place that shows what is left in my onboarding (connected, bot reachable, notification choices made) SO THAT I know which step to take next.
- AS a client I WANT to start the login bot and have the platform recognise that SO THAT I can receive the product updates and security notices I subscribed to.
- AS a client I WANT my notification choices to stay separate from signing in SO THAT connecting my account never means I agreed to marketing.
- AS an operator (`admin:users`) I WANT each identity's lifecycle stage in `list_telegram_identities` SO THAT I can see why a client is not receiving product communication without combining four fields by hand.
- AS a broadcast operator I WANT the audience preview to keep relying on the same consent and reachability facts SO THAT the lifecycle view and the broadcast eligibility can never disagree.

## Acceptance criteria (EARS)

- WHEN the lifecycle of a user is derived THE SYSTEM SHALL compute it with one pure function (`lifecycle.Derive`) from the facts already stored: identity capture, onboarding completion / active session, bot reachability and resolved notification preferences. The derivation SHALL perform no I/O.
- WHEN `lifecycle.Derive` runs THE SYSTEM SHALL return an ordered list of steps (`identity`, `connected`, `bot_reachable`, `notifications_decided`). Each step SHALL have a status (`done`, `pending`, `action_required`, `unknown`) and a stable `reason_code`. The result SHALL also include one `stage` value equal to the first step that is not done, or `complete`.
- WHILE a user has no `client_bot_reachability` row THE SYSTEM SHALL report the `bot_reachable` step as `unknown` (never as `done`), and SHALL NOT write a synthetic reachability row.
- WHILE the `product_updates` preference is not explicit (`ResolvedPref.Explicit == false`) THE SYSTEM SHALL report `notifications_decided` as `pending` and SHALL NOT treat the default (unsubscribed) as consent.
- IF a client authenticates or connects a Telegram session THEN THE SYSTEM SHALL NOT change any notification preference. Consent SHALL stay a separate, explicit act through the existing setters (`SetNotificationPrefs` via the manage page, `/api/account/notifications`, or `set_my_notification_preferences`).
- WHEN an authenticated client calls `GET /api/account/lifecycle` THE SYSTEM SHALL return that client's derived lifecycle as JSON, and SHALL return 401 when no identity is present.
- WHEN an authenticated client calls the new read-only MCP tool `get_my_onboarding_status` THE SYSTEM SHALL return the same structure as `GET /api/account/lifecycle`, with a declared output schema and read-only annotations, and without requiring any admin scope.
- WHEN a client opens `/telegram/connect/manage` THE SYSTEM SHALL render a "Getting started" checklist from the derived lifecycle. Each non-done step SHALL have a remedy link: connect, start the bot, or the notification section on the same page.
- WHERE `TELEGRAM_LOGIN_BOT_USERNAME` is configured THE SYSTEM SHALL render the bot-reachability remedy as a `https://t.me/<username>` link. IF it is not configured THEN THE SYSTEM SHALL render plain-text instructions and no link.
- WHEN an admin calls `list_telegram_identities` THE SYSTEM SHALL include an omitempty `lifecycle_stage` field on each `IdentityRow`, derived with the same `lifecycle.Derive`, and SHALL leave every existing field unchanged.
- WHEN the bot receiver accepts a `message` update from a known private chat THE SYSTEM SHALL record `client_bot_reachability.state = reachable` with `source = bot_inbound` for the user that owns that chat. The write SHALL happen inside the receiver's dispatch transaction.
- IF the inbound update comes from an unknown, group, channel or ambiguous chat THEN THE SYSTEM SHALL NOT record reachability. The existing `KnownChatFunc` drop path covers this.
- WHILE handling an inbound update THE SYSTEM SHALL NOT decode or persist message text, SHALL NOT send any message, and SHALL NOT change notification preferences.
- WHEN a broadcast audience is evaluated THE SYSTEM SHALL keep using `broadcast.Evaluate` unchanged, so lifecycle onboarding gives a model no new send path and no broadcast authority.
- WHEN the lifecycle surfaces render THE SYSTEM SHALL NOT log phone numbers, message bodies, or session data. Only the stage and reason codes MAY be logged.

## Out of scope

- Bot commands that read message text (`/subscribe`, `/settings`, `/stop`): these need `bot.Update` to be widened, which `internal/bot/update.go` requires to happen in a separate change that makes its own case.
- Callback-query handling (owned by #571) and any bot reply or welcome message.
- Any operator-identity or OpenClaw-only lookup account (#400 and mctl-gitops#1182 are retired).
- Changes to broadcast eligibility rules, approval flow, or product-update digest generation.
- New notification categories.
- Automatic outreach to clients whose reachability is `unknown`. Probing stays forbidden by `internal/notify`.

## Open questions

- Is an inbound private message acceptable evidence of reachability? `internal/notify/classify.go` currently says reachability is derived "only from the outcome of a real Telegram Bot API delivery". This proposal treats a message the client sent to the bot as real, non-probe evidence and updates that package comment. A reviewer may prefer to keep inbound evidence in a separate column instead. That is the alternative B2 in design.md.
- Should `notifications_decided` require an explicit choice only for `product_updates` (the marketing category), or for every category? The proposal requires only `product_updates`, because operational categories default to subscribed by design.
- The bot username could be configured (`TELEGRAM_LOGIN_BOT_USERNAME`) or discovered with `getMe` at startup. The proposal uses configuration to avoid a startup network dependency.
- The issue does not say what counts as "done" for the epic. This proposal assumes that the integrated self-service view, the admin stage and inbound reachability are enough to close `onboarding-integration`.
