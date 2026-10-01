# Tasks: issue-679-feat-client-lifecycle-integrate-identity

Scope is fixed by the owner's 2026-10-01 decision on mctlhq/mctl-telegram#679: three
implementation tasks, plus tests and docs. Do NOT add the `internal/lifecycle` package,
`GET /api/account/lifecycle`, an MCP tool (`get_my_onboarding_status` or any other),
`IdentityRow.LifecycleStage`, bot commands other than `/start`, consent changes through the
bot, or callback handling (#571). No change to `docs/tool-descriptors.json` or
`docs/portal-allowlist.json` is expected.

- [ ] 1. **`/start` records reachability, never consent.**
  - (a) Add `db.KindStartCommand = "start_command"`.
  - (b) Give `bot.Message` a custom `UnmarshalJSON` that decodes `text` and `entities` into locals only, sets the exported `StartCommand bool` (first entity is a `bot_command` at offset 0 whose token, up to an optional `@suffix`, equals `/start`; any payload ignored), and keeps no text.
  - (c) Make `Update.Kind()` return `KindStartCommand` for such messages.
  - (d) Add `RecordBotReachabilityTx` (the upsert moved into an `execer` helper; `RecordBotReachability` unchanged) and `UserIDByTelegramIDTx`.
  - (e) Add `bot.StartHandler` in `internal/bot/start.go`. Through the dispatch tx, for chat id > 0, it records `reachable` / reason `bot_start` / source `bot_start` and returns `reachability_recorded`.
  - (f) Register only that handler, for `KindStartCommand`, in `cmd/server/main.go`. `KindMessage` and `KindCallbackQuery` stay unregistered.

  — DoD: a plain message ends `no_handler` with no other write and no send; `/start` writes only `client_bot_reachability`; no notification preference changes; no text is held in any struct field; `RecordBotReachability`'s existing tests pass unchanged.
- [ ] 2. **Manage page shows reachability and a `t.me` entry point.**
  - (a) Add the optional config `TelegramLoginBotUsername` (`TELEGRAM_LOGIN_BOT_USERNAME`), validated as a Telegram bot username; an invalid value is ignored with a startup warning.
  - (b) Pass it to `ManageServer`.
  - (c) Add `Store.GetBotReachability`.
  - (d) Render a "Login bot" block above the notification form in `manageTemplate`. It shows `unknown` / `reachable` / `blocked` (and "not started" for `cannot_initiate`), a `https://t.me/<username>?start=onboarding` link only when configured (otherwise plain-text instructions), and, while not reachable, a note that enabled categories cannot be delivered until the bot is started.

  — DoD: GET performs no write; a reachability read error hides the block and leaves disconnect working; config tests cover set, unset and invalid values.
- [ ] 3. **Explicit category choice on first connect.**
  - (a) Change the `HandleConnectDone` success page to show an explicit "Choose which notifications the login bot may send you" step linking to `/telegram/connect/manage?onboarding=1#notifications`, plus the start-the-bot link when configured.
  - (b) In `HandleManage`, render a "not chosen yet — product updates stay off until you save" prompt while `product_updates` has `Explicit == false`, and give the section `id="notifications"`.
  - (c) Keep `HandleSetNotifications` as the only web consent writer.

  — DoD: connecting or authenticating writes no preference; `product_updates` stays unsubscribed until an explicit save.
- [ ] 4. **Docs.**
  - (a) Update the package doc in `internal/notify/classify.go`: a client-sent `/start` is now reachability evidence, and probes stay forbidden.
  - (b) Update the headers in `internal/bot/update.go` and the `Delivery` comment in `internal/bot/registry.go` to name `StartCommand` as the only content-derived routing fact.
  - (c) Update the comment at the registry in `cmd/server/main.go`.
  - (d) Add a short "Login bot `/start` and onboarding" section to `docs/runbook.md`: the `start_command` kind and outcomes, the `bot_start` source, `TELEGRAM_LOGIN_BOT_USERNAME`, and the rollout order (release → separate gitops PR for `BOT_RECEIVER_ENABLED` → live proof).

  — DoD: `docs/runbook_test.go` passes.
- [ ] 5. Run `go fmt`, `go vet` and `golangci-lint` on the changed packages. — DoD: all clean. Test fixtures use only the existing personas (Alice, Bob, Carol, Dana), with ids checked with `git grep`.

## Tests (each mutation-verified: revert the change it covers and watch it fail)

- [ ] T1. Classification. Each of these sets `StartCommand=true`, kind `start_command`:
  - `/start`
  - `/start@SomeBot`
  - `/start onboarding`

  Each of these sets `StartCommand=false`, kind `message`:
  - plain text
  - `/settings`
  - `/startx`
  - a `/start` entity at a non-zero offset
  - a `bot_command` that is not the first entity
  - text with no entities

  After decoding, the `Update` value (reflect over all fields) holds no part of the text or payload.
- [ ] T2. Handler: a known private chat with `/start` → `reachable` with reason and source `bot_start`, and outcome `reachability_recorded`. An unknown, negative or ambiguous chat is dropped before dispatch (`unknown_chat`) and records nothing. A handler error rolls back the reachability row and the done mark together. A redelivered update is not handled twice (`DispatchOnce`).
- [ ] T3. Inertness: a plain `message` update from a known chat ends `no_handler`, writes no `client_bot_reachability` and no `client_notification_prefs` row, and makes no outbound HTTP call (stub transport asserts zero requests).
- [ ] T4. `/start` leaves every `client_notification_prefs` row (and resolved prefs) byte-identical, including for a user with explicit prefs.
- [ ] T5. `/start` overwrites a prior `blocked` with `reachable`; a later non-conclusive outbound outcome (429) leaves it `reachable`.
- [ ] T6. Manage page render covers:
  - each of `unknown` (no row), `reachable` and `blocked`, with the right label;
  - the `t.me` link only when the username is configured, and text otherwise;
  - the not-delivered note only when the state is not reachable;
  - a failing reachability read hides the block while disconnect still renders;
  - no write happens on GET.
- [ ] T7. First connect: the success page contains the explicit choice link to `/telegram/connect/manage?onboarding=1#notifications`, and the connect flow writes no preference. The manage page shows the "not chosen yet" prompt while `product_updates` is not explicit, and hides it after a save.
- [ ] T8. Broadcast respects the choice. Before any save, a `product_updates` campaign audience skips the user as `unsubscribed`. After saving `product_updates=subscribed` through `HandleSetNotifications`, the user is in the audience. `broadcast.Evaluate` tests pass unchanged.
- [ ] T9. Redaction: the receiver and handler log lines, captured through slog, contain no chat id, no message text and no payload for `/start` or plain messages.
- [ ] T10. Config: `TELEGRAM_LOGIN_BOT_USERNAME` set and valid, unset, and invalid (ignored with a warning).

## Rollout (outside this PR)

1. Release the code. The receiver stays off because `BOT_RECEIVER_ENABLED` is unset in production.
2. A separate mctl-gitops PR sets `BOT_RECEIVER_ENABLED` and `TELEGRAM_LOGIN_BOT_USERNAME` for `labs/mctl-telegram`, only after the release is live.
3. Live proof: onboarding → `/start` → reachability `reachable` → explicit category preferences saved → a broadcast preview respects them. #679 closes only after this proof.

## Rollback

All changes are additive, with no migration. To roll back, revert the PR and redeploy the
previous image. To stop only the inbound writes, unset `BOT_RECEIVER_ENABLED`. Rows written
with `source = bot_start` are valid observations and can stay. If they must be removed, run
`DELETE FROM client_bot_reachability WHERE source = 'bot_start'`, which returns those users to
`unknown`. Rows already stored with kind `start_command` are inert once the handler is gone,
because they end as `no_handler` on the sweep.
