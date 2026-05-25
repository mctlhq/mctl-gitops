# Canonicalize client tier in DB after enable_access completes

## Context

`tg.mctl.ai` runs with `AUTO_APPROVE_CLIENTS=true`, which lets any
Telegram-authenticated user self-register without an explicit admin
`set_telegram_access` call. Scope resolution (`ResolveScopes` /
`isClientTier` in `internal/oauth/server.go`) grants the client tier at
runtime solely from that flag when `users.access_tier` is NULL. No DB write
records that the user actually completed the MTProto login flow.

This is fragile: toggling `AUTO_APPROVE_CLIENTS=false` to pause new
registrations silently strips access from every self-registered user who
never had an explicit DB row, because the runtime flag is the only grant
they hold. Making the DB record authoritative — by writing `access_tier =
'client'` at the moment `finishEnable` completes — decouples existing users
from the flag and makes the registration durable.

## User stories

- AS an operator I WANT existing self-registered users to keep access when I
  set `AUTO_APPROVE_CLIENTS=false` SO THAT I can stop accepting new
  registrations without revoking access for current users.
- AS an operator I WANT the DB to be the authoritative record of who
  completed the enable_access flow SO THAT I can inspect
  `users.access_tier` to audit or bulk-manage registrations.
- AS a self-registered user I WANT my access to be independent of the
  `AUTO_APPROVE_CLIENTS` runtime flag SO THAT my connection is not silently
  broken by an operator config change.

## Acceptance criteria (EARS)

- WHEN a non-admin user successfully completes the enable_access flow
  (phone, SMS code, optional 2FA) THE SYSTEM SHALL write
  `access_tier = 'client'` to `users.access_tier` for that user's
  `telegram_login_id` before issuing the authorization code.
- WHEN `store.SetAccessTier` returns an error THE SYSTEM SHALL log the
  error at `slog.Error` level with fields `uid` and `err` AND SHALL
  continue to issue the authorization code (non-fatal).
- WHILE a user's `users.access_tier` is `'client'` (DB row) THE SYSTEM
  SHALL grant client-tier scopes regardless of the value of the
  `AUTO_APPROVE_CLIENTS` flag (existing behaviour of `isClientTier`
  unchanged).
- IF the completing user's Telegram ID is present in
  `cfg.AdminTelegramIDs` THEN THE SYSTEM SHALL NOT call `SetAccessTier`
  (admin tier is governed by the env allowlist, not the DB column).
- WHEN `SetAccessTier` succeeds for a user who already had
  `access_tier = 'client'` THE SYSTEM SHALL treat the write as an
  idempotent no-op (the UPDATE is already idempotent by design in
  `internal/db/store.go`).

## Out of scope

- Backfilling `access_tier` for users who completed enable_access before
  this change is deployed. A separate one-off migration is out of scope;
  those users continue to rely on `AUTO_APPROVE_CLIENTS` until the flag is
  changed.
- Any change to `ResolveScopes` / `isClientTier` logic. The existing
  DB-first, env-fallback ordering already handles a written `TierClient`
  row correctly.
- Any change to the admin MCP tool `set_telegram_access`. That tool
  already writes `access_tier` directly and is unaffected.
- Changing the behaviour for users who abandon the enable_access flow
  mid-way (no `finishEnable` call, so no DB write).

## Open questions

None. The issue is fully specified. The only interpretive choice — log and
continue vs. hard-fail on `SetAccessTier` error — is explicitly stated in
the issue body and in the acceptance criteria above (non-fatal, log and
continue).
