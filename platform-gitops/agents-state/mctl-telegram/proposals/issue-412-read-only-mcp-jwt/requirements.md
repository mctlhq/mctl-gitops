# Bounded minting path for read-only MCP worker tokens

## Context

`mctl-telegram` has two admin-mint token paths today: `POST /api/agent/token`
(mints `aud: "agent"` tokens, verified only at `/api/agent/v1/*` by
`selectAgentProvider`, `cmd/server/main.go:823`) and `POST /api/bridge/token`
(1-hour `aud: "bridge"` tokens for the Local Bridge daemon,
`internal/bridge/tokenhandler.go`). Neither can authenticate a headless,
non-interactive worker against `/mcp`: the agent-token path is rejected there
because `/mcp` uses the plain MCP provider, not `selectAgentProvider`, and the
bridge token is deliberately capped at one hour for an interactive session
that re-mints itself.

Because no bounded path exists for a read-only MCP worker, the canary
(`cmd/canary`, which only supports a static `CANARY_BEARER_TOKEN`, see
`loadConfig` in `cmd/canary/main.go:52`) has been running on a JWT signed by
hand with `OAUTH_JWT_SIGNING_KEY` and a one-year `exp`. This is exactly the
pattern `internal/config/config.go:13` (`maxOAUTHAccessTokenTTL`) was written
to prevent for the interactive OAuth flow: "access token is what an attacker
keeps after a leak, and its TTL is the only thing that bounds how long they
keep it." A hand-signed token also carries whatever scopes the signer typed
in, with no server-side allowlist and no record of it having been minted at
all — issue #399 already notes there is no revocation for access tokens, so a
long-lived, unlogged token is the worst combination available today.

This proposal adds a third bounded mint path — modeled directly on
`NewAgentTokenHandler` — for read-only MCP workers: an admin-scoped endpoint
that mints a token restricted to a fixed allowlist of `telegram:*:read`
scopes, bounded by a TTL ceiling well short of a year, logged the same way
every other admin mint is logged, and usable at the real `/mcp` endpoint the
canary (and any future read-only worker) actually calls.

## User stories

- AS the mctl-telegram operator I WANT to mint a long-lived but bounded,
  read-only MCP bearer token through an audited admin endpoint SO THAT I no
  longer need to hand-sign a year-long JWT with `OAUTH_JWT_SIGNING_KEY` every
  time a read-only worker (the canary, or a future one) needs a credential.
- AS the mctl-telegram operator I WANT the minted worker token to be
  rejected if it ever carries a write scope (`telegram:messages:send`,
  `telegram:messages:pin`) or `admin:users` SO THAT a compromised worker
  credential cannot send messages, pin messages, or reach admin-only routes.
- AS an on-call responder reading `docs/runbooks/canary.md` I WANT the
  documented rotation procedure to point at the new mint endpoint instead of
  manual JWT signing SO THAT rotating the canary's credential does not
  require touching the signing key by hand.

## Acceptance criteria (EARS)

- WHEN an authenticated caller with the `admin:users` scope calls the new
  mint endpoint with a target `telegram_id` and no explicit `scopes` THE
  SYSTEM SHALL mint a token carrying exactly the default read-only scope set
  (`telegram:dialogs:read`, `telegram:messages:read`).
- WHEN the caller supplies an explicit `scopes` list THE SYSTEM SHALL mint a
  token containing only the requested scopes, provided every requested scope
  is a member of the read-only allowlist.
- IF the caller supplies a scope outside the read-only allowlist (including
  `telegram:messages:send`, `telegram:messages:pin`, `admin:users`, or any
  unrecognized string) THEN THE SYSTEM SHALL reject the request with HTTP 400
  and mint nothing.
- IF the caller lacks the `admin:users` scope THEN THE SYSTEM SHALL reject
  the request with HTTP 403, identical to the existing `/api/agent/token`
  and `/api/admin/agent/profile` guards.
- WHEN a `ttl_hours` is supplied that exceeds the configured ceiling THE
  SYSTEM SHALL clamp the minted token's TTL to the ceiling rather than
  rejecting the request, mirroring `NewAgentTokenHandler`'s existing
  `maxAgentTokenTTL` clamp behavior.
- WHEN no `ttl_hours` is supplied THE SYSTEM SHALL mint a token with the
  documented default TTL (30 days).
- WHEN a token is minted THE SYSTEM SHALL log the admin's user id, the
  target Telegram id, the granted scopes, and the TTL at `info` level, in the
  same shape as the existing `agent token minted` / `bridge token minted`
  log lines.
- WHEN a worker token minted by this path is presented at `/mcp` THE SYSTEM
  SHALL authenticate it through the existing MCP provider (`selectProvider`)
  exactly as it would any other locally-issued JWT, subject to the same
  issuer/signature/expiry checks already implemented in `localjwt.Verify`.
- WHILE a worker token is valid THE SYSTEM SHALL still enforce the existing
  per-tool `requireScope` gate (`internal/mcp/tools.go:1196`) so a read-only
  scoped token cannot invoke `telegram:messages:send`/`:pin`-gated tools,
  regardless of how the token was minted.
- IF `OAUTH_JWT_SECRET` (`cfg.OAUTHJWTSecret`) is unset THEN THE SYSTEM SHALL
  NOT mount the new mint endpoint, matching the existing pattern for
  `/api/agent/token` and `/api/bridge/token` (both gated on `secret != ""`).

## Out of scope

- Teaching `cmd/canary` a refresh-token grant (issue's option 1). This
  proposal implements option 2 from the issue directly.
- Access-token revocation in general (issue #399). The new path reduces the
  blast radius of an unrevocable leak via TTL and scope bounds; it does not
  add a revocation mechanism.
- Session absolute-TTL work (issue #409) — unrelated axis (session store vs.
  bearer-token minting).
- Any change to `cmd/canary` itself. The canary already only needs a bearer
  string in `CANARY_BEARER_TOKEN`; it does not need to know how that string
  was produced. Rotating the canary's Kubernetes secret to a token minted by
  the new endpoint is an operational follow-up, not a code change.
- A dedicated `auth.Provider` / mount point analogous to `selectAgentProvider`
  or `selectBridgeProvider`. The worker token is designed to authenticate at
  the existing `/mcp` endpoint through the existing provider (see design.md
  for why a separate provider is not needed here).
- Building a UI or CLI for minting; this is an HTTP admin endpoint only, the
  same level of tooling `/api/agent/token` has today (curl/admin script).

## Open questions

- Should the read-only scope allowlist be centrally defined and shared with
  `internal/oauth/scopes.go`'s `DCRNegotiableScopes`, or kept local to the
  new handler? Resolved for this proposal as: define a small local
  `allowedReadOnlyScopes` slice in the new package, since `DCRNegotiableScopes`
  also contains write scopes and is scoped to the DCR advertisement use case,
  not admin-minting validation — coupling them would require the DCR list to
  never grow a read-only-incompatible entry silently. Revisit if a third
  consumer needs the same allowlist.
- Should the new endpoint require the target `telegram_id` to already exist
  as a connected user (like the agent token path implicitly assumes via
  `EnsureUserByTelegramID` at verification time), or allow minting for an
  account that has not connected yet? Resolved as: allow it, matching
  `NewAgentTokenHandler`'s behavior (it does not validate the target account
  exists at mint time; `EnsureUserByTelegramID` runs lazily on first
  `Authenticate` call). This matches the issue's stated context of migrating
  the canary to a fresh account (`924671154`).
- Exact TTL ceiling: the issue does not specify a number, only that it must
  be well short of a year. Resolved as 30-day default / 90-day max, taken
  directly from the existing `defaultAgentTokenTTL` / `maxAgentTokenTTL`
  constants in `internal/agentapi/tokenhandler.go`, since that is the closest
  existing precedent for a non-interactive, admin-minted worker credential.
  An operator who needs a shorter-lived canary token can still pass
  `ttl_hours`.
