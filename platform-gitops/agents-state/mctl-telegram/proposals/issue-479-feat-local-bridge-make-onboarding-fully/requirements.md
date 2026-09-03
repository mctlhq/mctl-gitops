# Local Bridge: fully self-service onboarding, zero required operator actions

## Context

Local Bridge (M4) lets a user run their MTProto session on their own machine
while `tg.mctl.ai` relays MCP tool calls to it. The server half is built and
deployed; the daemon (`cmd/local`) implements `init`, `login`, `connect`,
`daemon`. But `docs/local-bridge.md` and `internal/bridge/DESIGN.md` both
document that a fresh user cannot finish onboarding alone: an operator must
call the admin-only MCP tools `provision_local_account`
(`internal/mcp/tools.go:1093`) or `set_account_mode`
(`internal/mcp/tools.go:1011`), hand-mint a long-lived bearer token via
`POST /api/mcp/worker-token` (`internal/workertoken/tokenhandler.go`), and
call `set_account_send` (`internal/mcp/tools.go:951`) before sending works.
`internal/bridge/DESIGN.md`'s own "Remaining gaps" section already names this
exact gap ("No self-serve enablement", "No long-lived MCP token to hand to
connect"), so this proposal turns that gap into a concrete plan.

The issue asks for a local-first fresh-user path with zero mandatory operator
steps: local Telegram login, self-service identity activation, owner-controlled
send consent, automatic short-lived credential issuance with device-bound
refresh, and a documentation split between the client/owner path and the
operator support/recovery path. Existing hosted accounts, hosted->local
migration, and manually provisioned Local Bridge installs must keep working.

## User stories

- AS a new Local Bridge user I WANT to authenticate with Telegram locally and
  activate the bridge myself SO THAT I never have to contact an operator to
  get `telegram_id` registered or the account provisioned.
- AS a new Local Bridge user I WANT to explicitly choose whether sending is
  allowed during activation SO THAT I control message-sending risk without an
  operator flipping `set_account_send` on my behalf.
- AS a Local Bridge daemon operator (the end user running the daemon) I WANT
  credentials to be issued and refreshed automatically SO THAT I never mint
  or paste a long-lived bearer token.
- AS a platform operator I WANT credential theft to be less useful than today
  SO THAT a stolen bridge/worker credential cannot be replayed indefinitely
  from any machine.
- AS a platform operator I WANT to revoke a device/account and have that
  immediately stop refresh and bridge use SO THAT abuse and leaks are
  contained without me having to hunt down every derived token.
- AS an existing hosted user I WANT my account and migration path to keep
  working unmodified SO THAT this change does not regress current behavior.

## Acceptance criteria (EARS)

- WHEN a Telegram id has never completed a hosted login and its owner
  completes local login plus self-service activation THE SYSTEM SHALL create
  a `telegram_accounts` row with `mode='local'` and `session_encrypted=NULL`
  without any admin-scoped tool call.
- WHEN activation completes for an owner/device/account that already has an
  active `local` row THE SYSTEM SHALL treat the request as idempotent and
  SHALL NOT create a duplicate `telegram_accounts` row or duplicate device
  binding.
- WHEN activation binds an identity THE SYSTEM SHALL derive `telegram_id` from
  a server-verified proof of Telegram identity (the existing
  `internal/auth/telegramoidc` OIDC flow, the same mechanism
  `internal/oauth/enable_access.go`'s `startLoginFlow` already uses to check
  "the phone login must match the OIDC-proven id") rather than from an
  operator- or client-supplied integer.
- IF the identity a device claims does not match the identity the server
  independently verified THEN THE SYSTEM SHALL refuse activation and SHALL
  NOT create or modify any `telegram_accounts` row.
- WHILE an account has not been granted send consent THE SYSTEM SHALL keep
  `send_enabled=false` and SHALL continue returning the existing dry-run
  preview behavior from `send_message` (per-account `send_enabled=false`).
- WHEN the owner explicitly grants send permission during or after activation
  THE SYSTEM SHALL record `send_enabled=true` together with an audit row
  carrying the actor identity and timestamp, without requiring the
  `admin:users`-scoped `set_account_send` tool.
- WHEN the owner explicitly revokes send permission THE SYSTEM SHALL set
  `send_enabled=false` and SHALL audit the revocation the same way.
- IF an owner completes activation without granting send THEN THE SYSTEM
  SHALL still complete account creation and issue Local Bridge credentials
  scoped read-only.
- WHEN activation succeeds THE SYSTEM SHALL automatically issue a Local
  Bridge access credential scoped to `local-bridge` (the existing
  `allowedLocalBridgeScopes` allowlist in `internal/workertoken/tokenhandler.go`)
  without any call to the admin-only `POST /api/mcp/worker-token`.
- WHEN a Local Bridge access credential is issued via self-service activation
  THE SYSTEM SHALL set its lifetime in hours (not the current
  `defaultWorkerTokenTTL` of 30 days), matching the issue's "short-lived,
  hours not months" requirement.
- WHILE a Local Bridge daemon holds a valid, unexpired, unrevoked credential
  bound to its registered device key THE SYSTEM SHALL allow that daemon to
  refresh the credential without operator involvement, extending the pattern
  `internal/workertoken/renewhandler.go` already implements for admin-minted
  tokens.
- IF a refresh request is not accompanied by valid proof of the bound device
  key THEN THE SYSTEM SHALL refuse the refresh.
- WHEN an operator revokes a device or account THE SYSTEM SHALL cause all
  subsequent refresh attempts for that device/account to fail and SHALL
  cause the bridge (`GET /bridge`, `internal/bridge/server.go`) to reject that
  daemon's connection.
- WHEN a self-service-issued Local Bridge credential is minted, refreshed, or
  revoked THE SYSTEM SHALL write an audit row through the existing
  `internal/db/store.go` `LogToolCall`/audit chain, and SHALL NOT include the
  token or device secret value in that row or in any log line (enforced via
  `internal/audit/redact.go`, which must gain any new sensitive field names
  this work introduces).
- WHERE an account was migrated from hosted to local via the existing
  `set_account_mode` admin tool THE SYSTEM SHALL continue to support that
  path unchanged.
- WHERE a Local Bridge daemon already holds a manually minted worker token
  (purpose `local-bridge`, minted via today's `POST /api/mcp/worker-token`)
  THE SYSTEM SHALL continue to accept it through `connect` and
  `/api/bridge/token` for a defined migration window.
- THE SYSTEM SHALL NOT silently migrate an existing hosted account to local
  mode as a side effect of any new self-service flow.
- THE SYSTEM SHALL NOT require the fresh-user path to create or store a
  hosted MTProto session (`session_encrypted`) at any point.

## Out of scope

- Changing the Local Bridge websocket transport, the `/bridge` protocol
  envelope (`internal/bridge/protocol.go`), or the public `/mcp` endpoint.
- Forcing any existing hosted user to migrate to local mode.
- Implementing the five tools already documented as unsupported in local mode
  (`edit_message`, `delete_messages`, `forward_messages`, `search_messages`,
  `set_reaction`) or the `fetch_media=true` restriction.
- A hosted always-on listener equivalent for local-mode accounts.
- A mctl-portal "connected daemons" UI (tracked separately per
  `internal/bridge/DESIGN.md`'s cross-repo notes).
- Windows ACL hardening for on-disk secrets (tracked as its own known gap in
  `internal/bridge/DESIGN.md`); this proposal does not make the Windows
  on-disk story worse, but does not fix it either.
- Removing existing admin tools (`provision_local_account`, `set_account_mode`,
  `set_account_send`, `POST /api/mcp/worker-token`); they remain as
  support/recovery/migration tools per the issue's non-goals.
- A new end-to-end encryption scheme between the MCP client and the daemon;
  the relay still sees payloads, unchanged from today's trust model.

## Open questions

- **How does the daemon prove Telegram identity to the server without a
  hosted session or a full OIDC browser round trip on every activation?**
  The issue requires the client to determine `telegram_id` locally and then
  activate against the server. The codebase's only existing
  server-verified Telegram identity proof is the browser-based
  `internal/auth/telegramoidc` OIDC flow (`oauth.telegram.org`), which today
  runs inside `internal/oauth`'s authorization-code dance. Interpretation
  used here: activation reuses that same OIDC proof through a
  device-authorization-style flow (daemon opens a browser to an activation
  URL; user completes Telegram OIDC login; server matches the OIDC-proven
  `telegram_id` against the one the daemon's local MTProto login reported)
  — mirroring the identity-match check `internal/oauth/enable_access.go`'s
  `startLoginFlow` already performs between OIDC identity and phone-login
  identity. This needs product sign-off before implementation; assumed here
  as the closest fit to existing infrastructure.
- **What proves device possession on refresh?** The issue asks for a device
  keypair bound at activation, with refresh requiring proof of that key
  rather than only a bearer secret. No such primitive exists in this
  codebase today (`internal/workertoken`'s renew path is bearer-token-only).
  This proposal assumes a signed-challenge (proof-of-possession) scheme
  layered on top of the existing renew handler; exact algorithm (e.g.
  Ed25519 challenge-response) is left to implementation, per the issue's own
  "exact crypto/protocol details can be chosen during design."
- **Where does send-consent UI live?** The issue mentions CLI and "browser/
  device activation step where useful" without mandating one. This proposal
  assumes the activation web page (a sibling of `internal/oauth`'s existing
  enable_access pages) is the natural place to collect explicit send
  consent, with a CLI flag as a secondary path for headless setups. Needs
  UX confirmation.
- **Definition of "short-lived" in hours.** The issue says "hours, not a
  manually copied permanent token" without a number. This proposal assumes
  a default of 8 hours for the self-service-issued Local Bridge access
  credential (short enough that a leaked, unrefreshed credential expires the
  same day; long enough that a daemon restart within a workday does not
  force re-activation), with automatic refresh keeping a running daemon
  alive indefinitely subject to the device-binding and revocation checks
  above. Needs product sign-off.
- **Multi-device support.** The issue's device-binding model implies one
  device key per activation. `docs/local-bridge.md` already documents "one
  account per machine" / "one daemon per account" as a current limitation;
  this proposal does not change that limitation, but device binding does add
  the scaffolding (a devices table) that a future multi-device story could
  build on. Not designed further here.
