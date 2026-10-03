# Client notification identity, bot reachability and preferences

## Context

`mctl-telegram` already keeps an admin-facing client projection: `users.telegram_login_id`,
`users.telegram_username`, `users.telegram_display_name`, `users.access_tier`, `users.created_at`,
whether a usable MTProto session exists, and which OAuth clients the user connected through
(`db.IdentityRow` / `Store.ListIdentities` in `internal/db/store.go:288-475`). That projection is
surfaced by the admin MCP tool `list_telegram_identities`
(`internal/mcp/tools.go:1054-1084`, gated on `admin:users` or `admin:users:read`) and consumed by the
daily new-client digest (`internal/digest/digest.go`). In practice the digest often prints
`(no username) — id …` because Telegram's OIDC `id_token` carries only `id`, `sub`, `username`,
`first_name` and `last_name` (`internal/auth/telegramoidc/oidc.go:198-204`), and because
`Store.EnsureUserByTelegramID` collapses an absent username into the display name
(`internal/db/store.go:191-194`), leaving no way to tell "Telegram supplied no @handle" from
"we never captured anything".

Issue #438 asks to extend that existing projection — not to build a second customer directory — with
(a) richer, provenance-tagged Telegram identity attributes, (b) an explicit model of whether the login
bot may currently initiate a chat with the client, modelled separately from OAuth authentication and
MTProto session state, and (c) category-level notification preferences with timestamp and source, with
a self-service surface in the existing account-management pages. This matters because today the only
outbound bot path in the codebase — `digest.sendTelegramMessage` — treats a delivery failure as a
log line and forgets it, and because there is no record anywhere of a user's consent to receive
product communication.

## User stories

- AS a platform operator I WANT the admin identity view to show a client's username, first/last name,
  language and when each attribute was captured SO THAT I can tell who a new client is without
  guessing from `(no username) — id …`.
- AS a platform operator I WANT missing attributes to carry an explicit provenance value SO THAT I can
  distinguish "Telegram never supplied this" from "capture or backfill has not run for this row".
- AS a platform operator I WANT the bot's reachability for a client recorded as `unknown`, `reachable`,
  `blocked` or `cannot_initiate` SO THAT I know whether a product notification could ever be delivered,
  independently of the client holding a valid OAuth token or MTProto session.
- AS a connected client I WANT to see and change my notification preferences per category on
  `/telegram/connect/manage` SO THAT I control whether I receive product updates.
- AS a privacy reviewer I WANT product-update consent to be an explicit, timestamped, source-attributed
  choice, and operational/security notices to be classified separately SO THAT an operational message is
  never retroactively treated as marketing consent.
- AS a client who deletes their account I WANT my notification preferences and reachability state removed
  SO THAT no consent record survives the deletion contract.

## Acceptance criteria (EARS)

### Migration and backward compatibility

- WHEN `db.Migrate` runs against an existing database THE SYSTEM SHALL add the new identity columns and
  the new notification tables additively, via `addColumnIfMissing` and `CREATE TABLE IF NOT EXISTS`
  on both the Postgres and SQLite branches, without rewriting any existing `users`,
  `telegram_accounts`, `oauth_refresh_tokens` or `oauth_client_registrations` row.
- WHILE the migration runs THE SYSTEM SHALL leave `users.access_tier`, `users.telegram_username`,
  `users.telegram_display_name` and every session/OAuth column byte-identical to their pre-migration
  values.
- THE SYSTEM SHALL NOT add any column to `audit_logs`, because a non-NULL default there retroactively
  changes the canonical hash input of older rows and makes `Store.VerifyAuditChain` report the whole
  chain as tampered (see the `call_path` comment at `internal/db/db.go:127-137`).
- WHEN `db.Migrate` runs THE SYSTEM SHALL backfill `users.onboarding_completed_at` from the earliest
  non-revoked, finalised `telegram_accounts.connected_at` for that user, using the same idempotent
  in-`Migrate` backfill pattern already used for `last_used_at`/`expires_at`
  (`internal/db/db.go:246-278`).

### Identity capture and provenance

- WHEN a Telegram OIDC login completes and `internal/oauth/server.go:1597` binds the identity, THE
  SYSTEM SHALL persist `username`, `first_name` and `last_name` into their own columns, set
  `identity_captured_at` to the capture time and `identity_source` to `telegram_oidc`.
- WHEN a Local Bridge activation completes (`internal/oauth/local_bridge_activate.go:1038`) THE SYSTEM
  SHALL perform the same capture with `identity_source` set to `local_bridge_activation`.
- IF Telegram supplies no value for an attribute THEN THE SYSTEM SHALL store the empty value and leave
  `identity_captured_at` set, so the attribute reads as "not supplied by Telegram".
- IF `identity_captured_at` is NULL THEN THE SYSTEM SHALL report the row's identity provenance as
  `unknown`, meaning capture has never run for it, and SHALL NOT present its empty attributes as
  "Telegram did not supply this".
- WHEN `db.Migrate` backfills a pre-existing row THE SYSTEM SHALL set `identity_source` to
  `backfill_legacy` and SHALL NOT split `telegram_display_name` into first/last name, because the
  existing column may already hold a username-fallback value written by the current
  `EnsureUserByTelegramID` behaviour.
- THE SYSTEM SHALL NOT derive any identity attribute from message content, dialog titles or any
  MTProto read path.
- WHILE no verified source for `language_code` exists THE SYSTEM SHALL leave
  `users.telegram_language_code` empty and report it as not supplied; the OIDC `id_token` claim set
  (`internal/auth/telegramoidc/oidc.go:198-204`) has no `language_code`, and the only `LangCode` in the
  repo is the hardcoded `"en"` in this service's own client config
  (`internal/telegram/login.go:123-124`), which is not the user's language.
- WHEN a client re-authenticates THE SYSTEM SHALL refresh the captured attributes and advance
  `users.last_seen_at`.

### Bot reachability

- THE SYSTEM SHALL model bot reachability as exactly one of `unknown`, `reachable`, `blocked`,
  `cannot_initiate`, stored separately from `users.access_tier`, from OAuth refresh-token state and
  from `telegram_accounts` session state.
- WHEN a user row is first created THE SYSTEM SHALL treat reachability as `unknown`.
- WHILE a client holds a valid OAuth token and an active MTProto session THE SYSTEM SHALL still report
  reachability `unknown` until a real bot interaction or delivery result is observed.
- WHEN a bot `sendMessage` to a chat returns HTTP 200 THE SYSTEM SHALL record reachability `reachable`
  with the observation time and source.
- WHEN a bot `sendMessage` returns HTTP 403 whose description indicates the bot was blocked or the user
  is deactivated THE SYSTEM SHALL record reachability `blocked`.
- WHEN a bot `sendMessage` returns HTTP 400 `chat not found` THE SYSTEM SHALL record reachability
  `cannot_initiate`.
- IF a bot `sendMessage` fails with a transport error, a 429, or any 5xx THEN THE SYSTEM SHALL leave the
  stored reachability state unchanged and record only that an attempt failed.
- THE SYSTEM SHALL NOT issue any Telegram request whose sole purpose is to classify reachability.
- WHEN reachability is recorded THE SYSTEM SHALL store a normalised reason code only, never the raw
  Telegram response body and never the bot token.

### Notification preferences

- THE SYSTEM SHALL store preferences per `(user_id, category)` for the categories `product_updates`,
  `maintenance` and `security`, each with a state, a `decided_at` timestamp and a `source`.
- IF no explicit row exists for `product_updates` THEN THE SYSTEM SHALL resolve it to `unsubscribed`
  and mark it as not explicitly decided.
- IF no explicit row exists for `maintenance` or `security` THEN THE SYSTEM SHALL resolve it to
  `subscribed` and mark it as not explicitly decided, and SHALL classify it as an operational notice
  rather than marketing consent.
- WHEN a client submits a preference change THE SYSTEM SHALL write `decided_at` and a `source`
  identifying the surface that produced the change, and SHALL mark the category as explicitly decided.
- WHEN an authenticated client calls `GET /api/account/notifications` THE SYSTEM SHALL return every
  category with its resolved state, whether it was explicitly decided, its `source` and its `decided_at`.
- WHEN an authenticated client calls `PUT /api/account/notifications` THE SYSTEM SHALL apply only the
  categories present in the request body and leave the others untouched.
- IF a request carries an unknown category or an unknown state THEN THE SYSTEM SHALL reject it with
  HTTP 400 and change nothing.
- IF a request is unauthenticated THEN THE SYSTEM SHALL return HTTP 401, matching the existing
  `AccountHandlers` behaviour.
- WHILE a client is viewing `/telegram/connect/manage` THE SYSTEM SHALL render the three categories with
  their current state and allow changing them, in the same way the existing `send_enabled` toggle works.
- THE SYSTEM SHALL NOT let a notification preference confer any Telegram, MCP or admin scope; scope
  resolution SHALL remain driven solely by `users.access_tier` and the auth provider.

### Admin projection

- WHEN `list_telegram_identities` is called with `admin:users` or `admin:users:read` THE SYSTEM SHALL
  additionally return, per identity: first name, last name, language code, identity provenance and
  capture time, last seen, onboarding completion time, bot reachability with its observation time and
  source, and the resolved notification preferences.
- IF the caller holds neither `admin:users` nor `admin:users:read` THEN THE SYSTEM SHALL return the
  existing scope error and no data.
- WHILE building the projection THE SYSTEM SHALL use bounded batch queries merged in memory, following
  the existing `connected_via` merge in `Store.ListIdentities`, and SHALL NOT issue a per-user query.
- THE SYSTEM SHALL keep every added JSON field optional so existing consumers of the tool's output
  continue to parse it.

### Deletion, retention and logging

- WHEN `Store.HardDeleteAccount` runs THE SYSTEM SHALL delete that user's notification preference rows
  and reachability row inside the same transaction, alongside the existing `purgeAgentData` call
  (`internal/db/store.go:798-805`).
- WHEN an account is disconnected via `Store.RevokeActiveSession` THE SYSTEM SHALL leave notification
  preferences unchanged, because a disconnect is not a deletion.
- THE SYSTEM SHALL NOT log message bodies, phone numbers, session material, OAuth tokens or the bot
  token on any new code path.
- THE SYSTEM SHALL NOT log first name, last name, display name or username; any new sensitive attribute
  name SHALL be registered in `audit.sensitiveKeys` (`internal/audit/redact.go:30-70`).
- WHEN a notification preference change is audited THE SYSTEM SHALL record only the category, the new
  state and the source, never free-text supplied by the user.

## Out of scope

- Sending product broadcasts, newsletters or any campaign machinery. This proposal records consent and
  reachability; it does not add a sender.
- AI-generated announcement copy.
- Re-implementing or replacing the scoped admin identity lookup from mctlhq/mctl-telegram#400.
- Bot commands `/subscribe`, `/unsubscribe`, `/settings`. The login bot has no update receiver today:
  the only Telegram Bot API call anywhere in the repo is the outbound
  `digest.sendTelegramMessage` POST to `sendMessage` (`internal/digest/digest.go:147`), and there is no
  `getUpdates` poller or webhook handler for it. Issue #438 permits these commands only if the bot
  "already has or deliberately gains a safe update receiver"; gaining one is a separate security
  surface and a separate proposal.
- Treating every authenticated user as messageable.
- Multi-bot reachability. A single login bot is assumed.
- Changing the existing `effectiveUsername` fallback in `Store.EnsureUserByTelegramID` for historical
  rows. New captures write the dedicated columns; the legacy column values are left untouched.

## Open questions

- Should a client be able to unsubscribe from `security`? This proposal stores a preference for all
  three categories and classifies `security` as operational, but leaves the enforcement decision to the
  future sender. Reasonable interpretation adopted: `maintenance` is suppressible, `security` is
  recorded but expected to be non-suppressible by operator policy.
- Is it acceptable to read `tg.User.LangCode` from a client's own finalised MTProto session to populate
  `telegram_language_code`? It is verified, first-party data and not message content, but it is a new
  read of the user's session. This proposal does not do it and leaves the column empty with provenance;
  a reviewer may enable it as a follow-up.
- Does "onboarding completion time" mean the first finalised `telegram_accounts` row (adopted here) or
  completion of the OAuth grant? The two differ for Local Bridge activations.
- Should the daily digest be changed to display reachability, or is that a separate change? This
  proposal only records reachability from the digest's delivery results and adds it to the admin
  projection; the digest text itself is left alone apart from that.
- Should account deletion hard-delete notification state, or retain an anonymised consent tombstone for
  compliance evidence? This proposal hard-deletes, matching the existing `purgeAgentData` contract.
