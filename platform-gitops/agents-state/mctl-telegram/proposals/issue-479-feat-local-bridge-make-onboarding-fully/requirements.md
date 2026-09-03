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
  allowed SO THAT I control message-sending risk without an operator flipping
  `set_account_send` on my behalf.
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
  a server-verified proof of Telegram identity using the existing
  `internal/auth/telegramoidc` flow rather than trusting an operator- or
  client-supplied integer.
- IF the identity a device claims does not match the identity the server
  independently verified THEN THE SYSTEM SHALL refuse activation and SHALL
  NOT create or modify any `telegram_accounts` row.
- WHEN activation is started THE CLI SHALL NOT require any pre-existing
  worker token, bridge token, hosted MTProto session, or authenticated MCP
  session. The browser/OIDC leg is the authority that proves the Telegram
  owner and authorizes exactly one pending device activation.
- WHEN activation completes THE SYSTEM SHALL always create/reconcile the
  account with `send_enabled=false`. Enabling send is a distinct explicit
  owner-consent action and is not part of account activation.
- WHILE an account has not been granted send consent THE SYSTEM SHALL keep
  `send_enabled=false` and SHALL continue returning the existing dry-run
  preview behavior from `send_message`.
- WHEN the owner explicitly grants send permission THE SYSTEM SHALL record
  `send_enabled=true` together with an audit row carrying actor identity and
  timestamp, without requiring the `admin:users`-scoped `set_account_send`
  tool.
- WHEN the owner explicitly revokes send permission THE SYSTEM SHALL set
  `send_enabled=false` and SHALL audit the revocation the same way.
- IF an owner completes activation without granting send THEN THE SYSTEM
  SHALL still complete account creation and issue Local Bridge credentials
  scoped read-only.
- WHEN activation succeeds THE SYSTEM SHALL automatically issue a Local
  Bridge access credential without any call to the admin-only
  `POST /api/mcp/worker-token`.
- WHEN a Local Bridge access credential is issued via self-service activation
  THE SYSTEM SHALL set its lifetime in hours, not days/months.
- WHILE a Local Bridge daemon holds a valid, unexpired, unrevoked credential
  bound to its registered device key THE SYSTEM SHALL allow that daemon to
  refresh the credential without operator involvement.
- IF a refresh request is not accompanied by valid proof of the bound device
  key THEN THE SYSTEM SHALL refuse the refresh.
- WHEN a device-bound credential is refreshed THE SYSTEM SHALL derive the new
  scopes from current server-side account/device state, including the current
  `send_enabled` value; refresh SHALL NOT simply copy scopes from the old
  credential. A send grant must become effective on a later refresh, and a
  send revoke must remove send capability on a later refresh.
- WHEN an operator revokes a device or account THE SYSTEM SHALL stop refresh
  immediately and SHALL prevent further bridge use by that device. The
  implementation SHALL either terminate an already-active bridge connection
  immediately or define, document, and test a bounded maximum revocation
  latency no longer than the lifetime of the derived bridge credential.
- WHEN a self-service-issued Local Bridge credential is minted, refreshed, or
  revoked THE SYSTEM SHALL write an audit row and SHALL NOT include token,
  activation-code, private-key, nonce, or signature material in logs/audit.
- WHERE an account was migrated from hosted to local via the existing
  `set_account_mode` admin tool THE SYSTEM SHALL continue to support that
  path unchanged.
- WHERE a Local Bridge daemon already holds a manually minted worker token
  (purpose `local-bridge`) THE SYSTEM SHALL continue to accept it through
  `connect` and `/api/bridge/token` for a defined migration window.
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
- A mctl-portal "connected daemons" UI.
- Windows ACL hardening for on-disk secrets.
- Removing existing admin tools (`provision_local_account`, `set_account_mode`,
  `set_account_send`, `POST /api/mcp/worker-token`); they remain support,
  recovery, and migration tools.
- A new end-to-end encryption scheme between the MCP client and daemon.

## Open questions

- Exact proof-of-possession wire format remains an implementation choice; the
  preferred shape is Ed25519 challenge-response over a short-lived,
  single-use server nonce.
- Exact hours-scale access TTL remains a tuning parameter. It must stay short
  enough for bounded exposure and be refreshed automatically by the daemon.
- Multi-device support is not required by this proposal; the device table is
  the future-compatible revocation/binding anchor.
