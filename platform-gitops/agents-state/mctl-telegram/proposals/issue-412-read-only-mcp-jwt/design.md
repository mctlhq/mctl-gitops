# Design: issue-412-read-only-mcp-jwt

## Current state

**Token issuance paths today** (all built on `internal/auth/localjwt`, an
HS256 self-issuer/verifier — `internal/auth/localjwt/issuer.go`):

1. **Interactive OAuth** (`internal/oauth/server.go`): a human logs in via the
   Telegram OIDC widget; `ResolveScopes` (`internal/oauth/server.go:666`)
   grants `telegram:*` scopes by tier (admin / client / none) and the token
   carries no `aud` by default. TTL is `cfg.OAUTHAccessTokenTTL`, hard-capped
   at `maxOAUTHAccessTokenTTL = 24h` (`internal/config/config.go:20`) precisely
   because these tokens are refreshable — `internal/oauth/server.go:1718`
   mints a fresh access token on `grant_type=refresh_token`, and rotation +
   reuse-detection already exist for refresh tokens (referenced in the issue,
   implemented in `internal/db/refresh_tokens.go`).
2. **`POST /api/bridge/token`** (`internal/bridge/tokenhandler.go`): any
   already-authenticated identity exchanges its token for a 1-hour
   `aud: "bridge"` token, verified only at `GET /bridge` by
   `selectBridgeProvider` (`cmd/server/main.go:759`), which sets
   `AudienceRequired: true, ExpectedAudience: "bridge"`. Deliberately short:
   built for an interactive daemon session, not a standing credential.
3. **`POST /api/agent/token`** (`internal/agentapi/tokenhandler.go`):
   admin-scoped (`id.HasScope("admin:users")`), mints `aud: "agent"` tokens
   for a *target* Telegram id different from the calling admin, TTL
   defaulting to 30 days and clamped at 90 days
   (`defaultAgentTokenTTL`/`maxAgentTokenTTL`). Verified only at
   `/api/agent/v1/*` by `selectAgentProvider` (`cmd/server/main.go:823`,
   `AudienceRequired: true, ExpectedAudience: "agent"`). This is the exact
   shape the issue wants, but scoped to the wrong surface: `/api/agent/v1` is
   the communication-agent job-queue API (`internal/agentapi/server.go`), a
   completely different feature (`AGENT_ENABLED`, `agentQueue`,
   `agent_profiles`) from the MCP tool surface the canary needs
   (`list_dialogs`, `get_unread_messages` over `/mcp`).
4. **Manual signing** (the workaround this issue is about): an operator runs
   `localjwt.Issuer.Mint` by hand (or an equivalent script) with
   `OAUTH_JWT_SIGNING_KEY`, picks arbitrary scopes and a one-year `exp`, and
   the result becomes `CANARY_BEARER_TOKEN` in the `mctl-telegram-canary`
   Kubernetes secret (`deploy/canary/cronjob.yaml:44`). No allowlist, no TTL
   ceiling, no log line, no record that minting happened.

**How `/mcp` verifies tokens today**: `selectProvider` (`cmd/server/main.go:591`)
builds the plain `localjwt.Provider` used at `/mcp` with
`ExpectedAudience: cfg.OAUTHJWTAudience` (env `OAUTH_JWT_AUDIENCE`, default
`""`) and `AudienceRequired: cfg.OAUTHJWTAudReq` (env
`OAUTH_JWT_AUDIENCE_REQUIRED`, default `false`). `localjwt.CheckAudience`
(`internal/auth/localjwt/issuer.go:145`) treats `expected == ""` as "check
disabled" — so today, by default, `/mcp` accepts a token with any `aud` value
at all, including none. This is what lets a hand-signed token with no `aud`
authenticate at `/mcp` in the first place.

**Per-tool authorization** happens after authentication, independent of how
the token was minted: `requireScope` (`internal/mcp/tools.go:1196`) and the
send-gate (`evaluateSendGate`, `internal/mcp/tools.go:1147`) check
`id.HasScope(...)` against the tool being called. A token with only
`telegram:dialogs:read` + `telegram:messages:read` scopes already cannot
invoke send/pin tools today — the *scope* enforcement point already exists.
What is missing is a bounded way to mint such a token that stays out of
`OAUTH_JWT_SIGNING_KEY`'s hands and cannot silently pick up write scopes or
a multi-year TTL.

## Proposed solution

Add a fourth mint path, `POST /api/mcp/worker-token`, modeled directly on
`NewAgentTokenHandler` but scoped to read-only MCP workers:

- **New package `internal/workertoken`** (not `internal/agentapi`): the
  agent-token handler lives in `agentapi` because it is one admin action
  inside the larger communication-agent feature area (job queue, profiles,
  kill switch) that package otherwise implements. A read-only MCP worker
  token is conceptually unrelated to that feature — it authenticates at
  `/mcp`, not `/api/agent/v1` — so it gets its own small package, the same
  way `bridge` has its own token handler file separate from `agentapi`
  despite both being "admin mints a scoped JWT" patterns.
- **Handler**: `workertoken.NewHandler(secret []byte, issuer string) http.HandlerFunc`,
  same signature shape as `NewAgentTokenHandler`/`NewBridgeTokenHandler`
  (constructs its own `localjwt.Issuer`). Request body:
  ```go
  type mintWorkerTokenRequest struct {
      TelegramID int64    `json:"telegram_id"`
      Scopes     []string `json:"scopes,omitempty"`   // defaults to allowedReadOnlyScopes
      TTLHours   int      `json:"ttl_hours,omitempty"`
  }
  ```
  Validation, in order: `admin:users` scope required (403 otherwise, same as
  `NewAgentTokenHandler`) → `telegram_id > 0` required (400) → every entry in
  `Scopes` (or the default set, if omitted) must be a member of
  `allowedReadOnlyScopes = []string{"telegram:dialogs:read", "telegram:messages:read"}`;
  any other value is a 400 with no token minted → `ttl_hours`, if given,
  clamped to `maxWorkerTokenTTL` exactly like `maxAgentTokenTTL` is clamped
  today.
- **Minted claims**: `Subject: "tg:" + telegramID`, `TelegramID: telegramID`,
  `Scopes: <validated set>`, `Audience: []string{"mcp-worker-ro"}`. The `aud`
  value is new and distinct from both the interactive flow's "no aud" and
  `"agent"`/`"bridge"`. It is not used to route to a different endpoint (this
  token is verified by the same `selectProvider` provider already mounted at
  `/mcp`) — its purpose is forensic and future-proofing: it lets a log line,
  an audit query, or a future revocation list identify "this credential was
  minted by the bounded worker path" versus a normal user session, without
  requiring a new provider or a new mount point. Because `OAUTH_JWT_AUDIENCE`
  defaults to `""` (check disabled) and `OAUTH_JWT_AUDIENCE_REQUIRED` defaults
  to `false`, this token authenticates at `/mcp` today exactly like any other
  locally-issued JWT — no config change required to adopt it. (See Platform
  impact for the one interaction to watch if an operator later tightens
  `OAUTH_JWT_AUDIENCE`.)
- **TTL**: `defaultWorkerTokenTTL = 30 * 24 * time.Hour`,
  `maxWorkerTokenTTL = 90 * 24 * time.Hour` — copied from
  `internal/agentapi/tokenhandler.go`'s existing constants rather than
  invented fresh, since that is the one place in this codebase that has
  already made the "how long should a non-interactive, admin-minted worker
  credential live" judgment call. Both orders of magnitude smaller than the
  year-long token this issue is about.
- **Mount point**: `cmd/server/main.go`, next to the existing
  `/api/agent/token` and `/api/bridge/token` registrations:
  ```go
  if secret := cfg.OAUTHJWTSecret; secret != "" {
      mux.With(auth.Middleware(provider, true, m, resourceMeta)).Post("/api/mcp/worker-token",
          workertoken.NewHandler([]byte(secret), selectAgentIssuer(cfg)))
  }
  ```
  Reuses `selectAgentIssuer(cfg)` as the issuer function — it already
  computes exactly "the issuer this deployment's locally-issued JWTs use"
  (`PublicBaseURL` for local-jwt mode, `https://api.mctl.ai` for
  shared-hmac), with no dependency on the agent feature despite the name.
  Renaming it to something feature-neutral (e.g. `selectLocalJWTIssuer`) is
  a reasonable follow-up but out of scope here to keep the diff minimal and
  reviewable.
  Gated on `secret != ""`, identical to the two existing mint endpoints —
  this deployment already requires `OAUTH_JWT_SECRET` for `/mcp` itself to
  work, so this is not a new operational requirement.
- **No new `auth.Provider`, no new verification path.** This is the key
  difference from the agent/bridge pattern and is deliberate: those two
  mint distinct-audience tokens *because* they authenticate at a
  differently-secured endpoint (`/api/agent/v1`, `/bridge`) that must reject
  ordinary MCP tokens. A read-only worker token's entire purpose is to
  authenticate at the *same* `/mcp` endpoint ordinary users already reach,
  just with a restricted scope set and a bounded TTL. Introducing a second
  `/mcp`-equivalent path would fragment the MCP tool surface for no benefit,
  since scope enforcement (`requireScope`) already runs per-tool regardless
  of mint path.
- **Logging**: `slog.Info("worker token minted", "admin_user_id", id.UserID,
  "target_tg_id", req.TelegramID, "scopes", scopes, "ttl", ttl)` — same shape
  as the existing `agent token minted` / `bridge token minted` lines, closing
  the "no record that minting happened" gap the manual-signing path has today.
- **Operational follow-up (doc only, no code)**: update
  `docs/runbooks/canary.md`'s "Token expired" mitigation to say "mint a new
  token via `POST /api/mcp/worker-token`" instead of "rotate the canary
  bearer in the Secret" with no indication of how the value was produced.

## Alternatives

1. **Add `aud: "mcp"` handling to the existing `NewAgentTokenHandler` /
   `/api/agent/token`, with a scope parameter.** Rejected: that handler's
   entire request/response contract, its doc comment, and its mount point
   are wired specifically to the communication-agent feature
   (`cfg.AgentEnabled` gates its sibling routes, though the token endpoint
   itself is mounted unconditionally when `AgentEnabled`; see
   `cmd/server/main.go:454`). Overloading it with a second audience and a
   second scope-validation branch makes one handler responsible for two
   unrelated authorization surfaces, which is exactly the kind of coupling
   `selectAgentProvider`'s doc comment (`cmd/server/main.go:816`) warns
   against ("a bridge token or a regular MCP token must not authenticate
   against the agent surface, and vice versa").
2. **Teach `cmd/canary` the OAuth refresh-token grant (issue's option 1).**
   Rejected for this proposal, per the issue's own analysis: it requires the
   canary's Kubernetes secret to become mutable (the canary would need to
   write back a rotated refresh token after every run, per the reuse-
   detection semantics in `internal/db/refresh_tokens.go`), and it requires
   granting the canary write access to its own credential store — a bigger
   change to a binary explicitly designed to be "a black-box HTTP client"
   with "no imports from .../internal/" (`cmd/canary/main.go:6`). Also does
   not generalize to a future read-only worker that is not `cmd/canary`
   specifically.
3. **Shorten the manually-signed token's TTL and add a renewal reminder
   (issue's option 3).** Rejected, matching the issue's own conclusion: this
   is the least work but leaves the core problems unaddressed — no scope
   allowlist (an operator could still fat-finger a write scope into the
   hand-signed claims), no audit trail of mint events, and continued direct
   use of `OAUTH_JWT_SIGNING_KEY` by a human for routine operations.
4. **Reuse `aud: "agent"` and mount the worker token consumer at
   `/api/agent/v1` instead of `/mcp`.** Rejected: the canary calls the real
   MCP JSON-RPC surface (`initialize`, `tools/call` for `list_dialogs`,
   `get_unread_messages` — see `cmd/canary/main.go:227` and `:303`), which is
   `/mcp`, not the communication-agent job-queue REST API implemented by
   `internal/agentapi/server.go`. There is no tool overlap between the two
   surfaces; redirecting the canary to `/api/agent/v1` would mean
   reimplementing MCP-shaped probes against a REST API that does not expose
   `list_dialogs` at all.

## Platform impact

- **Migrations**: none. No new tables — the minted token is a stateless JWT,
  same as every other `localjwt`-issued token; `localjwt.Provider.Authenticate`
  already lazily calls `EnsureUserByTelegramID` on first use
  (`internal/auth/localjwt/issuer.go:232`), which the worker token gets for
  free with no schema change.
- **Backward compatibility**: fully additive. The existing manually-signed
  canary token keeps working until its (already-issued) `exp` — nothing in
  this proposal invalidates it early, since there is still no revocation
  mechanism (#399). The new endpoint is opt-in; no existing route or token
  shape changes.
- **Resource impact**: negligible — one more `chi` route registered
  conditionally on `OAUTH_JWT_SECRET != ""`, no new background goroutines, no
  new dependencies.
- **Risks + mitigations**:
  - *Risk*: an operator later sets `OAUTH_JWT_AUDIENCE` to a single fixed
    value (e.g. tightening `/mcp` to require `aud` for defense-in-depth)
    without including `"mcp-worker-ro"`, silently breaking every
    already-minted worker token. *Mitigation*: document the `aud` value
    prominently in the new handler's doc comment (mirroring how
    `selectBridgeIssuer`/`selectAgentIssuer` already carry "must stay in
    lockstep" comments), and call it out in the canary runbook as the first
    thing to check if `mcp_init` starts failing for every worker at once
    after an `OAUTH_JWT_AUDIENCE` config change.
  - *Risk*: the 30-day default / 90-day ceiling is still long enough that a
    leaked token has a wide exploitation window, and there is still no
    revocation. *Mitigation*: this is explicitly the residual risk the issue
    accepts by choosing option 2 over option 1 — bounding TTL and scope is
    strictly better than the status quo (one-year, unbounded-scope,
    unlogged) without requiring #399 (revocation) to land first. An operator
    who wants a tighter bound can pass `ttl_hours` down to a value as small
    as they like; the ceiling only bounds the maximum, not the minimum.
  - *Risk*: scope-allowlist drift — if a future PR adds a new
    `telegram:*:read`-shaped scope (e.g. `telegram:profile:read`) and forgets
    to add it to `allowedReadOnlyScopes`, the mint endpoint would reject
    valid read-only requests (fails closed, not open — safe direction to
    fail, but an availability annoyance). *Mitigation*: call this out in a
    code comment on `allowedReadOnlyScopes` pointing at
    `internal/oauth/scopes.go`'s `DCRNegotiableScopes` as the place new
    scopes get introduced, so a reviewer adding a scope there is prompted to
    check this list too.
