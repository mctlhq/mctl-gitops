# Local Bridge device registry and an optional device_id claim

## Context

Local Bridge (M4, documented in `internal/bridge/DESIGN.md`) lets a user run
the Telegram MTProto session on their own machine via `cmd/local` while
`tg.mctl.ai` acts as a relay. Today a `telegram_accounts` row supports at
most one live daemon connection: `mode='local'` is a single flag on the
account, `bridge_token_hash` exists in the schema but is never written
(`internal/bridge/DESIGN.md`, "Correctness gaps" item 3), and there is no
concept of an individual daemon installation distinct from the account
itself. `internal/bridge/hub.go` already enforces a singleton-per-user
websocket registration in memory, but nothing durable identifies *which*
daemon that connection belongs to, so a reconnecting daemon, a second
machine, or a revoked-and-reissued installation are all indistinguishable
at the data layer.

This issue (#481, sub-issue 1 of 4 splitting #479) lays the foundation the
other three sub-issues build on: activation endpoints, consent changes, and
credential issuance/refresh/CLI/docs. It is deliberately additive — a new
table and an optional JWT claim — and must not change any existing
behaviour. It inherits tasks 1-2 of the retired #479 proposal
(`requirements.md`/`design.md`/`tasks.md` under
`mctl-gitops/platform-gitops/agents-state/mctl-telegram/proposals/issue-479-feat-local-bridge-make-onboarding-fully/`,
which remains the contract for those two tasks; that proposal itself is
`rejected` in favour of these four issues).

## User stories

- AS the Local Bridge system I WANT a durable per-daemon device record SO
  THAT a later sub-issue can distinguish, register, and revoke individual
  daemon installations instead of only flipping one account-wide mode flag.
- AS a platform operator I WANT device rows to be lookup-able and
  revocable through `Store` methods SO THAT a later admin surface (activation
  endpoints, consent UI) can be built without touching schema again.
- AS the JWT layer I WANT an optional `device_id` claim on `localjwt.Claims`
  SO THAT a future credential can be scoped to one device while every
  existing token (which carries no such claim) keeps verifying unchanged.

## Acceptance criteria (EARS)

- WHEN `db.Migrate` runs against a fresh SQLite database THE SYSTEM SHALL
  create a `local_bridge_devices` table via `sqliteSchema()`.
- WHEN `db.Migrate` runs against a fresh Postgres database THE SYSTEM SHALL
  create a `local_bridge_devices` table via `pgSchema()`.
- WHEN `db.Migrate` runs against a database that already has the
  `local_bridge_devices` table THE SYSTEM SHALL leave it unchanged
  (idempotent, `CREATE TABLE IF NOT EXISTS`).
- WHEN a `Store` method registers a new device for a user THE SYSTEM SHALL
  insert a row and return an identifier usable for later lookup/revoke.
- WHEN a device is registered twice with the same idempotency key (e.g. the
  same daemon retries a registration call after a network timeout) THE
  SYSTEM SHALL return the existing row rather than creating a duplicate.
- WHEN a `Store` method looks up a device by its identifier THE SYSTEM SHALL
  return the device's current state, including whether it is revoked.
- WHEN a `Store` method revokes a device THE SYSTEM SHALL record a
  revocation timestamp and reason without deleting the row.
- WHEN a `Store` method updates a device's last-seen timestamp THE SYSTEM
  SHALL persist it so future sub-issues can build staleness/idle logic on
  top of it.
- WHEN `localjwt.Issuer.Mint` is called with `Claims.DeviceID` set THE
  SYSTEM SHALL include a `device_id` claim in the signed token.
- WHEN `localjwt.Issuer.Mint` is called with `Claims.DeviceID` empty THE
  SYSTEM SHALL omit the `device_id` claim from the token body (`omitempty`).
- WHEN `localjwt.Verify` decodes a token that carries a `device_id` claim
  THE SYSTEM SHALL populate `Claims.DeviceID` with that value.
- WHEN `localjwt.Verify` decodes a legacy token minted before this claim
  existed (no `device_id` field in the payload) THE SYSTEM SHALL verify it
  exactly as before, with `Claims.DeviceID` left as the empty string.
- WHILE this issue is the only one merged THE SYSTEM SHALL NOT reject,
  require, or otherwise change behaviour based on `device_id` anywhere in
  `internal/bridge`, `internal/mcp`, or `internal/workertoken` — no caller
  is updated to set, check, or depend on it.
- IF a caller mints or verifies a token without ever setting `DeviceID`
  THEN THE SYSTEM SHALL behave identically to the pre-#481 code path (same
  signature input, same claim set, same verification outcome).

## Out of scope

- Any HTTP/MCP endpoint for a user or daemon to register, list, or revoke a
  device (that is a follow-up sub-issue).
- Any change to the Local Bridge consent flow or UI.
- Issuing device-scoped credentials, or refreshing/rotating them.
- The `cmd/local` CLI and `docs/local-bridge.md` documentation.
- Wiring `device_id` into `internal/bridge/server.go`'s websocket
  registration, `internal/bridge/hub.go`'s singleton-per-user logic, or
  `needsRevocationCheck`/`RevocationCache` in `internal/auth/localjwt`.
- Fixing the pre-existing, unrelated `bridge_token_hash` dead-schema gap
  noted in `internal/bridge/DESIGN.md` ("Correctness gaps" item 3) — this
  issue adds a new, separate table rather than resurrecting that column.
- Enforcing a maximum number of devices per user.

## Open questions

- Exact column set for `local_bridge_devices` beyond what the issue and
  `DESIGN.md` imply (id, user reference, a public device identifier, a
  human-readable label, registered-at, last-seen-at, revoked-at,
  revoked-reason). The issue does not enumerate columns; this proposal
  designs a minimal set sufficient for register/lookup/revoke/last-seen and
  leaves room for follow-up sub-issues to add columns additively via
  `addColumnIfMissing`, the pattern already used throughout `db.go`.
- Whether `device_id` (the JWT claim) is meant to be the same value as the
  device registry's primary/public identifier, or an independent string.
  This proposal treats them as the same namespace (the registry's public
  device identifier is what a future sub-issue would place in the claim)
  since the issue groups them in one sub-issue, but does not add any code
  that couples them yet — that wiring is explicitly out of scope here.
- Whether device identifiers should be server-generated (UUID) or
  client-supplied (daemon generates its own and registers it). This
  proposal assumes server-generated, matching how `oauth_refresh_tokens`
  and `worker_token_revocations` generate their own ids/hashes rather than
  trusting a client-supplied value, and defers any client-supplied-id
  variant to the sub-issue that adds the registration endpoint.
- Whether one user may have multiple *active* (non-revoked) devices
  simultaneously. The issue does not say. This proposal does not enforce a
  singleton at the DB layer (no unique-active-device index), matching how
  `telegram_accounts` similarly does not enforce single-active-session at
  the schema level, and leaving any such policy to the sub-issue that
  implements activation semantics.
