# Per-client read-only OAuth scope ceiling for the Personal Assistant client (P1-0)

## Context

Issue #1327 is Phase 1 / P1-0 of the Personal Assistant (PA) epic #1312. It is the
security prerequisite for PA account linking (#1314, #1315). ADR 0011
(`docs/adr/0011-personal-assistant.md`) and threat model T8
(`docs/agent-runtime/personal-assistant-threat-model.md`, "Scopes and audience: the
strict read-only token contract") require that a token `tg` issues to the PA OAuth
client carries exactly `telegram:dialogs:read` and `telegram:messages:read`, even when
the signed-in principal is an administrator.

Today that is not true. `narrowGrant` (`internal/oauth/scopes.go`) narrows only the
five `DCRNegotiableScopes` to the requested set. It deliberately keeps the
membership-granted scopes `admin:users`, `admin:users:read` and `admin:broadcast`, so a
PA token for a principal in `TG_LOGIN_ADMINS` and `BROADCAST_OPERATORS` would carry admin
and broadcast authority. The refresh path (`boundRefreshGrant` in
`internal/oauth/server.go`) only intersects with the original grant, so it inherits
the same problem. This change adds a server-side scope ceiling for one explicitly
configured, trusted PA client identity. The ceiling applies to every grant path and
is fail-closed. Ordinary clients keep their current behaviour.

## User stories

- AS the platform owner I WANT a PA token issued by `tg` to carry only the two read
  scopes, whoever signs in, SO THAT a bug in the PA catalog pin or executor cannot
  reach admin, write, account-management or broadcast tools.
- AS a `tg` operator I WANT to name the PA client identity explicitly in deployment
  config, and I WANT the server to refuse to start on a bad value, SO THAT a typo cannot
  leave the PA client without its ceiling.
- AS the PA executor (#1314) I WANT the token response `scope` to always report the
  exact effective scope, and I WANT a refresh never to widen it, SO THAT my
  equality check after each exchange and refresh is a sound signal.
- AS an existing MCP client user (claude.ai, ChatGPT, Town, Cloudflare portal) I WANT
  my grants and refreshes unchanged SO THAT this security change does not break me.

## Acceptance criteria (EARS)

Configuration and identity binding
- WHEN `OAUTH_PA_CLIENT_ID` is unset or empty THE SYSTEM SHALL configure no scope
  ceiling and SHALL issue and refresh tokens exactly as before this change (S1-T11).
- WHEN `OAUTH_PA_CLIENT_ID` is set THE SYSTEM SHALL start only if the value meets all
  of these conditions. Otherwise startup SHALL fail with an error that names the
  variable:
  - it equals the `client_id` of an `OAUTH_PREREGISTERED_CLIENTS` entry, or it is a
    CIMD URL client_id while `OAUTH_CIMD_ACCEPT` is on and its host is in
    `OAUTH_CIMD_ALLOWED_HOSTS`;
  - it is not `mctl_self_connect`;
  - it does not use a server-generated DCR prefix (`tgdcr_`, `tgmcp_`);
  - it has no surrounding whitespace.
- IF `MCP_CLIENT_PROFILES` binds the PA client_id to any profile other than
  `pa-readonly` THEN THE SYSTEM SHALL refuse to start.
- THE SYSTEM SHALL identify the PA client only by exact, byte-for-byte equality of
  the OAuth `client_id` with the configured value. A client's `client_name`,
  requested scope, redirect host or other DCR or CIMD metadata SHALL NOT select or
  bypass the ceiling.

Ceiling at every grant
- WHEN an authorization code is redeemed at `/oauth/token` for the PA client THE SYSTEM
  SHALL grant the intersection of the identity's resolved scopes with the ceiling
  {`telegram:dialogs:read`, `telegram:messages:read`}. Implicit and membership scopes
  (`admin:users`, `admin:users:read`, `admin:broadcast`), write scopes and
  `account:manage` SHALL be removed, as SHALL any scope added to `ResolveScopes` later.
- WHEN a PA refresh token is rotated, including on the grace-window replay path, THE
  SYSTEM SHALL apply the same ceiling after `boundRefreshGrant`. The stored successor
  scope SHALL be the ceilinged set.
- WHILE a token is minted for the PA client THE SYSTEM SHALL carry no `groups` claim
  and SHALL stamp the `pa-readonly` tool profile.
- IF a code path asks `mintAccessToken` to mint a PA-client token whose scopes exceed
  the ceiling THEN THE SYSTEM SHALL mint nothing and SHALL answer `server_error`.
- WHEN an admin principal who is also a broadcast operator completes the PA flow THE
  SYSTEM SHALL return a token response whose `scope` is exactly
  `telegram:dialogs:read telegram:messages:read`. The access token's scopes SHALL be
  the same (S1-T8).
- IF the PA client's `/oauth/authorize` request names any scope outside the ceiling THEN
  THE SYSTEM SHALL refuse the request with `invalid_scope` and SHALL issue no code. An
  omitted scope SHALL be treated as the ceiling.
- THE SYSTEM SHALL always echo the effective granted scope in the token response. It
  SHALL never echo the requested scope. A refresh SHALL never return a scope wider
  than the grant it descends from.

Downstream refusal in `tg`
- WHEN a PA-client token calls `list_telegram_identities`, `set_telegram_access`,
  `mint_worker_token`, `prepare_broadcast`, `list_broadcasts`, `get_broadcast`,
  `cancel_broadcast`, `send_message` or any `account:manage` tool THE SYSTEM SHALL hide
  the tool from `tools/list` and refuse the `tools/call`. This check is made by `tg`
  itself, independent of the PA catalog pin.
- WHEN a PA-client token is presented to any HTTP route other than `/mcp`, such as
  `/api/bridge/token`, `/api/agent/token`, `/api/mcp/worker-token`, `/api/account` or
  the manage pages, THE SYSTEM SHALL refuse it with 403. This uses the existing
  profiled-credential confinement in `auth.Middleware`.

Non-PA clients
- WHILE a client_id is not the configured PA client THE SYSTEM SHALL keep the existing
  `narrowGrant`, `boundRefreshGrant`, groups and profile behaviour unchanged (S1-T11).

## Out of scope

- PA account linking, PA token storage, executor effective-scope verification, and
  activation. #1314 and #1315 own these. S1-T9 and S1-T10 are proven downstream. This
  change only guarantees the server half of that contract.
- Adding `OAUTH_PA_CLIENT_ID` or a PA preregistered client or CIMD host to the deployed
  `mctl-gitops` values. No preview deployment and no runtime activation.
- Alice (`alice`) scope narrowing, Glovo, Phase 2, write tools, and any widening of
  permissions.
- A general multi-client ceiling table configurable by env. The internal shape allows
  one later, but only the PA ceiling is wired now.

## Open questions

- Which identity will the PA bot use against `tg`: a preregistered client
  (`OAUTH_PREREGISTERED_CLIENTS`) or a CIMD document URL? ADR 0011 says "CIMD where
  served, DCR otherwise". `tg` serves CIMD, but no PA CIMD host is allowlisted today.
  Both are accepted and validated. Plain DCR is deliberately not accepted, because a
  DCR client_id is server-generated per registration and cannot be configured in
  advance.
- Should `/oauth/authorize` refuse a PA request that asks for an out-of-ceiling scope
  (`invalid_scope`, as proposed), or should it silently narrow it? The proposal refuses,
  to make the requested-vs-granted contract loud.
- If the signed-in identity is not entitled to one of the two read scopes, the
  response `scope` truthfully reports the narrower set and the executor fails the
  connection. Should the server refuse such a PA grant outright? It does not today. The
  proposal leaves this to the executor's equality check.
- The exact tool list and argument rules of the new `pa-readonly` profile. The proposal
  mirrors the T8 Phase 1 pin and forbids `fetch_media` on `get_messages`. The owner
  may want `core-readonly` argument limits (required peer, page bounds) as well.
