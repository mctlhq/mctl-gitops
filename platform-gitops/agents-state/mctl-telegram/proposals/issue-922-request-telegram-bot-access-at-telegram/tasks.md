# Tasks: issue-922-request-telegram-bot-access-at-telegram

- [ ] 1. Add the same-bot gate to `internal/config/config.go`: `BotIDFromToken(token) (string, bool)`
  and `(*Config).LoginBotMatchesOIDCClient() (bool, string)`, with reasons `bot_token_unset`,
  `bot_token_malformed` and `bot_id_mismatch`. DoD: pure functions with unit tests, and no token
  value ever placed in a returned reason or error.
- [ ] 2. In `internal/auth/telegramoidc/oidc.go`, add `ScopeBotAccess`, `requestedScopes(bool)`,
  `Config.RequestBotAccess`, the `BotAccess` tri-state, `Identity.BotAccess`, and the pure
  `parseBotAccess(raw any, requested bool)`. Set it in `Exchange` from `tok.Extra("scope")` after
  id_token verification. DoD: the `Authenticator` interface is unchanged, and `go vet` and
  `golangci-lint` are clean.
- [ ] 3. (depends on 1, 2) Wire the gate:
  - add `TelegramOIDCRequestBotAccess bool` to the oauth server `Config` in
    `internal/oauth/server.go`, and pass it to `telegramoidc.New`;
  - compute it in `cmd/server/main.go` from `LoginBotMatchesOIDCClient`, and log one
    `slog.Warn` with only the reason when it is false.
  DoD: the boot log shows the warning when the ids differ, and none when they match.
- [ ] 4. Add `notify.SourceOIDCBotAccess = "oidc_bot_access"` and
  `(*db.Store).RecordOIDCBotAccessGrant(ctx, userID, observedAt) (bool, error)` in
  `internal/db/reachability.go`. Its upsert never overwrites `state='blocked'` or a row whose
  `observed_at` is newer or equal. DoD: works on SQLite and Postgres, and is covered by T5-T8.
- [ ] 5. (depends on 2, 4) In the `/oauth/telegram/callback` handler, after
  `EnsureUserByTelegramCapture`:
  - log `bot_access_signal` with no identifiers;
  - on `BotAccessGranted`, call `RecordOIDCBotAccessGrant` best-effort, so an error is logged and
    the sign-in continues.
  DoD: a decline or an unknown signal leaves the sign-in flow byte-for-byte unchanged.
- [ ] 6. In `internal/web/manage.go`, render the "Let the bot message you" link (and the plain-text
  fallback) only when `.Bot.NotReachable`. DoD: a reachable user sees no link; no row, `blocked` and
  `cannot_initiate` all show it.
- [ ] 7. Copy: add one neutral sentence on the optional bot permission to the pre-login page
  (`internal/web/connect.go` about line 436), and extend the `client_bot_reachability` row in
  `internal/web/privacy.html` to mention the sign-in permission. Update any pinned-copy tests.
  DoD: the copy says the permission is optional and does not contradict Telegram's consent screen.
- [ ] 8. (depends on 3, 5) Deploy to `labs/mctl-telegram-preview` first. The operator does one
  test sign-in, accepting and then declining the permission. Record in the PR whether the
  `bot_access_signal` log shows `granted`/`not_granted` or `unknown`. DoD: the observed behaviour is
  written in the PR or the issue before prod rollout. Sign-in succeeds both ways.

## Tests

- [ ] T1. `telegramoidc`: the `AuthCodeURL` of a `Client` built with `RequestBotAccess=true` has
  query `scope=openid profile telegram:bot_access`; with `false` it has `scope=openid profile`.
  Build the `Client` against the httptest provider from `oidc_verify_test.go`.
- [ ] T2. `parseBotAccess` table test: not requested gives unknown; nil, non-string or empty gives
  unknown; `"openid profile telegram:bot_access"` gives granted; `"openid profile"` gives
  not_granted; extra whitespace and different order are still parsed correctly.
- [ ] T3. `Exchange` end-to-end against the httptest provider: the token response with `scope`
  including the scope yields `Identity.BotAccess == granted`, and without a `scope` field yields
  `unknown`.
- [ ] T4. `config`: `BotIDFromToken` handles valid, missing colon, non-digit and empty input, and
  `LoginBotMatchesOIDCClient` returns each reason. Use a synthetic token such as `123456:AAsynthetic`,
  never a real one.
- [ ] T5. `db`: `RecordOIDCBotAccessGrant` with no row inserts `reachable`/`oidc_bot_access`.
- [ ] T6. `db`: over a stored `blocked` row, nothing is written and `applied == false`.
- [ ] T7. `db`: over an older `cannot_initiate` row it applies; over a row with a newer
  `observed_at` it does not.
- [ ] T8. `db`: after a grant, `RecordBotReachability` with a conclusive `blocked` outcome
  overrides it.
- [ ] T9. `oauth` callback with a fake Authenticator returning `BotAccessGranted` writes a
  reachability row. With `BotAccessUnknown` and with `BotAccessNotGranted`, no row exists after the
  callback, and both complete sign-in with the same redirect as today. Use existing personas
  (Alice/Bob) and ids already used in `internal/oauth` tests.
- [ ] T10. `oauth` callback: a store error from `RecordOIDCBotAccessGrant` does not change the
  HTTP outcome.
- [ ] T11. `web/manage`: the link is absent for `reachable`, present for nil row, `blocked` and
  `cannot_initiate`, and the fallback text is shown when the username is empty and the user is not
  reachable.

## Rollback

- Revert the PR, or ship a patch that sets `RequestBotAccess` to false. Sign-in goes back to
  `openid profile` on the next deploy.
- `oidc_bot_access` rows already written can stay: they are ordinary `reachable` rows that later
  conclusive delivery outcomes override.
- To remove them anyway:
  `DELETE FROM client_bot_reachability WHERE source = 'oidc_bot_access';`
  This brings those users back to "unknown". No schema change needs undoing.
