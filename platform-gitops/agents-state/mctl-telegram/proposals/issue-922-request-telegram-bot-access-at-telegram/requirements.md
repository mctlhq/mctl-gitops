# Request telegram:bot_access at Telegram OIDC sign-in so the login bot can reach users

## Context

The login bot (`@MCTL_AI_bot`, `internal/botapi`, `internal/digest`, `internal/broadcast`) can start a
chat only with users who sent it /start themselves (`client_bot_reachability.source = bot_start`,
`internal/bot/start.go`). As of 2026-10-28, only 4 of 51 users who reached `connect:success` are
reachable. That blocks every bot-initiated message: the #912 onboarding reminder, digests and
broadcasts. The Telegram OIDC sign-in (`internal/auth/telegramoidc/oidc.go`, `var scopes`) requests
only `openid profile`. Telegram's OpenID Provider also offers `telegram:bot_access` ("Allows your bot
to send direct messages to the user after login"), and we never request it.

This proposal requests that scope on OIDC sign-in only when two conditions both hold: an explicit
rollout flag, `TELEGRAM_OIDC_BOT_ACCESS_ENABLED`, is on (default off), and the OIDC client is the
same bot that sends notifications. Shipping the code changes nothing on any environment. Preview is
enabled by its own gitops PR. Prod is enabled by a separate gitops PR, and only after the preview
check below gives a result that passes the rollout rule. It records a `reachable` observation only when Telegram positively
reports the grant. It also limits the manage page's existing login-bot deep link to users who are
not already reachable. Telegram documents no claim for this scope and shows no `scope` field in its
token response example. So the design treats "Telegram did not tell us" as unknown and writes
nothing in that case.

## User stories

- AS a newly connecting user I WANT to let the login bot message me during the Telegram sign-in I
  already do SO THAT I receive onboarding help and notifications without a separate /start.
- AS an existing user who signed in before this change I WANT a "Let the bot message you" link on
  the manage page SO THAT I can opt in without signing in again.
- AS an operator I WANT reachability to be recorded only from positive evidence SO THAT digest,
  broadcast and onboarding targeting never assumes a reachability that was not observed.
- AS a user who declines the extra permission I WANT sign-in to still succeed SO THAT the bot
  permission is never a condition of using the service. Whether Telegram's consent screen allows
  declining the permission separately from sign-in is unverified. It is checked on preview (task 8)
  before any copy promises it, and before prod is enabled.
- AS the owner I WANT the scope request to stay off until I enable it per environment SO THAT
  merging and releasing the code never changes the production sign-in flow by itself.

## Acceptance criteria (EARS)

- WHEN the server builds a Telegram authorization URL AND the bot-access gate is enabled THE SYSTEM
  SHALL request the scope `openid profile telegram:bot_access` (space-separated, in that order).
- THE SYSTEM SHALL read a boolean `TELEGRAM_OIDC_BOT_ACCESS_ENABLED`, default `false`. An unset,
  empty or unparseable value SHALL mean `false`.
- WHEN the server starts AND `TELEGRAM_OIDC_BOT_ACCESS_ENABLED` is true AND
  `TELEGRAM_LOGIN_BOT_TOKEN` is set AND the numeric bot id before its colon equals
  `TELEGRAM_OIDC_CLIENT_ID` THE SYSTEM SHALL enable the bot-access gate. In every other case the
  gate SHALL be disabled.
- WHILE `TELEGRAM_OIDC_BOT_ACCESS_ENABLED` is false THE SYSTEM SHALL request exactly
  `openid profile`, byte-for-byte the same authorization URL scope as before this change, and SHALL
  log no bot-access warning.
- IF `TELEGRAM_OIDC_BOT_ACCESS_ENABLED` is true AND `TELEGRAM_LOGIN_BOT_TOKEN` is unset or
  malformed, or its bot id differs from `TELEGRAM_OIDC_CLIENT_ID`, THEN THE SYSTEM SHALL request
  only `openid profile` and log one warning at boot. The warning SHALL name the reason and SHALL
  NOT contain the token.
- WHEN the token response carries a `scope` value whose space-separated entries include
  `telegram:bot_access` THE SYSTEM SHALL report the grant as `granted` to the callback.
- IF the token response carries a `scope` value that does not include `telegram:bot_access` THEN
  THE SYSTEM SHALL report `not_granted` and SHALL NOT write any reachability row.
- IF the token response carries no `scope` value, or the value is not a string, THEN THE SYSTEM
  SHALL report `unknown` and SHALL NOT write any reachability row.
- WHEN a `/oauth/telegram/callback` sign-in reports `granted` and has resolved a `users.id` THE
  SYSTEM SHALL upsert `client_bot_reachability` with `state=reachable`,
  `reason_code=oidc_bot_access`, `source=oidc_bot_access` and `observed_at` equal to the callback
  time.
- WHILE the stored reachability row has `state=blocked` THE SYSTEM SHALL NOT overwrite it from an
  OIDC grant.
- IF the stored reachability row has an `observed_at` at or after the grant's observation time THEN
  THE SYSTEM SHALL leave the row unchanged.
- WHEN a later conclusive delivery outcome (`blocked` or `cannot_initiate`) is recorded THE SYSTEM
  SHALL override an `oidc_bot_access` row through the existing `RecordBotReachability` path,
  unchanged.
- IF recording the grant fails THEN THE SYSTEM SHALL log the error (without Telegram ids) and
  complete the sign-in normally.
- WHEN a user declines the permission on Telegram's consent screen, or Telegram returns the user
  with fewer scopes, THE SYSTEM SHALL complete sign-in exactly as it does today. This is a
  requirement on our callback only. Whether Telegram offers a separate decline at all is an open
  question, verified in task 8.
- WHILE the user's reachability state is `reachable` THE SYSTEM SHALL NOT render the
  "Let the bot message you" link on the manage page.
- WHILE the user's reachability state is anything other than `reachable` (no row, `blocked`,
  `cannot_initiate`) AND a login bot username is configured THE SYSTEM SHALL render a
  "Let the bot message you" link to `https://t.me/<bot>?start=onboarding` on the manage page.
- WHEN a sign-in completes THE SYSTEM SHALL log one structured event with the observed
  bot-access signal (`granted`, `not_granted` or `unknown`). The event SHALL NOT include a user id,
  Telegram id or username.
- WHILE the bot-access gate is enabled THE SYSTEM SHALL show on the pre-login `/telegram/connect`
  page one neutral sentence: Telegram may ask whether the MCTL login bot can message the user. The
  sentence SHALL NOT claim that the permission is optional or can be declined. That claim is added
  only in a follow-up change, after task 8 has shown on the real Telegram consent screen that
  declining is possible and sign-in still succeeds.
- WHILE the bot-access gate is disabled THE SYSTEM SHALL NOT show that sentence.
- THE SYSTEM SHALL describe in the privacy page that `client_bot_reachability` may also be learned
  from a sign-in permission.

## Out of scope

- Sending any message to the user as part of sign-in or to "verify" the grant. Probe-based
  classification is forbidden by the existing design (`internal/notify/classify.go` package doc).
- Recording a grant from the Local Bridge activation callback (`internal/oauth/local_bridge_activate.go`).
  It shares the same `telegramoidc.Client`, so the scope is requested there too, but its result is
  not recorded in this proposal.
- Changing notification preferences. A bot-access grant is reachability evidence, not consent to a
  notification category, the same rule `RecordBotStartTx` follows for /start.
- The #912 onboarding reminder itself.
- A schema migration. `client_bot_reachability.source` and `reason_code` are free TEXT.

## Rollout rule

The flag is enabled per environment by separate gitops PRs:

1. Merging and releasing this change enables nothing. The flag is absent everywhere.
2. Preview (`labs/mctl-telegram-preview`): one gitops PR sets the flag. Then task 8 runs.
3. Prod: a separate gitops PR, opened only if task 8 recorded all of the following:
   - sign-in succeeds with the permission accepted;
   - the consent screen lets the user decline the permission separately, and sign-in still
     succeeds after declining;
   - `bot_access_signal` was `granted` when accepted, and `not_granted` when declined.
4. Single stop rule, the same in design.md and tasks.md: if a separate decline is not possible, or
   the check result is `unknown`, prod stays off until a separate owner decision. "Not possible"
   covers a consent screen that makes the permission a condition of signing in, and one that does
   not show it as a separate choice at all. An `unknown` result is not enabled either. Asking users for a
   permission whose grant we cannot observe brings no measurable benefit. Turning it on anyway
   would only add a consent prompt. The owner then decides on #922 whether it is worth enabling
   anyway (the bot may be able to reach users even though we cannot record it), or whether
   another trustworthy grant signal exists. Nothing is promoted automatically.

## Open questions

- Telegram does not document how it reports the `telegram:bot_access` grant. The scope has no
  claims, the token response example has no `scope` field, and the docs do not say whether the user
  can decline it. RFC 6749 section 5.1 allows a server to omit `scope` when it equals the request.
  If Telegram omits it, every sign-in reads `unknown`, nothing is written, and reachability still
  depends on /start or delivery outcomes. The `bot_access_signal` log event (and one operator test
  sign-in, task 1) will show which case holds. A follow-up can then decide whether some other
  signal is trustworthy.
- `TELEGRAM_OIDC_CLIENT_ID` is `8568443430` in the deployed values. The bot token is in Vault and
  was not observed, so its bot id could not be compared. The boot-time gate makes the code safe
  either way. If the ids differ in production, the scope is simply not requested, and the warning
  says why.
- Telegram's JS library uses a separate `write` permission ("Request Direct Messages"), and the
  docs do not say whether it is the same grant as `telegram:bot_access`. This proposal uses only the
  OIDC scope named in the issue.
