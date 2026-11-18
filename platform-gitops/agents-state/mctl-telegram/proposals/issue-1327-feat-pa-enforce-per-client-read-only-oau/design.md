# Design: issue-1327-feat-pa-enforce-per-client-read-only-oau

## Current state

**Scope resolution.** `Server.ResolveScopes` (`internal/oauth/server.go`) maps a
Telegram id to its groups and scopes:
- A `TG_LOGIN_ADMINS` id gets `telegram:dialogs:read`, `telegram:messages:read`,
  `telegram:messages:send`, `telegram:messages:pin`, `admin:users` and
  `account:manage`, with groups `platform-admins` and `admins`.
- If that id is also in `BROADCAST_OPERATORS`, it gets `admin:broadcast` as well.
- The lookup tier gets `admin:users:read`.

**Narrowing on code exchange.** `narrowGrant(entitled, requested)`
(`internal/oauth/scopes.go`) narrows only the scopes listed in `DCRNegotiableScopes`
(the two reads, send, pin, `account:manage`). Its doc comment states that it keeps
every non-negotiable scope (`admin:users`, `admin:users:read`, `admin:broadcast`)
whatever was requested. An empty request returns the full entitled set.

**Grant paths that mint OAuth access tokens.** All of them go through `mintAccessToken`:
- `handleTokenAuthCode`: `ResolveScopes`, then `narrowGrant`, then `mintAccessToken`,
  then `issueRefreshToken`, then `writeTokenJSON`.
- `handleTokenRefresh`: `ResolveScopes`, then `boundRefreshGrant(groups, scopes,
  rt.Scope)`, then `refreshGrantStillValid`, then `mintAccessToken`, then
  `RotateRefreshToken` with `Scope: strings.Join(scopes, " ")`.
- `attemptGraceRecovery`: the same sequence for a grace-window replay.
- `ExchangeConnect`: only for `ConnectClientID` (`mctl_self_connect`). Its codes and
  refreshes are refused at `/oauth/token`.

`boundRefreshGrant` only intersects with the predecessor's stored scope. Refresh is
already monotonic, but it is only as narrow as the original grant.

**Token claims.** `mintAccessToken(origin tokenOrigin, ...)` is documented as "the only
place an OAuth access token is minted". It stamps `ClientID` and the tool profile from
`profileFor(origin)`, which uses `Config.ClientProfiles` (`toolprofile.Bindings`,
`MCP_CLIENT_PROFILES`). `writeTokenJSON` always echoes the granted scope set.

**Client identity.**
- `client_id` is bound at code redemption (`entry.ClientID != clientID` returns
  `invalid_grant`) and at refresh (`rt.ClientID != clientID` returns `invalid_grant`).
  The refresh-token family stores `ClientID` and `RedirectURI`.
- Static clients come from `Config.PreregisteredClients`, parsed from
  `OAUTH_PREREGISTERED_CLIENTS` in `internal/config/config.go`. They are seeded into
  `s.clients` with exact redirect URIs in `oauth.New`, and `validatePreregisteredClient`
  refuses the `db.PinnedClientIDPrefix` (`tgdcr_`) prefix.
- DCR client ids are server-generated (`"tgmcp_" + randomToken(16)`, or pinned
  `tgdcr_`). A registrant cannot choose one.
- CIMD URL client_ids are resolved by `Config.CIMD` at authorize and at both token
  grants (`authenticateCIMDClient`). `internal/config` already cross-checks
  `OAUTH_CIMD_ACCEPT` against preregistered URL-shaped ids.

**Downstream enforcement.**
- `internal/mcp/toolscopes.go` (`toolScopes`, `scopeAllows`, `toolAllowed`) is applied
  through `mcpserver.WithToolFilter` on `tools/list` and on `tools/call`. The relevant
  entries:
  - `send_message` requires `telegram:messages:send`.
  - `list_telegram_identities` requires `admin:users` or `admin:users:read`.
  - `set_telegram_access` and `mint_worker_token` require `admin:users`.
  - The four broadcast tools require `BroadcastScope` (`admin:broadcast`).
  - The account tools require `account:manage`.
  - `get_my_identity`, `get_my_audit_log`, `get_my_send_status` and `list_assistants`
    accept any authenticated identity.
- A credential carrying a tool profile is refused with 403 on every route except
  `/mcp` (`internal/auth/middleware.go`, `MsgProfileRestricted`). Without a profile, a
  read-scoped token is still accepted by HTTP routes that check no scope, such as
  `/api/bridge/token` (`internal/bridge/tokenhandler.go`, which also copies
  `id.Groups` into the bridge token).
- `internal/toolprofile/toolprofile.go` defines `core-readonly` and `core-reply`.
  `ParseBindings` fails closed on a bad table.
- `internal/mcp/zero_admin_e2e_test.go` already shows the pattern of driving the real
  `oauth.Server` from an `internal/mcp` test.

**Deployed state checked:**
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`. Observed:
  - `AUTH_MODE: local-jwt`.
  - `OAUTH_CIMD_ACCEPT: "true"`, `OAUTH_CIMD_ALLOWED_HOSTS: chatgpt.com,claude.ai,vscode.dev,www.town.com`.
  - `MCP_CLIENT_PROFILES` binds only the Town CIMD client to `core-reply`.
  - No `OAUTH_PREREGISTERED_CLIENTS` (the comment notes the portal static client was
    retired 2026-09-26).
  - `OAUTH_DCR_REDIRECT_URIS` set for the Cloudflare portal.
  - `TG_LOGIN_ADMINS` and `BROADCAST_OPERATORS` each name the single operator id,
    the same account in both.
  - No PA client identity or `OAUTH_PA_CLIENT_ID` is configured.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`: `AUTH_MODE:
  local-jwt`, issuer `https://tg-preview.mctl.ai`, no CIMD, profile or preregistered
  settings.
- The mctl MCP tools were not called. The gitops values were sufficient for the
  config questions, and this change deploys nothing.

So the production admin is exactly the S1-T8 principal: a member of both
`TG_LOGIN_ADMINS` and `BROADCAST_OPERATORS`. No PA client exists yet, so leaving the
variable unset in production keeps today's behaviour.

## Proposed solution

### 1. The PA identity and the ceiling (`internal/oauth`)

- In `internal/oauth/scopes.go`, add:
  - `var PersonalAssistantScopeCeiling = []string{"telegram:dialogs:read", "telegram:messages:read"}`;
  - `capToCeiling(groups, scopes, ceiling []string) ([]string, []string)`, which
    returns the intersection of `scopes` with `ceiling` in ceiling order and `nil`
    groups. It is a pure function next to `narrowGrant`. Its doc comment explains that
    it is the one narrowing that includes membership scopes, and that it works as an
    allowlist, so a scope added to `ResolveScopes` later is stripped by default.
- In `oauth.Config`, add `PersonalAssistantClientID string`. `New` builds an
  unexported `s.scopeCeilings map[string][]string`, with at most one entry today. The
  map shape lets a later client get a ceiling without touching the grant paths.
- In `New`, validate the value and fail closed. When the value is non-empty:
  - it must equal a `PreregisteredClients[i].ClientID`, or be `cimd.IsCIMDURL(...)`
    with `cfg.CIMD != nil`;
  - it must not be `ConnectClientID`;
  - it must not start with `db.PinnedClientIDPrefix` or `tgmcp_`;
  - it must not carry whitespace;
  - if `cfg.ClientProfiles.ByClientID` already binds it to anything other than
    `toolprofile.PersonalAssistantReadonly`, that is an error.

  `New` then injects the binding `ByClientID[paClientID] = pa-readonly` into its own
  copy of the bindings, so the profile follows the client without any extra operator
  step.
- Add the method `s.ceilingFor(clientID string) ([]string, bool)`, which matches
  exact bytes only.
- Apply the ceiling at every grant path:
  - In `handleTokenAuthCode`, after `narrowGrant`:
    `if c, ok := s.ceilingFor(clientID); ok { groups, scopes = capToCeiling(groups, scopes, c) }`.
    The refresh token is then saved with the ceilinged set, because `issueRefreshToken`
    is passed `scopes`. The implementer must confirm which scope string the refresh row
    stores.
  - In `handleTokenRefresh` and `attemptGraceRecovery`, after `boundRefreshGrant` and
    before `refreshGrantStillValid`, apply the same helper. A family that loses both
    reads is then refused by the existing logic rather than minted scopeless. A PA
    family rotated before this change, or one carrying wider scopes, is narrowed on its
    next refresh. It is never widened.
  - In `ExchangeConnect`, call the helper too, for uniformity. It never matches,
    because `New` rejects the self-connect id.
- Add an invariant at the choke point. `mintAccessToken` checks
  `s.ceilingFor(origin.ClientID)`. If any scope is outside the ceiling, or groups are
  non-empty, it returns `errCeilingViolation` and mints nothing. The callers map that
  error to `server_error` and log it at ERROR. This catches a future grant path that
  forgets the helper.
- `/oauth/authorize` gets a requested-scope contract. For a ceiling client, after
  `validateClient` succeeds, every field of `scope` must be in the ceiling. Otherwise the
  server redirects with `error=invalid_scope` (RFC 6749 4.1.2.1), because the
  redirect_uri was already validated, and records no pending entry. An empty scope is
  allowed, and the token endpoint caps it to the ceiling.
- The token response is unchanged. `writeTokenJSON` already echoes the granted
  set, which is now exactly the ceiling for an entitled principal. The grant log line
  should add `ceiling_applied=true` and the stripped scope names. It must not log the
  Telegram id beyond what the existing line logs.

### 2. The PA tool profile (`internal/toolprofile`)

Add `PersonalAssistantReadonly = "pa-readonly"`. Its tools are `list_dialogs`,
`list_folders`, `list_topics`, `get_messages` (with `fetch_media` forbidden),
`search_messages` and `get_my_identity`. This mirrors the T8 Phase 1 pin. The profile
does two jobs:
- through `auth.Middleware`, it confines the PA credential to `/mcp`, so
  `/api/bridge/token`, `/api/agent/token`, `/api/mcp/worker-token*`, `/api/account` and
  the manage pages answer 403;
- it hides `get_unread_messages`, `get_media`, `prepare_get_media` and the
  any-identity tools the pin excludes.

The profile is defence in depth. The scope ceiling is the authorization boundary,
and `toolScopes` alone already refuses every admin, write, broadcast and account tool.

### 3. Configuration (`internal/config`, `cmd/server`)

- Add `OAUTHPAClientID` to `internal/config/config.go`, read from `OAUTH_PA_CLIENT_ID`.
  `Load` validates it after `OAUTH_PREREGISTERED_CLIENTS` and the CIMD settings are
  parsed. It fails startup unless the value is either:
  - a preregistered `client_id`, or
  - a CIMD URL while `OAUTHCIMDAccept` is on and its host is in the CIMD allowed hosts.

  This is the only place the CIMD host allowlist is visible, because the
  `CIMDResolver` interface does not expose it.
- In `cmd/server/main.go`, pass the value as `PersonalAssistantClientID` in the
  `oauth.Config` literal next to `PreregisteredClients` and `ClientProfiles`, and add it
  to the startup info log.
- Document the variable wherever `OAUTH_PREREGISTERED_CLIENTS` and
  `MCP_CLIENT_PROFILES` are documented: README or SECURITY env tables and the client
  tool profiles runbook. Check `docs/compatibility_test.go` and any env-var doc tests.

### Why this shape

- The PA client is keyed by exact `client_id`. Exact match is the only identity `tg`
  already binds at both code redemption and refresh. Preregistered and CIMD ids are
  operator-controlled and cannot be minted by a DCR registrant.
- A spoofed PA `client_id` can only narrow the spoofer: the ceiling removes authority
  and grants none, and its codes still go only to the registered redirect URIs.
- The reverse spoof, where a client obtains PA-like treatment without the ceiling, is
  impossible, because the ceiling does not depend on `client_name`, scope or redirect
  host.
- Enforcing the ceiling in grant handling and again as an invariant in
  `mintAccessToken` follows the precedent of `profileFor`, which is already consulted
  at that single choke point.

## Alternatives

1. **Add the admin scopes to `DCRNegotiableScopes` or make `narrowGrant` strip
   non-negotiable scopes for read-only requests.** Dropped. This changes behaviour for
   every client: the Cloudflare portal and admins who omit scope rely on today's
   semantics, which S1-T11 forbids. It also keys the decision on the requested scope,
   which the issue rules out as user-controlled.
2. **Rely on a tool profile alone (bind the PA client to `core-readonly` or
   `pa-readonly` without a scope ceiling).** Dropped as the boundary. The token would
   still carry `admin:users` and `admin:broadcast` in its `scope` and claims. The
   executor's exact-equality check (S1-T9) would then fail for every admin. A profile
   bug, or a future route that admits profiled credentials, would expose admin
   authority. The profile is kept only as defence in depth.
3. **A general `OAUTH_CLIENT_SCOPE_CEILINGS` env table (client_id to arbitrary scope
   list).** Deferred. It is more flexible, but it lets an operator configure a "ceiling"
   that includes `admin:*`, and it widens the review surface of a security
   prerequisite. The internal `scopeCeilings` map leaves the door open, and the env
   surface stays a single PA id with a code-defined ceiling.
4. **Key the PA identity on DCR `client_name` or a software statement.** Rejected.
   That metadata is unverified and user-controlled, which the issue forbids.

## Platform impact

- **Migrations:** none. The refresh-token rows already store `ClientID` and `Scope`. A
  ceilinged family simply stores a narrower scope string.
- **Backward compatibility:** with `OAUTH_PA_CLIENT_ID` unset, which is today's
  production and preview state, every code path behaves byte-for-byte as before. S1-T11
  regression tests guard this. The `pa-readonly` profile is unused unless the PA
  client is configured, or an operator binds it.
- **Resource impact:** negligible. There is one map lookup per grant and per mint.
- **Risks and mitigations:**
  - *A grant path added later bypasses the helper.* Mitigation: the invariant in
    `mintAccessToken` refuses to mint, and a test enumerates every grant path.
  - *Misconfiguration silently leaves PA uncapped.* Mitigation: fail-closed validation
    in both `internal/config` and `oauth.New`. The PA executor also checks exact
    equality (#1314), so a missing ceiling breaks linking loudly rather than silently.
  - *The PA identity ends up being the CIMD URL of a host later removed from the
    allowlist.* Startup then fails, which is correct. The operator must remove
    `OAUTH_PA_CLIENT_ID` or restore the host.
  - *Groups dropped for PA tokens.* In local-jwt mode no authorization decision reads
    `Groups`. Dropping them also stops the label leaking into bridge tokens, which the
    profile confinement already blocks.
- **Rollout:** this change is code only, with no gitops change. Configuring the PA
  client in `mctl-gitops` is a later, separately approved step under the issue's
  governance.
