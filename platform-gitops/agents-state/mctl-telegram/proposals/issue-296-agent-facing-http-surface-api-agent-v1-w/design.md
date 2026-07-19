# Design: issue-296-agent-facing-http-surface-api-agent-v1-w

## Current state

**Auth stack.** `internal/auth/identity.go` defines `auth.Provider` (one
method: `Authenticate(*http.Request) (*Identity, error)`) and
`auth.Middleware` (`internal/auth/middleware.go`), which wraps any handler,
calls the provider, and either 401s or injects `*Identity` into the request
context via `auth.With`/`auth.From`. `internal/auth/localjwt/issuer.go`
implements both sides: `Issuer.Mint(Claims, ttl)` signs HS256 JWTs with a
polymorphic `aud` claim, and `Provider.Authenticate` verifies signature +
issuer + expiry + audience (`CheckAudience`) and then resolves the token's
`tg_id` to an internal `user_id` via `Store.EnsureUserByTelegramID`. This
exact machinery is already reused three times with three different
audiences:

- MCP: `selectProvider` builds a `localjwt.Provider` with
  `ExpectedAudience: cfg.OAUTHJWTAudience` (operator-configured, typically
  unset/generic).
- Bridge: `selectBridgeProvider` (`cmd/server/main.go:595-637`) builds a
  *separate* `localjwt.Provider` with `ExpectedAudience: "bridge"` and
  `AudienceRequired: true`, hard-coded (not operator-configurable) so a
  regular MCP token can never authenticate `/bridge`. Bridge tokens
  themselves are minted only after the caller already holds a valid MCP
  token, via `POST /api/bridge/token`
  (`internal/bridge/tokenhandler.go`), guarded by
  `auth.Middleware(provider, true, m)`.
- Local-dev: `local-dev` mode returns a fixed operator identity from
  `localdev.New` for every provider selector, including the bridge one,
  so the whole chain works without an OAuth issuer.

**Communication-agent data model.** `internal/db/agent_schema.go` defines
seven tables (`agent_profiles`, `incoming_events`, `conversations`,
`conversation_messages`, `agent_actions`, `job_leads`,
`owner_notifications`), all scoped by `user_id -> users(id)`. Typed access
lives in three files:

- `internal/db/agent_domain.go`: `AgentProfile` CRUD
  (`UpsertAgentProfile`, `GetAgentProfile`, `SetAgentAutopilotPaused`,
  `ListListenerEnabledProfiles`), `Conversation` CRUD (`EnsureConversation`,
  `GetConversation`, `GetConversationByPeer`, `SetConversationState`,
  `IncrementAutonomousTurns`, `ResetAutonomousTurns`,
  `TouchConversationIncoming`), and `ConversationMessage` writes/reads
  (`InsertConversationMessage`, `ListConversationMessages`).
- `internal/db/agent_events.go`: `IncomingEvent` (`InsertIncomingEvent` —
  idempotent via a unique `event_id` index, `GetIncomingEvent`,
  `SweepAgentMessageBodies` for retention). There is **no** "list events
  since X for user" query yet — only point lookup by `event_id`.
- `internal/db/agent_actions.go`: `AgentAction` state machine
  (`InsertAgentAction`, `GetAgentAction`/`GetAgentActionByCode`,
  `UpdateAgentActionStatus` — a compare-and-set on `(from, to)` — plus
  `SetAgentActionExecuted`, `ExpireStaleAgentActions`), `JobLead` CRUD, and
  `OwnerNotification` writes (`InsertOwnerNotification`,
  `MarkOwnerNotificationSent/Failed`). Body/payload columns
  (`incoming_events.body_encrypted`, `agent_actions.payload_encrypted`,
  `conversation_messages.body_encrypted`) are sealed with
  `crypto.SealForUser`, matching the pattern `session_encrypted` already
  uses (`internal/crypto`).

Constants already encode the intended policy state machine:
`AgentModeObserve/Guarded/Off`, `ConversationActive/Paused/TakenOver/Closed`,
`ActionProposed -> PendingApproval -> Approved -> Executing -> Executed`
(with `Rejected`/`Expired`/`Denied` off-ramps), and
`PolicyAllow/RequireApproval/Deny`. The doc comment on `AgentProfile`
explicitly states: "All limits are enforced server-side by the policy
engine; the profile row is the single source of truth" and on `AgentAction`:
"the agent process itself never enforces it" — i.e. by design, whatever
calls into this data model is not trusted to self-report policy.

**Consumers today: none.** `grep -rn "agent_actions\|incoming_events\|AgentProfile" internal/mcp internal/web`
returns no matches. `internal/telegram/agentruntime.go` defines the
`AgentRuntime` interface (`HandlerFor`, `RunFor`) that `ClientPool` will
call into (`WithAgentRuntime`, landed in PR #289), plus `Pin`/`Unpin` to
exempt a listening user's pool entry from idle GC — but no concrete
implementation exists in this clone, and its own comment says the runtime
"lives outside the pool (internal/agent/listener)", a package that does not
exist yet. Nothing in `cmd/server/main.go` wires an `AgentRuntime` today.

**HTTP mounting pattern.** `cmd/server/main.go` shows the established
recipe for a new authenticated JSON surface, used verbatim by `/api/account`
(lines 258-263):

```go
accountMux := chi.NewRouter()
accountHandlers := web.NewAccountHandlers(store, pool)
accountHandlers.Register(accountMux)
mux.Mount("/api/account", auth.Middleware(provider, true, m)(accountMux))
```

`web.AccountHandlers` (`internal/web/account.go`) is a small struct holding
`*db.Store` (+ a narrow interface for whatever else it needs), a
`Register(mux)` method binding relative routes, per-handler
`auth.From(r.Context())` + `writeAccountErr`/`writeAccountJSON` helpers, and
an `h.audit(...)` call after every operation that writes through
`Store.LogToolCall` — the same audit trail MCP tool calls use, surfaced via
`GET /api/account/audit`.

## Proposed solution

Add a new `internal/agentapi` package (sibling to `internal/web`,
`internal/bridge`) that mirrors the `web.AccountHandlers` shape, plus a
fourth `localjwt.Provider` audience (`"agent"`) selected the same way the
bridge provider is selected today.

**1. New audience + provider selector — `cmd/server/main.go`.**
Add `selectAgentProvider(cfg, store) auth.Provider`, structurally identical
to `selectBridgeProvider` (lines 595-637): a `localjwt.Provider` with
`ExpectedAudience: "agent"`, `AudienceRequired: true`, keyed off the same
`AUTH_MODE` switch (`local-jwt` / `shared-hmac(-legacy)` / `local-dev`
fallback to `localdev.New`), and the same fail-closed `rejectAllProvider`
when `OAUTH_JWT_SECRET` is unset. This reuses 100% of the existing
verification code path (`localjwt.Verify` + `CheckAudience`); the only new
runtime cost is one more `Provider` struct.

**2. Token issuance — no new public endpoint (see Open question 1).**
Because the communication-agent runtime is designed to run in-process
(`AgentRuntime` wired directly into `telegram.ClientPool`), token minting
happens server-side: `main.go` constructs one `localjwt.Issuer` (same
secret/issuer as everything else) and, when/where the future
`internal/agent/listener` package starts a user's listener loop, it mints
a short-lived (e.g. 15m, refreshed on demand — shorter than the 1h
`bridgeTokenTTL` since the caller is local and can re-mint cheaply) token
with `Audience: []string{"agent"}` and the user's `tg_id`/`tg_username`,
the same `Claims` struct the bridge path already uses. This PR adds the
issuer wiring and the `Mint`-based helper (e.g.
`agentapi.MintToken(issuer, userTGID, ttl)`) but the actual listener
integration is out of scope (see requirements.md).

**3. Handlers — `internal/agentapi/handlers.go`.**
A `Handlers` struct holding `*db.Store` (and nothing else — no pool, no
crypto needed directly since `Store` already handles seal/unseal), with
`Register(mux)` binding these routes (mounted at `/api/agent/v1`):

```
GET  /api/agent/v1/profile                 -> AgentProfile (mode, limits, disclosure text)
GET  /api/agent/v1/events?since_id=N&limit=  -> []IncomingEvent, ordered by id
GET  /api/agent/v1/conversations/{id}       -> Conversation + recent messages
GET  /api/agent/v1/conversations/{id}/messages?since_id=&limit=
POST /api/agent/v1/actions                  -> propose an action; server computes policy_decision
GET  /api/agent/v1/actions/{id}             -> current AgentAction row
POST /api/agent/v1/actions/{id}/execute     -> approved -> executing -> executed transition
POST /api/agent/v1/notifications            -> record an owner_notifications row (e.g. summary queued)
```

Every handler:
- Reads `id := auth.From(r.Context())`; 401s defensively if nil (should be
  unreachable given `auth.Middleware(provider, true, m)` in front, same
  defensive pattern `NewBridgeTokenHandler` already uses).
- Scopes every `Store` call to `id.UserID` — never accepts a caller-supplied
  user id, closing the cross-account read/write path called out in
  requirements.md.
- Calls `h.audit(r, id, "<verb> /api/agent/v1/...", err)` on the way out,
  reusing the exact `Store.LogToolCall` audit chain `web.AccountHandlers`
  already writes to, so agent activity is visible via the existing
  `get_my_auditLog` MCP tool and `GET /api/account/audit` without adding a
  second audit mechanism.
- Never logs `slog` attributes named `body`/`payload`/`text`/
  `proposed_text` (all already in `sensitiveKeys`,
  `internal/audit/redact.go`) with raw content — only ids/status/lengths.

**4. Server-side policy evaluation — `internal/agentapi/policy.go`.**
`POST /api/agent/v1/actions` cannot trust a caller-supplied
`policy_decision` (requirements.md AC3-AC4). Add a small pure function:

```go
func evaluate(profile *db.AgentProfile, actionType, intent string, replyChars int, blocked bool) (decision string, reasons []string)
```

implementing exactly what the existing doc comments promise: `mode=="off"`
or `AutopilotPaused` -> `PolicyDeny`; sender in `BlockedSenders` -> `PolicyDeny`;
`replyChars > MaxReplyChars` -> `PolicyDeny` (or truncate + `RequireApproval`,
TBD by implementer — flagged as an implementation detail, not a contract
change); `mode=="guarded"` and `intent` in `IntentAllowlist` -> `PolicyAllow`;
otherwise -> `PolicyRequireApproval`. This is intentionally the minimal
version of "the policy engine" the doc comments already promise, not a new
pluggable framework — `MaxMsgsPerMinute`/`MaxAutonomousTurns` rate/turn
enforcement is explicitly deferred (see Out of scope) since it needs
call-site data (recent send timestamps, current `conversations.autonomous_turns`)
this PR's handler already has access to via `Store` but which is reasonable
to land as a fast-follow once the first policy pass is proven out.

**5. New `Store` query — `ListIncomingEventsSince`.**
`agent_events.go` currently only supports point lookup
(`GetIncomingEvent` by `event_id`). `GET /api/agent/v1/events` needs a
ranged, ordered, paginated query scoped by `user_id`. Add:

```go
func (s *Store) ListIncomingEventsSince(ctx context.Context, userID, sinceID int64, limit int) ([]IncomingEvent, error)
```

mirroring the existing `ListConversationMessages`/`ListJobLeads` shape
(`ORDER BY id ASC LIMIT ?`, decrypt each row's `body_encrypted` the same
way `GetIncomingEvent` already does). This is additive — no schema
migration needed, `idx_incoming_events_created_at` already exists but the
handler should filter/sort on the primary key `id` for stable cursoring
rather than `created_at` (multiple rows can share a timestamp).

**6. Route mounting — `cmd/server/main.go`.**
Immediately after the existing `/api/account` mount block:

```go
agentProvider := selectAgentProvider(cfg, store)
agentMux := chi.NewRouter()
agentapi.NewHandlers(store).Register(agentMux)
mux.Mount("/api/agent/v1", auth.Middleware(agentProvider, true, m)(agentMux))
```

`auth.Middleware`'s `required` is always `true` here (unlike the MCP
mount, which honors `cfg.AuthRequired` for anonymous local-dev testing) —
an agent-facing surface with direct Telegram-send capability should never
be reachable anonymously, matching `/bridge` and `/api/account`'s posture
rather than `/mcp`'s.

## Alternatives

1. **Extend the existing MCP tool surface with `agent_*` tools instead of a
   new HTTP surface.** Rejected: MCP tools authenticate with the general
   MCP JWT (any `aud` the operator configured, typically none), so any MCP
   client (Claude, ChatGPT, ad-hoc curl with a stolen user token) would
   gain the ability to drive the autonomous agent's action queue. The
   issue explicitly asks for a separate `aud=agent`-scoped surface, and
   the codebase's existing pattern (bridge gets its own audience, not new
   MCP tools) supports keeping this separate. It also avoids polluting the
   MCP tool schema (`internal/mcp/tools.go`, already 70KB) with
   internal-plumbing tools no end-user client should ever see or call.

2. **Give the agent runtime direct `*db.Store` access (no HTTP hop at
   all), since `AgentRuntime` already runs in-process.** Rejected for this
   PR: it's the fastest path today, but the issue explicitly asks for an
   HTTP surface with its own JWT audience, which implies the design intends
   to support an out-of-process agent runtime later (a separate worker
   deployment, matching how `/bridge` supports an out-of-process Local
   Bridge daemon). Building the HTTP boundary now — even though the only
   caller in this milestone is in-process — keeps the option open without
   a breaking change later, and forces the policy-evaluation logic to live
   behind a real interface boundary instead of being inlined into whatever
   package ends up running the agent loop.

3. **Reuse `sharedhmac`/a brand-new bespoke auth scheme for the agent
   surface instead of `localjwt` + a new audience.** Rejected: `localjwt`
   already supports arbitrary audiences via `Claims.Audience` +
   `CheckAudience`, and `selectBridgeProvider` already proves the pattern
   composes cleanly with the existing `AUTH_MODE` switch (including
   fail-closed behavior and `local-dev` fallback). Introducing a second
   token format would duplicate `Verify`/`CheckAudience`/`EnsureUserByTelegramID`
   logic for no benefit and would need its own entry in
   `middleware.go`'s `providerName`/`classifyAuthError` helpers.

## Platform impact

- **Migrations:** none required for the route/handler work itself. The one
  new `Store` method (`ListIncomingEventsSince`) is a `SELECT` against an
  existing table/index — no `ALTER TABLE`. If the deferred
  `MaxMsgsPerMinute`/`MaxAutonomousTurns` enforcement lands in this PR
  after all, it still only reads existing columns.
- **Backward compatibility:** fully additive. No existing route, table, or
  `auth.Provider` behavior changes. `local-dev` and `shared-hmac-legacy`
  deployments keep working unchanged; `/api/agent/v1` simply does not get
  meaningfully exercised until something mints an `aud=agent` token, which
  nothing in production does until the (separate, future) listener PR.
- **Resource impact:** negligible — one more `chi` sub-router, one more
  `localjwt.Provider` instance (stateless struct), one more indexed
  `SELECT`. No new background goroutines beyond what a future listener PR
  would add anyway.
- **Risks + mitigations:**
  - *Risk:* a bug in `evaluate()` (policy.go) could let a `guarded`-mode
    action bypass approval and auto-send. *Mitigation:* the compare-and-set
    in `Store.UpdateAgentActionStatus` and the `executing` trap-state
    (already documented in `agent_actions.go`) mean a wrong `allow`
    decision can send at most once per proposed action, never double-send;
    add unit tests enumerating every `(mode, autopilot_paused, blocked,
    over_length)` combination against the documented state machine before
    merge.
  - *Risk:* cross-account data leakage if a handler ever accepts a
    caller-supplied `user_id`. *Mitigation:* every handler derives
    `user_id` exclusively from `auth.From(r.Context()).UserID`; add a test
    that a token minted for user A cannot read user B's `/events` or
    `/conversations/{id}` (expect `404`/`403`, not silent cross-tenant
    return) — this is the same shape of test `internal/bridge` already has
    for the bridge audience.
  - *Risk:* forgetting to wire `selectAgentProvider` into the same
    fail-closed posture as `selectBridgeProvider` (i.e. defaulting to
    `localdev` in an ambiguous config and accidentally accepting
    unauthenticated agent calls in a prod-like deployment).
    *Mitigation:* copy the existing `rejectAllProvider` fallback verbatim
    and add a config test analogous to whatever covers
    `selectBridgeProvider` today (if none exists, add one — currently
    `cmd/server/main_test.go` is only 2100 bytes / likely thin, worth
    checking during implementation).
  - *Risk:* plaintext message content ending up in structured logs via a
    new field name not in `sensitiveKeys`. *Mitigation:* reuse the
    existing key names (`body`, `payload`, `text`, `proposed_text`) for any
    logged attribute that could carry content; do not invent new field
    names for message text.
