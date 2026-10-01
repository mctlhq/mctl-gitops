# Design: issue-679-feat-client-lifecycle-integrate-identity

Scope is fixed by the owner's 2026-10-01 decision on mctlhq/mctl-telegram#679. It has three
implementation tasks: `/start` → reachability, a reachability block on the manage page, and an
explicit category choice on first connect. Nothing in this design adds a lifecycle model, a REST
endpoint, an MCP tool, or a change to the admin projection.

## Current state (main at `f52bc11`)

- **Inbound bot (`internal/bot/`, issue-619).** The receiver long-polls `getUpdates` and makes
  each update durable once (`Store.AcceptUpdate` → `bot_updates(update_id, kind, chat_id, …)`).
  It drops unknown chats through `KnownChatFunc` (`internal/bot/wiring.go`: chat id ≤ 0,
  `ErrUserNotFound` and `ErrTelegramIdentityAmbiguous` are all "unknown") and dispatches
  through `Store.DispatchOnce`, so a handler's writes and the done mark share one
  transaction.
  - The pending sweep (`ListPendingUpdates`) redelivers from the **stored row**, which holds
    only `kind` and `chat_id`.
  - `Update` / `Message` / `Delivery` carry no text by construction (`internal/bot/update.go`,
    `registry.go`).
  - In `cmd/server/main.go` (~line 990) the registry is built with **no handlers**, and the
    receiver starts only when `BOT_RECEIVER_ENABLED` is set. It is **not set** in production
    (`services/labs/mctl-telegram/values.yaml`).
- **Reachability.** `notify.DeliveryOutcome{State, ReasonCode, Conclusive}` comes from
  `internal/notify/classify.go`, which has four states: `unknown`, `reachable`, `blocked`,
  `cannot_initiate`.
  - `Store.RecordBotReachability(ctx, userID, outcome, source)` upserts
    `client_bot_reachability` through `s.DB`, not through a caller's tx, and only for
    conclusive outcomes.
  - The callers are outbound only: `internal/digest/digest.go:152` and
    `internal/broadcast/worker.go:430,439`.
  - `getBotReachability` returns nil (`unknown`) when no row exists.
- **Consent.** `ResolveNotificationPrefs` returns one `ResolvedPref` per category with
  `Explicit`. `product_updates` defaults to unsubscribed.
  `HandleSetNotifications` (`internal/web/manage_notifications.go`) writes every category with
  source `manage_page`. Authentication never writes a preference.
- **Manage page.** `HandleManage` (`internal/web/manage.go`) renders session controls and the
  notification form (`manageTemplate`). A prefs read failure hides the section, so disconnect
  still works.
- **First connect.** `HandleConnectDone` (`internal/web/connect.go`) renders "Step 4 of 4 —
  Done" with a plain "Manage your session" link (line ~451).
- **Broadcast (#439).** `broadcast.Evaluate` skips `unsubscribed`, and skips `unreachable` only
  after a conclusive failed delivery. It is unchanged here.

## Proposed solution

### 1. `/start` → reachability (task 1)

**Classification at accept time, persisted as a kind.** The sweep redelivers from the stored
row, so a `/start` flag must survive in it. Rather than add a column, the receiver stores a
distinct kind:

- `internal/db/bot_updates.go`: add `KindStartCommand = "start_command"`.
- `internal/bot/update.go`: give `Message` a custom `UnmarshalJSON`. It decodes `text` and
  `entities` into **locals**, sets one exported boolean `StartCommand`, and discards the text.
  - `StartCommand` is true only when the first entity has `type == "bot_command"` and
    `offset == 0`, and the command token (`text[:length]` in UTF-16 units, up to an optional
    `@suffix`) equals `/start`.
  - A payload after the command (`/start onboarding`) is ignored and never stored.
  - The struct still has no text field; the package doc states that `StartCommand` is the
    only content-derived fact and why.
- `Update.Kind()` returns `KindStartCommand` for a message with `StartCommand == true`, and
  `KindMessage` for any other message. Callback and unsupported kinds are unchanged.
- The metrics label set gains one bounded value (`start_command`): the `kind` label of
  `bot_updates_total` is still drawn only from the `db.Kind*` constants, never from content.
- `edited_message`, `channel_post` and `edited_channel_post` are not decoded into `Message`,
  so a `/start` in them is never `start_command`; they keep their current `unsupported`
  kind.

**Handler.**

- `internal/db/reachability.go`: move the upsert SQL into an unexported helper over an
  `execer`. Add `RecordBotReachabilityTx(ctx, tx, userID, outcome, source)` and a tx-scoped
  Telegram-id-to-user read (`UserIDByTelegramIDTx`, same ambiguity rule as
  `UserIDByTelegramID`).
  - `RecordBotReachability` keeps its behaviour, including the no-op on a non-conclusive
    outcome.
- `internal/bot/start.go` (new): `StartHandler(store)` is a `HandlerFunc` for
  `KindStartCommand`. For `ChatID.Int64 > 0` it resolves the user through `tx` and records
  `notify.DeliveryOutcome{State: StateReachable, ReasonCode: "bot_start", Conclusive: true}`
  with source `bot_start` through `tx`. It returns the outcome `db.OutcomeReachabilityRecorded`
  (`"reachability_recorded"`, a new named constant next to the other `Outcome*` values in
  `internal/db/bot_updates.go`). The `mctl_bot_updates_total` Help text in
  `internal/metrics/metrics.go`, which enumerates every outcome, is updated in the same change.
  - It sends nothing, touches no preference, and logs no chat id.
  - A repeated `/start` upserts the same state with a newer `observed_at` (idempotent).
- `cmd/server/main.go`: register only `StartHandler` for `KindStartCommand`. `KindMessage`
  and `KindCallbackQuery` stay **unregistered**: plain messages end as `no_handler` (inert:
  no write besides the update row, no send, no model or action path), and callbacks remain
  #571's. Update the comment block there.
- A `/start` overwrites a prior `blocked` or `cannot_initiate`. That is correct, because
  Telegram delivers it only from a user who has started the bot, and the next failed outbound
  delivery would set the state again.

### 2. Manage page reachability block (task 2)

- `internal/config/config.go`: add an optional `TelegramLoginBotUsername` read from
  `TELEGRAM_LOGIN_BOT_USERNAME`. It is validated against Telegram's username rule
  (5–32 chars, `[A-Za-z0-9_]`, ending in `bot`, case-insensitive). An invalid value is
  ignored with one warning at startup, not fatal.
- `ManageServer` receives the username (constructor argument). `HandleManage` reads
  reachability through an exported `Store.GetBotReachability(ctx, userID)` (a thin wrapper
  over `getBotReachability`) and passes a small view to the template: state label, an
  optional `t.me` URL built by the shared `loginBotStartURL(username)` helper (the same one the
  success page uses, §3; it returns `https://t.me/<username>?start=onboarding`, or "" when the
  username is unset), and a `NotReachable` flag. Neither page builds the URL inline.
- `manageTemplate`: a "Login bot" block above the notification form.
  - It shows `Not yet observed — we have not yet seen your login bot respond; start it to
    confirm delivery` (no row), `Reachable`, `Blocked`, or `Not started` (for
    `cannot_initiate`), and the link or plain-text instructions. The no-row copy is
    observational only and never says the client did not start the bot: a client may have
    started it before the receiver was enabled, and that start was never recorded.
  - While not reachable, it adds a note: "The login bot cannot deliver the categories you
    enable until you start it."
  - A reachability read error hides the block, mirroring the prefs-failure rule.
- Rendering is read-only. No write occurs on GET.

### 3. Explicit category choice on first connect (task 3)

- `ConnectConfig` (`internal/web/connect.go`) gains `LoginBotUsername`, set from the same
  validated `TelegramLoginBotUsername` in `cmd/server/main.go`, because `HandleConnectDone`
  belongs to `ConnectServer`, not `ManageServer`. The URL is built by one shared helper
  (`loginBotStartURL(username)`), so the two pages cannot diverge.
- `HandleConnectDone` success page: replace the plain "Manage your session" link with an
  explicit step: "Choose which notifications the login bot may send you" →
  `/telegram/connect/manage?onboarding=1#notifications`, plus "Start the login bot" with the
  same `t.me` link when configured.
  - The success page writes nothing new; authentication still writes no preference.
- `HandleManage`: when `product_updates` has `Explicit == false`, render a prompt above the
  form ("You have not chosen yet. Product updates stay off until you save."). With
  `onboarding=1`, give the notification section `id="notifications"` focus via the anchor.
  - The checkbox reflects the resolved default (unchecked).
- The existing `HandleSetNotifications` remains the only consent writer on the web surface,
  and `broadcast.Evaluate` reads the same rows. A client who never saves stays `unsubscribed`;
  one who saves "subscribed" joins the audience.

### 4. Docs

- `internal/notify/classify.go` package doc: reachability evidence is either a conclusive Bot
  API delivery outcome or a `/start` the client sent to the login bot. Probes stay forbidden.
- `internal/bot/update.go` header and `registry.go` `Delivery` comment: name `StartCommand`
  as the one content-derived routing fact.
- `docs/runbook.md`: a short "Login bot `/start` and onboarding" section covering the
  `start_command` kind and its outcomes, the `bot_start` source,
  `TELEGRAM_LOGIN_BOT_USERNAME`, and the rollout order (release → `BOT_RECEIVER_ENABLED` →
  live proof).

## Alternatives

- **A. Register a handler for `KindMessage` and decide `/start` inside it.** Dropped. The
  sweep redelivers only `kind` and `chat_id`, so the handler could not tell `/start` from
  other text after a restart without storing content. It would also give every plain message
  a handler, which is the opposite of the required inertness.
- **B. Add a `command` column to `bot_updates`.** Workable, but a migration for one boolean
  that a kind value already expresses. Not chosen.
- **C. Treat any inbound message as reachability evidence.** Dropped. The owner scoped
  evidence to `/start`, and other messages must stay inert.
- **D. Lifecycle model, REST endpoint, MCP tool, admin stage.** Out of scope by owner
  decision. They can be proposed separately if needed.

## Platform impact

- **Migrations.** None. `start_command` is a new value in the existing `bot_updates.kind`
  TEXT column.
- **Backward compatibility.** Rows already stored as `message` keep that kind and stay
  `no_handler`. No MCP tool, descriptor, allowlist or broadcast behaviour changes.
- **Activation.** Nothing runs until `BOT_RECEIVER_ENABLED` is set in a separate gitops PR
  after the release. Without `TELEGRAM_LOGIN_BOT_USERNAME`, the pages show text instead of a
  link.
- **Resource impact.** One indexed read per manage-page load. Per `/start` on a low-volume
  1:1 bot: two identity lookups and one upsert. `KnownChatFunc` resolves the chat before
  dispatch (outside the tx, as for every update), then `StartHandler` resolves it again through
  `UserIDByTelegramIDTx` inside the dispatch tx so the write uses a user id read in the same
  transaction. Both are indexed point reads.
- **Risks and mitigations.**
  - *Content leakage via the new decode.* Text is decoded into a local and dropped. A test
    asserts that no field or log line contains it.
  - *Spoofed chat.* Updates come only from `getUpdates` with the bot token, and unknown or
    ambiguous chats are dropped before dispatch.
  - *Handler error loop.* An error rolls back the write and the done mark together, and the
    sweep retries. The upsert is idempotent.
  - *Reachability misread as consent.* Separate rows and separate copy on the page. `/start`
    never writes a preference, and a test pins that.
