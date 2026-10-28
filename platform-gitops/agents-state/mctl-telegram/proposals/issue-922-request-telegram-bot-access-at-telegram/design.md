# Design: issue-922-request-telegram-bot-access-at-telegram

## Current state

- `internal/auth/telegramoidc/oidc.go`
  - `var scopes = []string{oidc.ScopeOpenID, "profile"}` is passed as `oauth2.Config.Scopes` in
    `New`.
  - `Client.AuthCodeURL` adds the nonce and PKCE.
  - `Client.Exchange` calls `oauth2.Config.Exchange`, verifies the `id_token` and returns
    `*Identity` (TelegramID, Sub, Username, FirstName, LastName). The `oauth2.Token` is discarded,
    so nothing about granted scopes reaches callers today.
  - The `Authenticator` interface is the test seam. Fakes are in `internal/localbridgetest`
    (`OIDC`) and the oauth tests.
- `internal/auth/telegramoidc/oidc_verify_test.go` (`TestExchange_VerifiesAgainstSecp256k1JWKS`)
  already runs an httptest OpenID Provider with a `/token` handler that returns `access_token`,
  `token_type` and `id_token`. It can be extended to return a `scope` value.
- `internal/oauth/server.go`
  - Builds the client at about line 750 with `telegramoidc.New(ctx, telegramoidc.Config{...})`.
    The oauth `Config` has the OIDC client id and secret but not the bot token.
  - The `/oauth/telegram/callback` handler (about line 1822) calls `s.tgoidc.Exchange`, then
    `s.store.EnsureUserByTelegramCapture`, which returns `uid`. Then follow best-effort blocks
    (auto-grant tier) that log and continue on error.
- `internal/oauth/local_bridge_activate.go:898` calls the same `Exchange` for device activation.
- `internal/db/reachability.go`
  - `RecordBotReachability` writes outbound delivery outcomes with an unconditional upsert, so a
    later `blocked`/`cannot_initiate` always wins.
  - `RecordInboundBotReachabilityTx` writes /start outcomes with an upsert guarded by
    `observed_at < EXCLUDED.observed_at`.
  - `GetBotReachability` reads the row.
  - Schema (`internal/db/db.go` about lines 880 and 1207): `state`, `reason_code` and `source` are
    TEXT with no CHECK constraint, so a new source value needs no migration.
- `internal/bot/start.go`: `reasonBotStart = "bot_start"` is both reason_code and source. /start is
  documented as reachability evidence, not consent.
- `internal/notify/classify.go`: states are `unknown`, `reachable`, `blocked` and
  `cannot_initiate`. Probes are forbidden.
- `internal/web/manage.go`
  - `loginBotStartURL(username)` builds `https://t.me/<bot>?start=onboarding`.
    `buildBotReachabilityView` sets `NotReachable=false` only for `reachable`.
  - The template renders `<a href="{{.Bot.StartURL}}">Start the login bot</a>` unconditionally
    whenever a username is set, even for reachable users. Only the explanation is gated on
    `.Bot.NotReachable`.
  - So most of issue item 3 exists already. What is missing is gating the link on not-reachable,
    plus the copy.
- `internal/web/connect.go:436`: pre-login copy "Click the button below to sign in with Telegram
  and link your account to this MCP connector." It says nothing about the bot. Line 476 offers the
  start link after success.
- `internal/web/privacy.html:73-74` describes `client_bot_reachability` as learned "from which
  delivery". That wording needs to cover the sign-in grant too.
- `internal/config/config.go`
  - `TelegramLoginBotToken` (`TELEGRAM_LOGIN_BOT_TOKEN`) and `TelegramOIDCClientID` are read
    independently.
  - The `TelegramOIDCClientID` comment says it is "the login bot's numeric id", but nothing checks
    that against the token.
- Telegram docs (https://core.telegram.org/bots/telegram-login, fetched 2026-10-28):
  - `telegram:bot_access` returns no claims.
  - The token response example lists only `access_token`, `token_type`, `expires_in` and
    `id_token`, with no `scope`.
  - The docs do not say whether the user can decline the scope.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`
  - Tenant `labs`, `AUTH_MODE: local-jwt`, `TELEGRAM_OIDC_CLIENT_ID: "8568443430"`,
    `TELEGRAM_LOGIN_BOT_USERNAME: "MCTL_AI_bot"`.
  - `TELEGRAM_LOGIN_BOT_TOKEN` comes from Vault `secret/data/platform/mctl-telegram/login` and
    `TELEGRAM_OIDC_CLIENT_SECRET` from `.../oauth` (`oidc-client-secret`).
  - The bot token value was not observable, so whether its bot id equals `8568443430` could not be
    verified. This is recorded under Open questions, and the design handles it with a boot-time
    gate.
- The mctl MCP tools were not called: the gitops values were enough for the config this design
  depends on. Prod reachability counts are taken from the issue, not re-measured.

## Proposed solution

### 1. Scope request behind a rollout flag and a same-bot gate (`internal/auth/telegramoidc`, `internal/config`, `cmd/server`)

- In `oidc.go`, add `const ScopeBotAccess = "telegram:bot_access"`. Replace the package-level
  `scopes` with a function `requestedScopes(botAccess bool) []string` that returns
  `[openid profile]` or `[openid profile telegram:bot_access]`.
- Add `Config.RequestBotAccess bool`. `New` uses it to set `oauth2.Config.Scopes`.
- In `internal/config`, add a pure helper `BotIDFromToken(token string) (string, bool)`. It returns
  the digits before the first colon, or false if they are missing or not decimal.
- Add `LoginBotMatchesOIDCClient() (ok bool, reason string)` on `*Config`, with reasons
  `bot_token_unset`, `bot_token_malformed` and `bot_id_mismatch`.
- Add `TelegramOIDCBotAccessEnabled bool`, read with `envBool("TELEGRAM_OIDC_BOT_ACCESS_ENABLED",
  false)`, the same helper as `BOT_RECEIVER_ENABLED`. It defaults to off.
- `cmd/server/main.go` computes the gate as
  `cfg.TelegramOIDCBotAccessEnabled && LoginBotMatchesOIDCClient()`. It passes the gate into the
  oauth server `Config` as a new `TelegramOIDCRequestBotAccess bool`. `internal/oauth/server.go`
  forwards it to `telegramoidc.Config.RequestBotAccess`.
- With the flag off, nothing is logged about bot access, and the scope set is exactly today's.
- With the flag on and the same-bot check failing, main logs one
  `slog.Warn("telegram:bot_access not requested", "reason", reason)`. The token never appears in
  the log. `bot_token`-like keys are already covered by `internal/audit/redact.go`, and the warning
  carries only the reason enum.
- When the gate is on, main logs one `slog.Info("telegram:bot_access requested")` at boot. That way
  the preview check can confirm which state the running pod is in.

Why two gates:
- The flag separates shipping from enabling. Without it, the first prod deploy with matching ids
  would change the sign-in consent screen for every user before the preview check ran. The flag
  makes "preview first" a technical guarantee rather than a task-list promise. Each environment is
  enabled by its own gitops PR, under the rollout rule in requirements.md.
- The same-bot check stays as a safety net under the flag. If the OIDC client and the sending bot
  differ, the grant goes to a bot that never sends, so recording `reachable` would be wrong for the
  bot that does send. Comparing two values we already hold proves this offline at boot.

### 2. Report the grant signal (`telegramoidc.Exchange`)

- Add a tri-state type:

  ```go
  type BotAccess string
  const (
      BotAccessUnknown    BotAccess = "unknown"     // no usable scope in the token response
      BotAccessGranted    BotAccess = "granted"     // scope present and includes telegram:bot_access
      BotAccessNotGranted BotAccess = "not_granted" // scope present and excludes it
  )
  ```

- Add `Identity.BotAccess BotAccess`.
- Add a pure function `parseBotAccess(raw any, requested bool) BotAccess`:
  - not requested gives `unknown`
  - a non-string or empty value gives `unknown`
  - otherwise it splits on whitespace (`strings.Fields`) and returns `granted` or `not_granted`
- `Exchange` calls it with `tok.Extra("scope")` after the id_token checks succeed.
- `parseIdentity` stays claims-only.
- The `Authenticator` interface signature is unchanged, so fakes only gain an optional field.

### 3. Record the grant (`internal/db/reachability.go`, `internal/oauth/server.go`)

- New store method:

  ```go
  // RecordOIDCBotAccessGrant records a reachable observation from a sign-in
  // where Telegram reported the telegram:bot_access grant. It never overwrites
  // a stored blocked row (a grant does not unblock the bot) and never
  // overwrites a newer observation. applied reports whether a row was written.
  func (s *Store) RecordOIDCBotAccessGrant(ctx context.Context, userID int64, observedAt time.Time) (applied bool, err error)
  ```

- SQL: the same INSERT as `RecordInboundBotReachabilityTx`, with
  `state='reachable', reason_code='oidc_bot_access', source='oidc_bot_access'`, and
  `ON CONFLICT DO UPDATE ... WHERE client_bot_reachability.state <> 'blocked' AND
  (client_bot_reachability.observed_at IS NULL OR client_bot_reachability.observed_at < EXCLUDED.observed_at)`.
  - It validates `userID > 0` and a non-zero `observedAt`.
  - The query works in both SQLite and Postgres, because the existing upserts already use this
    dialect.
- Define `const SourceOIDCBotAccess = "oidc_bot_access"` in `internal/notify` next to the states,
  so digest and broadcast code can refer to it.
- Interaction with the existing rules:
  - A later `blocked` or `cannot_initiate` delivery goes through `RecordBotReachability`'s
    unconditional upsert and wins, which the issue requires.
  - A grant may lift `cannot_initiate`, because that state means the user had not started the bot,
    which is exactly what the grant addresses. A later failed delivery re-records it if the grant
    did not actually work.
  - A grant never lifts `blocked`, which the issue requires. A user who unblocks and sends /start
    still lifts it through the /start path, unchanged.
- In the `/oauth/telegram/callback` handler, after `EnsureUserByTelegramCapture` returns `uid`:

  ```go
  slog.Info("telegram oidc sign-in", "bot_access_signal", string(identity.BotAccess))
  if identity.BotAccess == telegramoidc.BotAccessGranted {
      if _, err := s.store.RecordOIDCBotAccessGrant(r.Context(), uid, time.Now().UTC()); err != nil {
          slog.Error("record oidc bot access grant failed", "err", err)
      }
  }
  ```

  The write is best-effort, like the auto-grant block next to it. A DB failure never fails the
  sign-in. The log event carries no ids, so it is safe under the redaction rules and lets operators
  measure how Telegram actually reports the grant.

### 4. Manage page link (`internal/web/manage.go`)

- In the login-bot block, render the link only inside `{{if .Bot.NotReachable}}`, with the text
  "Let the bot message you". The target stays `loginBotStartURL` (`?start=onboarding`).
- Reusing the existing start payload keeps one /start path (`internal/bot/start.go`), so tapping
  Start records `bot_start` reachability exactly as today. No new start payload or handler is
  needed.
- Keep the plain-text fallback for an unset username inside the same condition.
- A reachable user sees the "Reachable" label and no link.

### 5. Copy (`internal/web/connect.go`, `internal/web/privacy.html`)

- Add one short neutral sentence to the pre-login page at `connect.go:436`, rendered only while the
  gate is on: "Telegram may also ask whether the MCTL login bot can message you."
  - Do NOT add "This is optional" or "you can sign in without it" in this change. Whether
    Telegram's consent screen allows declining the permission separately is unverified (Open
    questions).
  - If task 8 shows that it does, a follow-up copy change adds that sentence.
  - If it does not, prod stays off under the rollout rule, so no user is asked for a permission
    they cannot refuse.
  - The connect page view model gains a `BotAccessRequested bool` from the same gate value.
- Update the `client_bot_reachability` row in `privacy.html` to say "from which delivery, /start,
  or sign-in permission".
- Adjust any test that pins exact copy (`internal/web/connect_test.go`, `landing_privacy_test.go`,
  `security_test.go`) in the same change.

## Alternatives

- **Treat an absent `scope` as granted.** RFC 6749 allows a server to omit `scope` when it equals
  the request, so this would likely mark most new users reachable. Dropped: the issue forbids
  reading "could not observe" as "observed", and a user who declined would be indistinguishable.
  The `bot_access_signal` log event lets a follow-up revisit this with evidence.
- **Prove the grant by sending a welcome message right after sign-in.** This yields a conclusive
  delivery outcome. Dropped: probe-based classification is explicitly forbidden
  (`internal/notify/classify.go`), and an unsolicited message at sign-in contradicts the
  notification-consent model.
- **Always request the scope and drop the same-bot check.** Simpler, but if the OIDC client and the
  sending bot ever diverge (a token rotation to a new bot), users are asked for a permission that
  helps nobody, and reachability rows would be wrong. The check costs only a string comparison at
  boot.
- **A new `?start=bot_access` payload for the manage link.** It gives no reachability benefit over
  `?start=onboarding`: the start handler does not key on the payload. It would add a second payload
  to keep in sync with the connect page.

## Platform impact

- **Migrations:** none. `source` and `reason_code` are free TEXT.
- **Backward compatibility:**
  - `Authenticator` is unchanged. `Identity` gains a field whose zero value (`""`) is treated like
    `unknown` (only `granted` writes).
  - Existing reachability rows are untouched. Users who signed in before the change opt in through
    the manage link or a new sign-in.
- **Config:** one new env var, `TELEGRAM_OIDC_BOT_ACCESS_ENABLED`, a boolean that defaults to
  `false`. Neither this change nor its release adds it to any values file.
  - Preview is enabled by a separate gitops PR to `services/labs/mctl-telegram-preview`.
  - Prod is enabled by another gitops PR, only under the rollout rule.
  - The gate also needs `TELEGRAM_LOGIN_BOT_TOKEN` and `TELEGRAM_OIDC_CLIENT_ID` to match, and both
    are already deployed.
  - With the flag on, an environment without a bot token gets the old scope set and a boot
    warning.
- **Resources:** one extra upsert on granted sign-ins only. Negligible.
- **Risks and mitigations:**
  - Telegram rejects the unknown or extra scope, or changes the consent flow in a way that blocks
    sign-in. Mitigation: the flag is off by default, so only preview sees the change until task 8
    passes. Rollback on any environment is setting the flag to false (see tasks.md Rollback), with
    no code revert.
  - The permission cannot be declined separately: either it is a condition of signing in, or it is
    not shown as a separate choice. Mitigation: the single stop rule in requirements.md (Rollout
    rule, item 4) keeps prod off until a separate owner decision. The same rule applies when the
    check result is `unknown`. The copy never claims the permission is optional.
  - The grant is reported but delivery still fails. Mitigation: the first real delivery records
    `cannot_initiate`/`blocked` through the existing conclusive path and overrides the row.
  - The signal is always `unknown`. Then nothing changes versus today except the consent prompt.
    The log event makes this visible, so it does not fail silently.
  - Privacy: no new personal data is stored. The log event has no identifiers.
