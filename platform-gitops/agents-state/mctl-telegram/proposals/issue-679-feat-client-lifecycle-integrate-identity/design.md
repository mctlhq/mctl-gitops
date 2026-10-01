# Design: issue-679-feat-client-lifecycle-integrate-identity

## Current state

The lifecycle facts exist, but each one has its own owner and surface.

- **Identity.** `internal/db/identity_capture.go` (`EnsureUserByTelegramCapture`) records the
  first name, last name, username and language code, plus `identity_source` and
  `identity_captured_at`. `internal/db/identity_provenance.go` resolves the provenance of each
  attribute.
- **Onboarding completion.** `users.onboarding_completed_at` is set once by
  `stampOnboardingCompleted` in `internal/db/store.go` (called from `SaveSession`, with a
  backfill in `internal/db/db.go`). `users.last_seen_at` tracks activity.
- **Reachability.** `internal/notify/classify.go` defines four states (`unknown`, `reachable`,
  `blocked`, `cannot_initiate`) and `ClassifyDelivery`. `Store.RecordBotReachability` in
  `internal/db/reachability.go` upserts `client_bot_reachability` from conclusive outcomes
  only. The only callers are outbound: `internal/digest/digest.go` (`digest_delivery`) and
  `internal/broadcast/worker.go` (`broadcast_delivery`). `getBotReachability` returns nil when
  no row exists, which means "unknown".
- **Consent.** `internal/db/notification_prefs.go` stores one row per category in
  `client_notification_prefs`. The categories are `product_updates` (marketing, default
  unsubscribed) and `maintenance` / `security` (operational, default subscribed).
  `ResolvedPref.Explicit` separates "never decided" from "decided". Setters are exposed in the
  web manage page (`internal/web/manage_notifications.go`), the REST API
  (`internal/web/account.go`, `GET|PUT /api/account/notifications`) and MCP
  (`get_my_notification_preferences` / `set_my_notification_preferences` in
  `internal/mcp/tools.go`). Authentication never writes a preference.
- **Safe broadcast (#439).** `internal/broadcast/policy.go` `Evaluate` checks audience, tier,
  `ResolvePrefState` for the category, and reachability (`blocked` and `cannot_initiate` are
  skipped). The preview, approval, audit and worker live in `internal/broadcast/` and
  `internal/web/broadcasts.go`.
- **Product-update evidence (#440).** `internal/productupdate/` (feed, gate, digest, render)
  is published at `/docs/product-updates` (`cmd/server/main.go`).
- **Admin projection.** `db.IdentityRow` in `internal/db/store.go` already contains
  `OnboardedAt`, `LastSeenAt`, `BotReachability` and `NotificationPrefs`, and is filled by
  `ListIdentities` for `list_telegram_identities`. This is the only place where all the facts
  appear together, and it is admin-only. No code derives a stage or a next step from them.
- **Inbound bot.** `internal/bot/` (issue-619) long-polls `getUpdates`, stores each update
  durably, drops unknown chats through `KnownChatFunc` (`internal/bot/wiring.go`), and
  dispatches to a `Registry`. In `cmd/server/main.go` (around line 990) the registry is built
  with no handlers, so every message ends as `no_handler`. A client who presses Start on the
  login bot stays `unknown` until an outbound digest or broadcast happens to reach them.
  `Delivery` carries no text by design.
- **Client self-view.** `HandleManage` (`internal/web/manage.go`) shows session state and
  notification rows. `get_my_identity` returns only id, username and display name. Nothing
  tells the client whether the bot can reach them or what is left to do.

## Proposed solution

### 1. `internal/lifecycle` (new, pure)

```go
type Facts struct {
    IdentityCapturedAt *time.Time
    OnboardedAt        *time.Time
    HasSession         bool
    Reachability       *db.BotReachability // nil = never observed
    Prefs              []db.ResolvedPref
}
type Step struct { Name, Status, ReasonCode string; ObservedAt *time.Time }
type Status struct { Stage string; Steps []Step }
func Derive(f Facts) Status
```

The steps run in a fixed order:

1. `identity`. Done when `IdentityCapturedAt != nil`. Otherwise the step is `pending` with
   reason `identity_not_captured`.
2. `connected`. Done when `OnboardedAt != nil`. If the client onboarded but has no active
   session, the step stays done and gets the informational reason `session_disconnected`, so
   the client is not told to reconnect just to receive notices. If the client never
   onboarded, the step is `pending` with reason `not_connected`.
3. `bot_reachable`. If there is no reachability row, the step is `unknown` with reason
   `never_observed`. `reachable` maps to done. `blocked` and `cannot_initiate` map to
   `action_required`, and the reason code is copied from the row.
4. `notifications_decided`. Done when the `product_updates` preference is `Explicit`, with
   either value. Otherwise the step is `pending` with reason `product_updates_undecided`.

`Stage` is the name of the first step that is not done, or `complete`. Status strings and
reason codes are exported constants, so the web, REST, MCP and admin surfaces always use
the same words. The package imports `internal/db` only for its types. A
`db -> lifecycle` import would create a cycle, so the stage is computed by callers and
never inside `internal/db`.

### 2. Store read: `Store.GetClientLifecycleFacts(ctx, userID)`

This goes in a new file, `internal/db/client_lifecycle.go`. It makes one `users` read for
`identity_captured_at` and `onboarding_completed_at`, checks for an active session the way
`ListIdentities` computes `has_session`, and reuses `getBotReachability` and
`ResolveNotificationPrefs`. It returns a `db.ClientLifecycleFacts` struct, which is
converted to `lifecycle.Facts` with a small adapter in `internal/lifecycle`. It adds no
schema.

### 3. Self-service surfaces

- **REST.** `GET /api/account/lifecycle` is registered in `AccountHandlers.Register`
  (`internal/web/account.go`). It returns `lifecycle.Status` plus a `remedies` map (step
  name to relative URL) and uses the same auth and `no-store` handling as `getNotifications`.
- **MCP.** A new tool, `get_my_onboarding_status`, goes in `internal/mcp/tools.go`. It is
  read-only, not destructive, and not open-world, and it takes no inputs. It declares an
  output schema through `outputSchema[...]()`. Registering it means regenerating
  `docs/tool-descriptors.json` and updating `docs/portal-allowlist.json`, and the descriptor
  and allowlist tests (`internal/mcp/descriptors_test.go`, `portal_allowlist_test.go`) must
  pass. `get_my_identity` stays unchanged to keep its contract stable.
- **Web.** `HandleManage` calls `GetClientLifecycleFacts` and `lifecycle.Derive` and passes
  a `GettingStarted []checklistRow` to `renderManagePage`. As with the notifications
  section, a read failure hides the section and does not block disconnect. The remedies are:
  `not_connected` links to `/telegram/connect`; `bot_reachable` links to
  `https://t.me/<TELEGRAM_LOGIN_BOT_USERNAME>` when configured, and otherwise shows text
  ("open the login bot in Telegram and press Start"); `notifications_decided` links to the
  `#notifications` anchor. The page also links to `/docs/product-updates`, so the client can
  see the product-update evidence they are agreeing to receive.
- **Config.** `internal/config/config.go` gets
  `TelegramLoginBotUsername string` from `TELEGRAM_LOGIN_BOT_USERNAME`. The value is
  optional, validated against `^[A-Za-z0-9_]{5,32}$`, and an invalid value is ignored with a
  warning. A username is not a secret.

### 4. Admin projection

`IdentityRow` gets `LifecycleStage string \`json:"lifecycle_stage,omitempty"\``. The field is
filled in the `list_telegram_identities` handler (`internal/mcp/tools.go`), not in
`ListIdentities`, because of the import cycle above. The handler builds `lifecycle.Facts`
from fields the row already has (`IdentityCapturedAt`, `OnboardedAt`, `HasSession`,
`BotReachability`, `NotificationPrefs`), so no extra query is needed.

### 5. Inbound reachability handler

- `internal/db/reachability.go` gets `RecordBotReachabilityTx(ctx, tx *sql.Tx, userID,
  outcome, source)`. The existing upsert SQL moves into an unexported helper that takes an
  `execer`, and `RecordBotReachability` keeps its behaviour. It also gets
  `UserIDByTelegramIDTx` (or an equivalent read through `tx`).
- `internal/bot/reachability.go` (new) adds `ReachabilityHandler(store)`, a
  `HandlerFunc` registered for `db.KindMessage`. For a private chat (`ChatID.Int64 > 0`) it
  resolves the user and records
  `notify.DeliveryOutcome{State: StateReachable, ReasonCode: "inbound_message", Conclusive: true}`
  with source `bot_inbound` through `tx`. It returns the outcome `reachability_recorded`.
  Records are idempotent: a repeated message upserts the same state with a newer
  `observed_at`. The handler sends nothing and reads no content.
- `cmd/server/main.go` registers the handler on `botRegistry`. The handler only runs when
  `BOT_RECEIVER_ENABLED` is set, which is already the case.
- The package doc of `internal/notify/classify.go` and the header of
  `internal/bot/update.go` are updated. Reachability evidence becomes either a conclusive
  Bot API delivery outcome or a message the client sent to the bot. Probes are still
  forbidden.
- `KindCallbackQuery` is not registered. #571 owns it, and `Registry.Register` panics on a
  double registration.

### 6. Product communication stays behind #439

`broadcast.Evaluate` and the worker do not change. The lifecycle view only reads the same
`client_notification_prefs` and `client_bot_reachability` rows that `Evaluate` reads, so the
checklist and the broadcast skip reasons cannot disagree. No new tool can send messages,
and models get no broadcast authority.

## Alternatives

- **A. Persist a `lifecycle_stage` column, updated by triggers or writers.** Dropped. Every
  input already has its own source of truth, and a stored copy would drift: reachability
  changes inside the broadcast worker, and prefs change in three places. Deriving the stage
  on read is cheap (one row per user) and is always correct.
- **B1. Learn reachability from a probe message after login.** Dropped. `internal/notify`
  forbids it explicitly, and it would message clients who never opted in.
- **B2. Store inbound evidence in a separate column (`last_inbound_at`) and keep it out of
  `client_bot_reachability`.** Not chosen, but this is a fallback if review rejects the
  open question. It keeps the "delivery-only" invariant, but then the broadcast `Evaluate`
  and the lifecycle need a merge rule, which brings back the disagreement risk.
- **C. Extend `get_my_identity` instead of adding a tool.** Dropped. Its description and
  output schema are a published contract (`docs/tool-descriptors.json`). Adding lifecycle
  fields there changes a stable tool for an unrelated concern.
- **D. Implement `/start` and `/settings` commands now.** Deferred. Reading text means
  widening `bot.Update`, which `internal/bot/update.go` requires to happen in its own change.
  Consent can already be managed on three surfaces.

## Platform impact

- **Migrations.** None. No new tables or columns. The added `IdentityRow.LifecycleStage`
  field is JSON-only and omitempty.
- **Backward compatibility.** Existing tool outputs are unchanged apart from one additive
  omitempty field on `list_telegram_identities` and one new tool. The descriptor snapshot
  and the portal allowlist must be regenerated in the same PR. If
  `TELEGRAM_LOGIN_BOT_USERNAME` is unset, the page shows text instead of a link.
- **Resource impact.** The manage page and the new endpoint add about 3 small indexed
  reads per request. The admin list adds no queries. The inbound handler does one lookup and
  one upsert per inbound message on a low-volume 1:1 bot.
- **Risks and mitigations.**
  - *Inbound evidence overwrites `blocked`.* This is correct: Telegram only delivers a
    message from a user who has unblocked the bot. The next failed outbound delivery would
    set `blocked` again in any case.
  - *Spoofed chat.* Updates come only from Telegram's `getUpdates` with the bot token, and
    unknown or ambiguous chats are already dropped by `KnownChatFunc`.
  - *Privacy.* No content is decoded, chat ids are not logged (the existing receiver
    convention), and only `stage` and `reason_code` may appear in logs. No new sensitive
    field names are needed in `internal/audit/redact.go`.
  - *Handler error loop.* An error rolls back the update and it is retried by the existing
    sweep. Because the upsert is idempotent, retries are safe.
  - *Stage misread as consent.* `notifications_decided` counts an explicit choice in either
    direction, never "subscribed", and the copy on the page says so.
