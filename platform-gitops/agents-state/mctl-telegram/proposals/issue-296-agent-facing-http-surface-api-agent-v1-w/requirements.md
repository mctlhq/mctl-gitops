# Agent-facing HTTP surface /api/agent/v1 with aud=agent JWT (communication agent, A-PR6)

## Context

`mctl-telegram` is building an autonomous "communication agent" (milestone M6)
that watches a user's Telegram DMs and proposes/sends replies on their behalf
under a policy the user configures. The database side of this feature already
exists: `internal/db/agent_schema.go` defines `agent_profiles`,
`incoming_events`, `conversations`, `conversation_messages`, `agent_actions`,
`job_leads`, and `owner_notifications`, with typed accessors in
`internal/db/agent_domain.go`, `agent_events.go`, and `agent_actions.go`
(confirmed by reading these files). `internal/telegram/agentruntime.go`
already wires a pluggable `AgentRuntime` (`HandlerFor`/`RunFor`) into the
MTProto client pool so a per-user update listener can run inside a pooled
client (landed in PR #289, "pinned pool entries with agent update handlers" —
the only commit visible in this shallow clone, confirming A-PR6 follows
directly after the pool/listener wiring).

What is still missing is any way for the agent's own reasoning process to
read what came in and act on it. There is no HTTP surface, no MCP tool, and
no consumer at all today (`grep` across `internal/mcp` and `internal/web`
for `agent_actions`/`incoming_events`/`AgentProfile` returns nothing outside
the `internal/db` package itself). Issue #296 asks for that surface: a new
`/api/agent/v1` HTTP API, authenticated with a JWT whose `aud` claim is
`"agent"`, so the communication-agent process (in-process goroutine or a
separate worker) can poll for new events and propose/track actions without
reusing the general-purpose MCP tool surface or the user-facing browser
session. The issue body itself was not populated by the reporter (placeholder
text only); this proposal is grounded entirely in the code already in the
repository plus the closest existing precedent — the `aud=bridge` pattern
used by `POST /api/bridge/token` and `GET /bridge`
(`internal/bridge/tokenhandler.go`, `main.go` `selectBridgeProvider`).

This matters because every other privileged channel in this codebase
(`/mcp`, `/bridge`, `/telegram/connect/manage`) already has a scoped
audience and an explicit provider selection function; leaving the agent
runtime to either share the general MCP token (over-broad: MCP callers could
also drive the agent surface) or bypass auth entirely (unacceptable per
CLAUDE.md's "treat all Telegram data as private user data") would break that
established isolation model.

## User stories

- AS the communication-agent runtime I WANT to authenticate to
  `mctl-telegram` with a narrowly-scoped token SO THAT a leaked or misused
  agent credential cannot be replayed against `/mcp`, `/bridge`, or
  `/api/account`.
- AS the communication-agent runtime I WANT to poll for new incoming
  Telegram events for the users it manages SO THAT it can react to DMs
  without holding an MTProto session itself.
- AS the communication-agent runtime I WANT to propose a reply/action and
  have the server independently evaluate it against the user's
  `agent_profiles` policy (mode, intent allowlist, blocked senders, reply
  length) SO THAT the policy is enforced in one place and cannot be
  bypassed by a compromised or buggy agent process (this mirrors the
  existing doc comment in `agent_actions.go`: "the agent process itself
  never enforces it").
- AS the communication-agent runtime I WANT to fetch the status of an
  action it previously proposed, and to mark it executed after a
  successful Telegram send SO THAT the `agent_actions` lifecycle state
  machine stays authoritative in the DB.
- AS the account owner I WANT the agent surface to only ever act within the
  boundaries of my own `agent_profiles` row SO THAT one user's agent token
  can never read or act on another user's conversations.
- AS a platform operator I WANT agent-token issuance and every
  `/api/agent/v1` call to be observable (metrics + audit log) in the same
  way `/api/account` and `/api/bridge/token` already are SO THAT misuse or
  runaway autonomous behavior is visible without needing bespoke tooling.

## Acceptance criteria (EARS)

- WHEN a caller issues a request to any `/api/agent/v1/*` route without a
  valid Bearer token THE SYSTEM SHALL respond `401 Unauthorized` and SHALL
  NOT touch any `agent_*`/`conversations`/`incoming_events` table.
- WHEN a caller presents a JWT whose `aud` claim does not include `"agent"`
  THE SYSTEM SHALL reject the request the same way `selectBridgeProvider`
  rejects a non-`bridge`-audience token on `/bridge` (401, classified as
  `jwt_wrong_audience`/`jwt_missing_audience` by
  `internal/auth/middleware.go`'s `classifyAuthError`).
- WHEN a caller presents a valid `aud=agent` token THE SYSTEM SHALL scope
  every subsequent read/write in that request to the `user_id` resolved
  from the token's `tg_id` claim (via `Store.EnsureUserByTelegramID`, the
  same resolution `localjwt.Provider.Authenticate` already performs) and
  SHALL NOT accept a caller-supplied `user_id` parameter that could target
  a different account.
- WHEN the agent runtime calls `GET /api/agent/v1/events` THE SYSTEM SHALL
  return incoming events for that user ordered by id/created_at with a
  cursor (e.g. `since_id`) so repeated polls do not re-deliver already-seen
  rows.
- WHEN the agent runtime calls `POST /api/agent/v1/actions` with a proposed
  action THE SYSTEM SHALL evaluate the user's current `AgentProfile` (mode,
  `intent_allowlist`, `blocked_senders`, `max_reply_chars`) server-side and
  SHALL persist the resulting `policy_decision`
  (`allow`/`require_approval`/`deny`) itself — the caller-supplied intent
  is an input to the decision, never the decision.
- IF `AgentProfile.Mode` is `"off"` OR `AgentProfile.AutopilotPaused` is
  true THEN THE SYSTEM SHALL deny every proposed auto-send action
  regardless of what the agent runtime requests.
- IF an action's resulting `policy_decision` is `allow` THEN THE SYSTEM
  SHALL permit the agent runtime to transition it through
  `approved -> executing -> executed` via the execute endpoint; IF the
  decision is `require_approval` THEN THE SYSTEM SHALL require the
  existing owner-approval path (Telegram `/mctl approve <code>`, already
  modeled by `ApprovalCode` in `agent_actions.go`) before execution is
  permitted, and the HTTP surface SHALL reject an execute call on a
  `pending_approval` row.
- WHEN the agent runtime calls the execute endpoint for an action already
  in `executing` or a terminal state (`executed`, `rejected`, `expired`,
  `denied`) THE SYSTEM SHALL reject the transition (compare-and-set
  semantics, matching `Store.UpdateAgentActionStatus`'s documented
  `from`/`to` contract) rather than silently double-sending.
- WHILE the communication agent is disabled for a user
  (`ListenerEnabled=false` or no `agent_profiles` row exists) THE SYSTEM
  SHALL still authenticate `/api/agent/v1` calls scoped to that user (so
  the agent runtime can read profile state / discover it is disabled) but
  SHALL reject any action-creating or action-executing call for that user.
- WHEN any `/api/agent/v1` handler completes THE SYSTEM SHALL record an
  audit entry via the same `Store` audit path used by
  `internal/web/account.go` (`h.audit(...)` -> `Store.LogToolCall`) so
  agent activity is visible in `get_my_auditLog` / `/api/account/audit`.
- WHEN message bodies or action payloads pass through `/api/agent/v1`
  handlers or their logging THE SYSTEM SHALL NOT log plaintext content —
  only encrypted-at-rest storage via `crypto.SealForUser` (the existing
  mechanism `InsertIncomingEvent`/`InsertAgentAction` already use) and
  redacted structured logs (existing `sensitiveKeys` in
  `internal/audit/redact.go` already cover `body`/`payload`/`text`/
  `proposed_text`).
- IF `OAUTH_JWT_SECRET` is unset in a mode that would otherwise mount
  `/api/agent/v1` THEN THE SYSTEM SHALL fail closed (mirror
  `selectBridgeProvider`'s `rejectAllProvider` fallback) rather than
  silently downgrading to an unauthenticated or `local-dev` identity.
- WHEN `mctl-telegram` starts in `AUTH_MODE=local-dev` THE SYSTEM SHALL
  still allow an operator to exercise `/api/agent/v1` end-to-end (matching
  how `/bridge` falls back to `localdev.New` in that mode) so local
  development does not require running the full OAuth issuer.

## Out of scope

- The actual agent reasoning/LLM loop that decides *what* to reply
  (`internal/agent/listener`, referenced only as a forward comment in
  `internal/telegram/agentruntime.go`, does not exist yet). This proposal
  only builds the HTTP surface + auth boundary the runtime will call.
- A full standalone "policy engine" package. This proposal requires
  `POST /api/agent/v1/actions` to compute `policy_decision` server-side
  using the fields already on `AgentProfile`, but a richer/pluggable policy
  evaluator (e.g. per-minute rate limiting via `MaxMsgsPerMinute`,
  autonomous-turn ceiling enforcement via `MaxAutonomousTurns`) can be
  extracted into its own package in a follow-up without changing this
  surface's routes or contracts.
- The `agent_jobs` queue table referenced in a code comment
  (`agent_actions.go`: `JobID int64 // agent_jobs.id`) does not exist in
  `agent_schema.go` yet. This proposal does not create it; `job_id` is
  accepted as an optional passthrough field only.
- Rewriting or extending the existing `internal/mcp` tool surface, the
  `/bridge` websocket relay, or `/api/account` self-service endpoints.
- A minting flow analogous to `POST /api/bridge/token` where a *human's*
  browser session exchanges its MCP JWT for an agent token. Given the
  agent runtime in this milestone is expected to run in-process
  (`AgentRuntime` is wired directly into `ClientPool`, not over a network
  boundary), token issuance is assumed to happen server-side at process
  start via a `localjwt.Issuer` call, not via a new public HTTP endpoint.
  This is recorded as an open question below because the issue does not
  specify it.
- Owner-facing UI/dashboard for reviewing agent activity (separate from
  the existing Telegram-native approval flow already implied by
  `ApprovalCode`).

## Open questions

The GitHub issue body was not populated (placeholder only), so the
following are inferred from the codebase and recorded rather than blocking
on:

1. **Where does the `aud=agent` token get minted?** The `bridge` precedent
   mints tokens via an authenticated HTTP endpoint (`POST
   /api/bridge/token`) because the Local Bridge daemon is an external
   process reached over the internet. The communication agent, per
   `AgentRuntime`'s doc comment, is expected to run "outside the pool" but
   inside the same deployment (`internal/agent/listener`, not yet built).
   This proposal assumes an in-process `localjwt.Issuer` call (no new
   public mint endpoint) is sufficient for A-PR6, since exposing a mint
   endpoint before the actual runtime exists would be an unused attack
   surface. If a future PR needs the agent runtime to run as a separate
   deployable, a `/api/agent/token` endpoint analogous to
   `/api/bridge/token` can be added then.
2. **Full endpoint list.** The issue title only says "HTTP surface"; it
   does not enumerate routes. This proposal's design.md proposes the
   minimal set needed to close the loop the DB schema already implies
   (read profile, read events, read/list/create/transition actions, touch
   conversations, record owner notifications). Additional routes (job
   leads CRUD, bulk event acknowledgement) can be added incrementally
   under the same `/api/agent/v1` prefix without a breaking change.
3. **Versioning posture of `v1`.** No other endpoint in this codebase is
   versioned in its path (`/api/account`, `/api/bridge/token` are
   unversioned). This proposal takes the issue's explicit `/api/agent/v1`
   literally and treats `v1` as a fixed path segment now, with `v2`
   reserved for a future breaking change — not as a signal to retrofit
   versioning onto the other `/api/*` surfaces.
4. **Polling vs. push.** This proposal specifies a polling `GET
   /api/agent/v1/events?since_id=` contract because there is no existing
   push/streaming mechanism between an in-process runtime and its own
   host process's HTTP server (SSE/websocket would be unusual for
   same-process communication). If the runtime ends up out-of-process,
   this can be revisited.
