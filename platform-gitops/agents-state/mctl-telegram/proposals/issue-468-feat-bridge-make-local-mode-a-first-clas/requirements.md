# Make local-mode a first-class account, not a flag on a hosted row

## Context

Local Bridge (M4) lets a user run MTProto on their own machine instead of trusting
`mctl-telegram`'s server-side session, with `tg.mctl.ai` reduced to a relay. Whether an
account uses this path is recorded in `telegram_accounts.mode` (`'hosted'` | `'local'`),
but that column sits on the same row that also carries the hosted session:
`session_encrypted BLOB NOT NULL` (`internal/db/db.go:301` SQLite, `:361` Postgres), and
`GetAccountMode` (`internal/db/store.go:1118-1133`) only looks at rows where
`revoked_at IS NULL`. The result is that "local" is not really a kind of account — it is a
temporary state of a hosted row, and every operation that touches that row's `revoked_at`
(the idle/absolute TTL sweepers, `disconnect_telegram_account`) can silently flip the
account back to `hosted` with no error and no log line, at which point `NewBridgeHandler`
(`internal/bridge/server.go:65-75`) starts rejecting the user's daemon with HTTP 400.

This matters because it makes local mode strictly worse than advertised in two concrete
ways verified against the code: (1) an account can never be *created* as local-only — a
hosted login (which requires `session_encrypted`) must happen first, contradicting the
stated goal of a server that never holds the session; and (2) `/security`
(`internal/web/security.html:121`, corrected in this pass) previously claimed
`session_encrypted` is `NULL` for local-mode accounts when the column forbids `NULL`
entirely, so the privacy promise a user is switching modes to get was never actually true.
The fix makes local a first-class row state (its own provisioning path, no server session,
immune to session-TTL sweeping by construction) instead of a derived, fragile flag.

## User stories

- AS a privacy-conscious user I WANT to have a Local Bridge account provisioned directly,
  without ever completing a hosted login, SO THAT the server never holds a copy of my
  Telegram session.
- AS an operator I WANT the idle-session sweeper to leave local-mode accounts alone by
  construction (a property of the row, not a deploy-time allowlist) SO THAT
  `SESSION_TTL_EXEMPT_TG_IDS` is not required to keep Local Bridge users connected, and
  adding a Local Bridge user does not require a GitOps PR and a pod restart.
- AS a user who migrated an existing hosted account to local mode I WANT revoking my
  server-held session to not silently revert my account to hosted mode SO THAT my bridge
  keeps working even after I have taken the step the product recommends for reducing what
  the server holds.
- AS a reader of `/security` I WANT the stated claim about local-mode session storage to be
  literally true for the accounts it describes SO THAT the security page is not making a
  promise the schema cannot keep.

## Acceptance criteria (EARS)

- WHEN an admin provisions a local-mode account for a Telegram id that has never completed
  a hosted login THE SYSTEM SHALL create a `telegram_accounts` row with `mode = 'local'`
  and `session_encrypted = NULL`, without requiring any prior hosted session.
- WHEN a Local Bridge daemon registers on `/bridge` for an account provisioned this way
  THE SYSTEM SHALL accept the connection and serve tool calls with `call_path = 'local'` in
  `audit_logs`, identically to a migrated (`set_account_mode`) local account.
- WHILE `telegram_accounts.mode = 'local'` for a row THE SYSTEM SHALL exclude that row from
  `SweepIdleSessions`, regardless of whether the Telegram id appears in
  `SESSION_TTL_EXEMPT_TG_IDS`.
- WHEN `SweepIdleSessions` runs against a local-mode account whose `last_used_at` is older
  than the idle TTL and `SESSION_TTL_EXEMPT_TG_IDS` is unset THE SYSTEM SHALL NOT revoke
  that account's row.
- WHEN the hosted session of a `telegram_accounts` row is revoked (idle expiry, absolute
  expiry, or explicit disconnect) WHILE that row's `mode = 'local'` THE SYSTEM SHALL
  continue to report `GetAccountMode = 'local'` for that account, and `/bridge` SHALL
  continue to accept that account's daemon.
- IF `session_encrypted` is `NULL` for a row THEN THE SYSTEM SHALL treat that row as having
  no server-side hosted session (no decrypt attempt, no hosted dispatch), without error.
- WHEN `set_account_mode` is called with `mode = "local"` for a telegram id THE SYSTEM
  SHALL NOT require that id to be present in `SESSION_TTL_EXEMPT_TG_IDS` (the refusal
  existed only to patch the sweeper coupling this proposal removes).
- WHEN a test changes the `SweepIdleSessions` predicate to also revoke local-mode accounts
  THE SYSTEM's test suite SHALL fail (mutation coverage on the sweeper predicate, not just
  a happy-path "hosted accounts still get swept" assertion).
- IF an admin attempts to provision a local-mode account for a Telegram id that already has
  an active `telegram_accounts` row THEN THE SYSTEM SHALL refuse and point at
  `set_account_mode` as the correct operation for migrating an existing account.
- WHEN `/security` and `internal/bridge/DESIGN.md` describe local-mode session storage
  THE SYSTEM's documentation SHALL state plainly that "no server-side session" is true for
  accounts provisioned as local from the start, and that a sealed blob still exists for
  accounts migrated from hosted via `set_account_mode` (until that blob is separately
  cleared, which is out of scope here).

## Out of scope

- Retiring `set_account_mode` itself. Migrating an existing hosted account to local mode
  is a distinct, still-needed operation from provisioning a fresh local account.
- Clearing/deleting the `session_encrypted` blob of accounts already migrated to local
  mode via `set_account_mode`. The bridge does not read it today; whether it is safe to
  null it out is a separate question the issue defers, and this proposal only makes the
  column nullable and stops new local-only accounts from ever populating it.
- Any change to the daemon (`cmd/local`). This is entirely server-side (schema, store,
  sweeper, admin tool, docs).
- Fully retiring `SESSION_TTL_EXEMPT_TG_IDS` as a feature. It also exempts long-lived
  operator/service identities that stay in hosted mode
  (`internal/config/config.go:133-137`) — that is a legitimate, separate use this proposal
  does not touch. This proposal only removes the requirement that local-mode Telegram ids
  be listed on it.
- Changing how `revoked_at` gates hosted-session freshness for `Pool.Borrow` /
  `CheckSessionValid`. Those remain scoped to the hosted dispatch path; local dispatch
  never calls them (`internal/mcp/tools.go` checks `GetAccountMode` and calls `bridgeCall`
  directly, bypassing `Pool.Borrow`).
- `bridge_token_hash` wiring — flagged as dead schema in `internal/bridge/DESIGN.md` but
  unrelated to this issue.

## Open questions

- Should `disconnect_telegram_account` / `POST /api/account/disconnect` fully disable
  bridge access for a local-mode account (i.e. flip `mode` back to something inert), or is
  "session revoked, mode still local, bridge still accepts the daemon" the intended
  end state per acceptance criterion 4? The issue's own "not in scope" section defers
  settling full revocation semantics, so this proposal implements the literal acceptance
  criterion (mode survives revocation) and leaves the disconnect-tool UX question for a
  follow-up. Proceeding with: revocation of the session never changes `mode`.
- Should `SweepAbsoluteSessions` (90-day absolute TTL) also skip `mode = 'local'` rows, or
  only `SweepIdleSessions` as the issue's reproduction steps describe? A migrated account
  keeps its original `expires_at` from its hosted `SaveSession` call, so the absolute
  sweep could still revoke it later even after this fix. Proceeding with: apply the same
  `mode <> 'local'` exclusion to both sweeps for consistency with "the exemption becomes a
  property of the data," and note it explicitly in the PR description since the issue only
  names the idle sweep in its acceptance criteria.
- Exact admin-tool name/shape for provisioning (`provision_local_account` used throughout
  this proposal) is not specified by the issue. Proceeding with an MCP tool mirroring
  `set_account_mode`'s admin-scope pattern (`admin:users`), auditable, refusing if an
  active row already exists for the target Telegram id.
- Whether provisioning should also accept/require `display_name`/`username` up front, or
  leave them empty until the daemon's first successful call populates them. Proceeding
  with: optional at provision time, since nothing today updates them post-connect for a
  bridge-only account and getting them wrong is cosmetic, not a correctness issue.
