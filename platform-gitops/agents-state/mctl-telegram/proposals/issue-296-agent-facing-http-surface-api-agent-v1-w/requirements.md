# Agent-facing HTTP surface /api/agent/v1 with aud=agent JWT (communication agent, A-PR6)

## Context

Issue #296 asks for a new, restricted HTTP surface under `/api/agent/v1` that
the communication agent's worker process (a headless Option-C worker per
#298, or an experimental Channels adapter) uses to poll for Telegram events,
read conversation/lead/policy state, and propose the narrow set of actions
the agent is allowed to take (reply, save a lead, ask the owner for
approval, send an owner summary, pause autopilot, complete a job). The
surface must authenticate with its own JWT audience (`aud=agent`), fail
closed against any other token (bridge, regular MCP, or none), and never
accept a client-supplied peer for outbound sends — the server derives the
peer from the conversation row so there is no generic "send to arbitrary
peer" primitive anywhere on this surface.

**This is a re-investigation, not a from-scratch design.** A prior proposal
for this same issue (dated 2026-07-19, still on disk in this proposal
directory before this rewrite) was grounded in a snapshot of the repository
that had no `internal/agentapi` package at all. The current clone (checked
out 2026-07-24, HEAD `e4e7928`) already contains a essentially complete
implementation: package `internal/agentapi` (10 files, ~2100 lines including
tests), mounted at `/api/agent/v1` in `cmd/server/main.go` behind
`cfg.AgentEnabled` (`AGENT_ENABLED`), with a dedicated `aud=agent` JWT
provider (`selectAgentProvider`) and a dedicated admin-only mint endpoint
(`POST /api/agent/token`, `internal/agentapi/tokenhandler.go`). Every
endpoint the issue lists exists and is wired (`internal/agentapi/server.go`
`Register`). This proposal therefore documents the existing implementation
against the issue's acceptance criteria, confirms what is already correct
(most of it, with tests), and calls out the concrete, verified gaps a Tier 2
implementer should close: two behavioral discrepancies from the issue text
(audit-log naming, HTTP status code on cross-audience rejection) and three
missing test scenarios the issue explicitly asks for.

Why it matters: this surface is the *only* channel the communication agent
has to mctl-telegram data or Telegram sends (per the package doc comment in
`internal/agentapi/server.go`). Any gap between the issue's stated
invariants and what is actually enforced/tested is a security-relevant gap,
not a cosmetic one — the whole point of A-PR6 is that the agent cannot reach
Telegram except through this narrow, audited, policy-gated door.

## User stories

- AS the communication agent worker (#298's headless process) I WANT to
  long-poll for the next due job and fetch its full event body SO THAT I can
  decide how to respond without polling the general MCP surface or holding a
  standing websocket.
- AS the communication agent worker I WANT to propose a reply, save a lead,
  ask the owner for approval, or send an owner summary through narrow,
  purpose-built endpoints SO THAT I can never be tricked (by a bad model
  output or a compromised prompt) into sending to an arbitrary peer.
- AS a platform operator I WANT to mint a long-lived `aud=agent` credential
  for one specific Telegram account, scoped to nothing else, SO THAT a
  deployed worker's credential cannot be replayed against `/mcp` or
  `/bridge`, and a leaked bridge/MCP token cannot be replayed against the
  agent surface.
- AS a security reviewer I WANT every state-changing agent call recorded in
  the existing hash-chained audit log under a name that is unambiguously
  attributable to this surface SO THAT I can distinguish agent-initiated
  actions from human/MCP-initiated ones in `LogToolCall` output without
  cross-referencing source code.
- AS the Tier 2 implementer picking this up next I WANT a precise list of
  what is done, verified, and still open SO THAT I do not re-implement
  working code or, worse, assume untested code paths are safe.

## Acceptance criteria (EARS)

Auth and audience isolation:
- WHEN a request to any `/api/agent/v1/*` route carries a JWT with `aud`
  other than `"agent"` (including a valid `aud=bridge` or generic MCP token)
  THE SYSTEM SHALL reject the request and grant no access to agent data or
  actions. (Implemented: `selectAgentProvider` + `localjwt.CheckAudience`,
  `cmd/server/main.go`. Currently surfaces as HTTP 401 via
  `auth.Middleware`'s generic `Authenticate` error path, not 403 — see Open
  questions.)
- WHEN a request to `/mcp` or `/bridge` carries a JWT with `aud="agent"` THE
  SYSTEM SHALL reject it the same way, for the same reason (their providers'
  `ExpectedAudience` do not include `"agent"`).
- IF `AGENT_ENABLED` is false THEN THE SYSTEM SHALL NOT mount
  `/api/agent/v1` at all (verified: `cmd/server/main.go`'s `if
  cfg.AgentEnabled { ... }` block; default `false`,
  `internal/config/config.go`).
- WHEN `POST /api/agent/token` is called THE SYSTEM SHALL require the
  caller to be authenticated on the *regular* MCP auth chain and hold the
  `admin:users` scope, and SHALL mint a token for the `telegram_id` supplied
  in the request body (not the caller's own identity) with `aud="agent"`.
  This endpoint SHALL NOT be reachable from `/api/agent/v1` itself.
- IF `OAUTH_JWT_SECRET` is unset in a JWT-based `AUTH_MODE` THEN THE SYSTEM
  SHALL fail closed on the agent surface (`rejectAllProvider`), not fall
  back to an unauthenticated or globally-shared provider.

Endpoints (`internal/agentapi/server.go` `Register`, all implemented):
- WHEN `GET /events` is polled THE SYSTEM SHALL hold the connection for up
  to the configured long-poll window (production default 20s, under the
  60s router timeout) and return `{"jobs": []}` with HTTP 200 on timeout,
  never an error status.
- WHEN `GET /events` claims one or more due jobs THE SYSTEM SHALL return,
  per job, `job_id`, `event_id`, `conversation_id`, an `attempt` fencing
  counter, and an advisory `deadline` (RFC3339) derived from the claim time
  plus the configured job-visibility window.
- WHEN a job is claimed by one caller THE SYSTEM SHALL NOT let a concurrent
  or subsequent poll (by the same or another account) claim it again while
  it remains within its visibility window, and SHALL NOT let a caller
  authenticated for account A see or claim account B's jobs.
- WHEN `GET /event/{id}` is called for a job that does not belong to the
  caller's account THE SYSTEM SHALL return 404, not another account's data.
- WHEN `POST /actions/propose_reply` is called THE SYSTEM SHALL derive the
  outbound peer exclusively from the `conversation_id`'s stored `peer_tg_id`
  server-side. The request schema SHALL NOT accept any peer-identifying
  field, and no code path SHALL honor one even if a client sends it (backed
  by `decodeStrict`'s `DisallowUnknownFields`).
- WHEN `POST /jobs/{id}/complete` is called with `status=completed` THE
  SYSTEM SHALL reject the call (409) unless a durable result already exists
  for that job (`agent_actions` row via `HasAgentActionForJob`, or a saved
  lead via `HasJobLeadForJob`) — an ack alone is never sufficient to close a
  job.
- WHEN `POST /jobs/{id}/complete` is called with a stale `attempt` value
  (the job was reclaimed by the sweeper after a visibility timeout) THE
  SYSTEM SHALL return 409, not silently accept the late ack.
- WHEN `GET /recruiters/{peer}` is called and no `OwnerProfileProvider` is
  configured THE SYSTEM SHALL return 501, not 500 or a fabricated profile
  (current state: no provider is wired yet — see Open questions, dependency
  on #297).
- WHEN any POST body fails to decode (malformed JSON, wrong field types, or
  a field not in the schema) THE SYSTEM SHALL respond 400 with a stable
  `{"error": "..."}` shape, and SHALL NOT respond 500 for caller input
  errors.
- WHEN any handler encounters an unexpected internal error (DB failure,
  etc.) THE SYSTEM SHALL log it via `slog` without message bodies, phone
  numbers, or secrets, and respond with a generic 500 body that does not
  leak internals.

Audit:
- WHEN any `/api/agent/v1` handler completes a request (success, denial, or
  domain-level failure) THE SYSTEM SHALL record it via
  `Store.LogToolCall`, the same hash-chained audit mechanism every other
  privileged surface in this codebase uses.
- IF an audit log entry originates from this package THEN its `tool` field
  name SHALL be prefixed `agent.` (e.g. `agent.propose_reply`) per the
  issue's explicit requirement, so it is distinguishable from MCP-tool and
  bridge audit entries without inspecting source. **Not currently true**:
  see Open questions / Out of scope boundary below — this is a confirmed
  gap, not a design choice.

Policy integration:
- WHILE the process-wide `AGENT_KILL_SWITCH` is engaged THE SYSTEM SHALL
  deny every state-changing action on this surface, including owner-facing
  notifications, not only outbound replies (verified by
  `TestHandleOwnerFacing_KillSwitchBlocksNotification`).
- WHEN the same job is redelivered to a worker after a crash (worker died
  after `propose_reply`/`notify/summary` but before `jobs/{id}/complete`)
  THE SYSTEM SHALL return the same action id / approval code / notification
  id as the original call, not create a duplicate (idempotent on
  `(job_id, action_type)`; verified by
  `TestHandleProposeReply_RedeliveryReturnsSameApprovalCode` and
  `TestHandleOwnerFacing_RedeliveryDoesNotDuplicateNotification`).

## Out of scope

- Implementing `OwnerProfileProvider` itself (the real profile-fetch +
  restricted-field stripping logic) — that is #297 (A-PR7). This surface
  already has the seam (`agentapi.OwnerProfileProvider` interface,
  `Server.WithProfile`) and a safe 501 default; wiring a concrete
  implementation is explicitly out of scope for #296 per the issue body.
- The headless Option-C worker process itself and the experimental Channels
  adapter (#298) — this surface is transport-agnostic and consumed
  identically by both; neither consumer is built in this proposal.
- Changing the job-queue, listener, or policy-engine semantics
  (`internal/agent/queue`, `internal/agent/listener`,
  `internal/agent/policy`) — those are `#286/#288/#289/#299/#290`, already
  merged, and this proposal treats them as fixed dependencies to be reused,
  not modified, except where a task below explicitly says otherwise.
- Rate limiting / quota enforcement beyond what `internal/agent/policy`
  already evaluates (per-conversation messages-per-minute). A true
  account-wide rate limit is called out as a possible future need in
  `internal/agentapi/actions.go`'s `recentAgentSends` doc comment but is not
  part of this proposal.
- Deleting or rewriting the prior (2026-07-19) proposal's historical
  record outside of this directory — only this directory's three files are
  replaced, per the task instructions.

## Open questions

1. **403 vs 401 on cross-audience rejection.** The issue text says
   "cross-audience tokens must 403, not just be ignored." The current
   implementation fails closed correctly (a bridge/MCP token is rejected,
   never silently treated as anonymous) but does so via
   `auth.Middleware`'s generic `Authenticate` error branch, which returns
   401 for every provider-level rejection (bad signature, expired, wrong
   issuer, *and* wrong audience alike — see `internal/auth/middleware.go`).
   There is no code path in this codebase, on any of the three JWT
   audiences (MCP/bridge/agent), that returns 403 for an audience mismatch;
   403 is reserved elsewhere for scope failures on an otherwise-valid
   identity (e.g. `tokenhandler.go`'s `admin:users` check). Interpretation
   used in this proposal: the issue's real intent — "must be hard-rejected,
   not silently dropped" — is satisfied today (it is a 401, not a 200 or a
   silent no-op), and changing 200+ providers' shared middleware to special
   case audience-mismatch as 403 would be a cross-cutting change well beyond
   this package. Tasks below record this as a documentation/test task
   (assert and pin the current 401 behavior with an explicit end-to-end
   test) rather than a code change, but flag it for human sign-off since the
   issue text is explicit about the status code.
2. **`agent.<name>` audit prefix.** Confirmed gap (see Acceptance criteria
   above and design.md) — `internal/agentapi/json.go`'s `audit` helper and
   every call site pass bare tool names (`"get_events"`, `"propose_reply"`,
   `"save_job_lead"`, etc.) with no `agent.` prefix, unlike the issue's
   explicit `agent.<name>` convention. Resolved as a concrete task, not left
   open, since it is unambiguous and low-risk to fix.
3. **No end-to-end (real JWT + real chi mount) test exists for audience
   isolation.** `internal/agentapi/server_test.go` bypasses
   `auth.Middleware` entirely (it injects `*auth.Identity` straight into the
   request context), so none of the 20+ tests in that file actually prove a
   bridge-minted or MCP-minted token is rejected by the mounted
   `/api/agent/v1` router, or that an agent-minted token is rejected by
   `/mcp`/`/bridge`. `cmd/server/main_test.go` only covers
   `selectProvider`'s `AUTH_MODE` switch, not `selectAgentProvider`'s, and
   has no HTTP-level test at all. This is the single largest verified test
   gap against the issue's explicit requirement ("aud enforcement: ...
   bridge/API tokens must 403 here, and agent tokens must 403 on non-agent
   routes"). Resolved as a task, not left open.
4. **Schema-validation edge cases are only partially covered.** The issue
   asks for "schema validation edge cases" as an explicit test category.
   Today's tests exercise domain-level 400s (bad `limit=`, bad
   `status=`, empty `text`) but no test sends a malformed JSON body or a
   body with an extra/unknown field to confirm `decodeStrict`'s
   `DisallowUnknownFields` + `MaxBytesReader` actually produce the required
   400-not-500 behavior end to end. Resolved as a task.
5. **`GET /recruiters/{peer}` is stubbed pending #297.** Not ambiguous —
   the issue and the code agree this is expected (`OwnerProfileProvider`
   nil-safe, 501 today) — recorded here only so the Tier 2 implementer does
   not mistake the 501 for a bug.

None of the above block proceeding: each has a concrete, reasonable
resolution captured in tasks.md.
