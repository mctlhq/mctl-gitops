# Client identity attributes and provenance

## Context

`mctl-telegram` already keeps a thin identity projection on the `users` table:
`telegram_login_id`, `telegram_username`, `telegram_display_name`, `access_tier`
and `created_at` (see `internal/db/db.go` `Migrate`, columns added via
`addColumnIfMissing`). `Store.ListIdentities` (`internal/db/store.go:403`) renders
that projection for the admin tool `list_telegram_identities`
(`internal/mcp/tools.go:1052`), enriched with `has_session` and `connected_via`,
and `Store.GetLoginIdentity` (`internal/db/store.go:353`) backs the self-service
`get_my_identity` tool (`internal/mcp/tools.go:953`). The verified OIDC id_token
already carries more than the projection keeps: `telegramoidc.Identity`
(`internal/auth/telegramoidc/oidc.go`) parses `username`, `first_name` and
`last_name`, and the OAuth callback (`internal/oauth/server.go:1597`) immediately
flattens first and last name into a single `display_name` string before calling
`Store.EnsureUserByTelegramID`. The separate components are then unrecoverable.

Worse, the projection cannot explain a blank field. `get_my_identity`'s own
description already promises that "username and display_name are omitted when
they were never captured — Telegram did not supply them, or the row predates
capture", but nothing in the schema distinguishes those two cases: both render
as an empty string. This proposal keeps the remaining verified identity
attributes (first name, last name, language code, onboarding completion, last
seen) and attaches an explicit per-attribute provenance so a missing value is
explainable rather than merely absent. It is the first slice of #438 and touches
neither reachability (slice 2) nor preferences (slice 3).

## User stories

- AS a platform operator I WANT `list_telegram_identities` to show each client's
  first name, last name, language code, first seen, last seen and onboarding
  completion time SO THAT I can identify and support a signed-in client without
  reading their messages or asking them for the data again.
- AS a platform operator I WANT every missing identity attribute to carry an
  explicit status SO THAT I can tell "Telegram never supplied this" from "this
  row predates attribute capture" and know whether re-authenticating the user
  would help.
- AS an authenticated client I WANT `get_my_identity` to return the same
  attributes and the same provenance about me SO THAT the transparency promise
  already written into the tool description is actually kept.
- AS a reviewer of this service I WANT the new attributes to never be inferred
  from message content and never to reach logs or audit rows SO THAT extending
  the projection does not widen the data-handling surface.

## Acceptance criteria (EARS)

- WHEN a user completes the Telegram OIDC flow and `internal/oauth/server.go`
  binds the identity, THE SYSTEM SHALL persist the verified `username`,
  `first_name` and `last_name` claims into their own `users` columns, in
  addition to the existing composed `telegram_display_name`.
- WHEN identity capture runs for a user, THE SYSTEM SHALL stamp
  `users.identity_captured_at` even if Telegram supplied no optional attribute
  at all.
- WHEN a hosted MTProto login finalises via `telegram.Login` /
  `telegram.LoginQR` and the resulting Telegram id matches the id the flow
  expected, THE SYSTEM SHALL capture the self-user's language code when Telegram
  populates it, and SHALL leave the column NULL otherwise.
- WHEN `list_telegram_identities` is called with the `admin:users` or
  `admin:users:read` scope, THE SYSTEM SHALL include `first_name`, `last_name`,
  `language_code`, `last_seen_at`, `onboarding_completed_at` and a `provenance`
  object alongside the fields it returns today.
- WHEN `get_my_identity` is called by an authenticated session, THE SYSTEM SHALL
  return the same attribute set and the same `provenance` object for the caller
  only, with no admin scope required.
- WHILE a `users` row has `identity_captured_at IS NULL`, THE SYSTEM SHALL report
  provenance `not_captured` for every optional identity attribute of that row.
- WHILE a `users` row has `identity_captured_at` set, THE SYSTEM SHALL report
  provenance `verified` for each non-empty captured attribute and `not_supplied`
  for each empty one.
- WHILE an attribute is computed from another verified server-side record rather
  than from a Telegram-supplied value, THE SYSTEM SHALL report its provenance as
  `derived`.
- IF a user has at least one finalised `telegram_accounts` row
  (`telegram_user_id IS NOT NULL`), THEN THE SYSTEM SHALL report
  `onboarding_completed_at` as the earliest such row's `connected_at`.
- IF a user has no finalised `telegram_accounts` row, THEN THE SYSTEM SHALL omit
  `onboarding_completed_at` and report its provenance as `not_captured`.
- IF a user has activity records (`telegram_accounts.last_used_at` or
  `oauth_refresh_tokens.created_at`), THEN THE SYSTEM SHALL report `last_seen_at`
  as the most recent of them with provenance `derived`.
- WHEN `Migrate` runs against a database that already holds `users` and
  `telegram_accounts` rows, THE SYSTEM SHALL add the new columns without
  altering any row's `access_tier`, `telegram_login_id`, session state or
  `oauth_refresh_tokens` linkage.
- WHEN `Migrate` runs, THE SYSTEM SHALL backfill `users.onboarding_completed_at`
  from the earliest finalised `telegram_accounts.connected_at` for rows where it
  is still NULL, and SHALL be idempotent across repeated runs.
- WHILE backfilling, THE SYSTEM SHALL NOT derive `first_name` or `last_name` by
  splitting `telegram_display_name`, and SHALL NOT derive any name from message
  content; such rows stay `not_captured` until the user next authenticates.
- IF the `telegram_first_name`, `telegram_last_name` or `telegram_language_code`
  values are handled anywhere in the process, THEN THE SYSTEM SHALL NOT write
  them to `slog` output or to `audit_logs` rows.

## Out of scope

- Bot reachability state and the "can the bot message this user" question
  (#438 slice 2).
- Notification preferences and per-user settings (#438 slice 3).
- Deletion semantics beyond what `HardDeleteAccount` already does.
- Any new user-directory table or endpoint separate from the existing `users`
  projection; `mctlhq/mctl-telegram#400`'s admin lookup is not duplicated.
- Changing `users.telegram_display_name` semantics or removing the composed
  value; it stays as the compatible display string.
- Photo URL, phone number, or any attribute Telegram's `profile` scope does not
  deliver to this relying party.

## Open questions

- Does Telegram's OIDC `profile` scope ever deliver a `language_code` claim?
  `idTokenClaims` in `internal/auth/telegramoidc/oidc.go` does not request or
  parse one today, and spike #48 only recorded `id`, `sub`, `username`,
  `first_name`, `last_name`. Reasonable interpretation taken here: add the claim
  field so it is captured if Telegram ever sends it, and otherwise source the
  language code from the MTProto self-user during hosted login. If neither
  source populates it the column stays NULL and reads as `not_supplied`, which
  is a correct answer, not a bug.
- `tg.User.LangCode` is flag-gated in MTProto and may never be set for a regular
  user account. If it is not, the language-code attribute is permanently
  `not_supplied` for every identity. Interpretation: ship the column and the
  provenance anyway — the issue asks for "language code where available", and
  the provenance value is what makes the absence explainable.
- "Last seen" could mean last MCP tool call rather than last session use or token
  issuance. Interpretation taken: derive it from `telegram_accounts.last_used_at`
  and `oauth_refresh_tokens.created_at`, both of which already exist, rather than
  add a write to a hot path. The provenance value `derived` makes this visible.
- Legacy rows whose `telegram_display_name` is set but whose first/last name are
  unknown will read as `not_captured` and only heal on the user's next sign-in.
  This is deliberate (splitting the composed name is inference) but means the
  admin view stays partially blank for dormant accounts.
