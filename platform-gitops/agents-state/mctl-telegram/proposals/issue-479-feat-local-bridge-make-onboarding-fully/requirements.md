# Local Bridge: fully self-service onboarding with zero required operator actions

## Context

`mctl-telegram` supports two Telegram deployment modes: "hosted" (the server
holds an encrypted MTProto session and talks to Telegram directly) and
"local" (Local Bridge — the MTProto session lives on the user's own machine
inside the `mctl-telegram-local` daemon, and `tg.mctl.ai` only relays MCP
tool calls to it over a websocket, `GET /bridge`). `internal/bridge/DESIGN.md`
and `docs/local-bridge.md` both document this mode candidly as "beta" and
list three operator-only actions that stand between a fresh user and a
working daemon:

1. `provision_local_account` (or `set_account_mode mode="local"` for an
   existing hosted account) — an admin-only MCP tool
   (`internal/mcp/tools.go:1088-1156`, requires `admin:users` scope) that
   creates the `telegram_accounts` row with `mode='local'`.
2. `POST /api/mcp/worker-token` with `purpose="local-bridge"`
   (`internal/workertoken/tokenhandler.go`) — an admin-only HTTP endpoint
   that hand-mints a 30-90 day bearer JWT the daemon exchanges for bridge
   tokens. There is no MCP tool for this; an operator makes the HTTP call by
   hand (`internal/bridge/DESIGN.md:143-150`).
3. `set_account_send` (`internal/mcp/tools.go:948-1005`) — an admin-only MCP
   tool that flips `telegram_accounts.send_enabled`, without which
   `send_message` returns a silent successful dry-run instead of sending.

The issue asks to remove all three from the mandatory path for a brand-new
user, while keeping every one of them available as an operator/support
mechanism, and without ever having the server hold an MTProto session for a
user who never asked for hosted mode. This matters because "beta, needs an
admin" is currently the single biggest adoption blocker for the mode the
project's own design doc identifies (`internal/bridge/DESIGN.md:120-167`,
"Remaining gaps... blocking a user, in the order a user hits them").

The codebase already has the two building blocks a self-service flow needs,
just not wired together for this purpose:

- **Proof of Telegram identity without an MTProto session.** `POST /oauth/telegram`
  drives `internal/auth/telegramoidc` (`internal/auth/telegramoidc/oidc.go`),
  an OIDC Relying Party against `https://oauth.telegram.org` that verifies a
  JWKS-signed `id_token` and yields a `TelegramID` the caller has proven
  ownership of — no MTProto, no server-side session. This is exactly the
  mechanism `internal/oauth/enable_access.go`'s browser wizard already uses
  before ever touching phone/SMS/2FA (`wantTgID` in `startLoginFlow`,
  `internal/oauth/enable_access.go:99-189`).
- **A precedent for self-service, per-user HTTP flows with no operator in the
  loop.** `internal/oauth/enable_access.go` is a complete, in-browser,
  admin-free flow (`ConnectClientID = "mctl_self_connect"`,
  `internal/oauth/server.go:446`) that already lets an authenticated Telegram
  user opt in or out of send permission via a checkbox
  (`stepPermissions`/`sendOptIn`, `internal/oauth/enable_access.go:257-292`)
  before finishing. It is the shape Workstream A and B should extend, not
  reinvent — it only currently drives a *hosted* login (phone/SMS/2FA), not
  a local one.

## User stories

- AS a fresh mctl-telegram user with no server-side account I WANT to
  install the local daemon, log in to Telegram locally, and activate Local
  Bridge myself SO THAT I never have to wait on or contact an operator to
  start using it.
- AS a privacy-conscious user I WANT my MTProto session to never leave my
  machine when I choose Local Bridge from the start SO THAT `tg.mctl.ai`
  never becomes a copy of my Telegram credentials.
- AS the account owner I WANT to explicitly and separately decide whether
  the daemon may send messages, and to revoke that later, SO THAT read-only
  use is the safe default and sending is an informed choice.
- AS a user running the daemon unattended I WANT it to renew its own
  short-lived credentials without me minting or copying a long-lived token
  SO THAT there is no permanent bearer secret sitting on disk.
- AS an operator I WANT device/account revocation to immediately and
  durably stop refresh and bridge connections for that device SO THAT a
  compromised or decommissioned client cannot keep working.
- AS an operator I WANT existing hand-provisioned Local Bridge accounts and
  hosted accounts to keep working unmodified SO THAT this change ships
  without a forced migration.

## Acceptance criteria (EARS)

- WHEN a Telegram id has no `telegram_accounts` row at all THE SYSTEM SHALL
  allow a self-service activation call, authenticated only by Telegram OIDC
  proof of that id plus a device public key, to create the row directly with
  `mode='local'` and `session_encrypted` left `NULL`.
- WHEN self-service activation succeeds THE SYSTEM SHALL NOT create, in that
  same flow, any hosted MTProto session or any temporary hosted/local
  intermediate account state.
- WHEN self-service activation is invoked again for the same owner, device
  public key, and Telegram id THE SYSTEM SHALL reconcile idempotently — no
  duplicate `telegram_accounts` row, no duplicate device-binding row — and
  return a usable credential rather than an error.
- IF a Telegram id already has an active `telegram_accounts` row in
  `mode='hosted'` THEN THE SYSTEM SHALL refuse to silently convert it to
  local mode via self-service activation and SHALL point the caller at the
  existing operator-mediated migration path (`set_account_mode`).
- WHEN self-service activation succeeds THE SYSTEM SHALL default
  `send_enabled=false` and SHALL require a separate, explicit owner action
  to set it `true`; no operator call to `set_account_send` shall be required
  for either state.
- WHEN the owner grants or revokes send consent THE SYSTEM SHALL record who
  granted it, when, and through which flow, in a form visible to
  `get_my_audit_log`/`GET /api/account/audit`.
- WHILE an activation has not granted send consent THE SYSTEM SHALL still
  permit a fully read-only activation and daemon connection to succeed.
- WHEN self-service activation succeeds THE SYSTEM SHALL automatically issue
  a Local Bridge access credential to the calling device, scoped to
  Local Bridge use, without an operator call to `POST /api/mcp/worker-token`.
- WHILE a device's issued Local Bridge access credential is valid THE SYSTEM
  SHALL keep its lifetime bounded to hours (not the existing 30-90 day
  worker-token range) and SHALL provide a refresh endpoint the daemon can
  call before expiry.
- WHEN a device calls the refresh endpoint THE SYSTEM SHALL require proof of
  possession of the device's bound private key (not bearer possession of the
  access credential alone) before issuing a new short-lived credential.
- IF a device or account is revoked THEN THE SYSTEM SHALL reject subsequent
  refresh calls for that device and SHALL cause the bridge (`GET /bridge`)
  to refuse or drop that device's connection.
- WHEN any credential is issued, refreshed, or revoked THE SYSTEM SHALL log
  an audit record of the outcome and SHALL NOT log the token/key material
  itself, consistent with `internal/audit/redact.go`'s existing redaction
  contract.
- WHERE an existing hand-minted `POST /api/mcp/worker-token` credential with
  `purpose="local-bridge"` is already in use THE SYSTEM SHALL continue to
  accept it against `POST /api/bridge/token` unchanged, for backward
  compatibility during the migration window.
- WHERE an account is `mode='hosted'` THE SYSTEM SHALL continue to support
  existing hosted login and the existing hosted-to-local `set_account_mode`
  migration path unchanged.
- IF an unauthenticated or OIDC-unproven caller attempts self-service
  activation for a Telegram id THEN THE SYSTEM SHALL refuse it; activation
  authority comes only from the OIDC-proven identity of the caller, never
  from a caller-supplied `telegram_id` parameter.

## Out of scope

- Removing or renaming `provision_local_account`, `set_account_mode`, or
  `set_account_send` — they remain as operator/support/recovery tools
  (explicitly required by the issue's "Backward compatibility" and
  "Non-goals" sections).
- Changing the public MCP endpoint or the bridge websocket transport
  protocol (`internal/bridge/protocol.go`).
- Adding always-on hosted-listener parity for local accounts (explicitly a
  known, separate gap in `internal/bridge/DESIGN.md`).
- Implementing the five tools that remain unsupported in local mode
  (`edit_message`, `delete_messages`, `forward_messages`, `search_messages`,
  `set_reaction`).
- Signing the released `mctl-telegram-local` binaries (tracked separately,
  per `internal/bridge/DESIGN.md`'s "No released binary" note).
- Building a first-class Windows ACL story for on-disk secrets (existing
  known gap, `cmd/local/umask_windows.go`); the new device private key
  inherits the same on-disk protection level as `bridge_token.json` today.
- A `mctl-portal` "connected daemons" UI (listed as optional/cross-repo in
  `internal/bridge/DESIGN.md`).

## Open questions

- Should the browser-based activation step reuse `internal/oauth/enable_access.go`'s
  existing wizard UI/session machinery (new step type that skips phone/SMS
  and instead confirms a device pairing code), or should it be a new,
  separate handler that only imports `telegramoidc` directly? This proposal
  assumes reuse of the OIDC-proof primitive and the `stepPermissions`
  send-consent UX pattern, but a new minimal handler, to avoid coupling to
  hosted-login state machine internals. Proceeding with a new, small
  `internal/oauth/activate_local.go` alongside the existing file.
- Exact device-proof cryptography (Ed25519 signature over a server-issued
  nonce vs. a full mTLS-like scheme) is left to implementation; this
  proposal assumes Ed25519 keypair generated at `init` time and a
  challenge-response at `activate`/refresh, matching the issue's "Preferred
  shape" section and the codebase's existing use of `crypto/rand` and
  `crypto/hmac` for similar bounded-secret work (`internal/workertoken/tokenhandler.go`,
  `internal/auth/localjwt/issuer.go`).
- Whether the CLI subcommand is literally named `activate` (as in the
  issue's illustrative example) or folded into `connect`. This proposal adds
  `activate` as new, additive command and deprecates none of `init` /
  `login` / `connect` / `daemon`, since `connect`'s current behavior
  (exchange worker token for bridge token) remains valid for legacy users.
- Exact short-lived credential TTL (issue says "hours, not days"). This
  proposal assumes 4 hours, matching the existing `bridgeTokenTTL = time.Hour`
  order of magnitude in `internal/bridge/tokenhandler.go` scaled up one step
  for the outer (worker-token-equivalent) credential, with the daemon
  refreshing at roughly half that interval the same way it already
  re-exchanges before expiry (`internal/bridge/DESIGN.md:111-114`). Exact
  number is a tuning parameter, not a correctness requirement.
- Whether device revocation is a new admin MCP tool or reuses
  `revoke_worker_token`'s pattern (`internal/mcp/revoke_worker_token_test.go`)
  extended with a `device_id` argument. This proposal assumes a new
  `revoke_local_bridge_device` tool that mirrors `revoke_worker_token`'s
  jti/telegram_id revocation semantics but keys on `device_id`, since a
  device row, not a single jti, is the durable revocation anchor here.
