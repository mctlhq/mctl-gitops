# Agent-channel stdio MCP bridge binary (cmd/agent-channel)

## Context

The MCTL Communication Agent workstream runs a dedicated `mctl-communication-agent`
deployment that hosts Claude Code as the reasoning loop for a Telegram
communication agent. That deployment needs a stdio MCP server it can spawn as
a subprocess: a thin bridge that (a) turns the durable `agent_events` /
`agent_actions` / `agent_jobs` queue exposed by the restricted HTTP surface
from issue #296 (`GET/POST /api/agent/v1/...`) into MCP tool calls, and (b)
turns new incoming events into wake-up notifications so Claude Code does not
have to poll on its own clock.

`mctl-telegram` already ships two MCP-adjacent patterns this binary should
follow: a streamable-HTTP mcp-go server for the user-facing Telegram tools
(`internal/mcp/server.go`) and a standalone reconnecting daemon binary
(`cmd/local`, `internal/bridge`) for a machine that is not the primary HTTP
server. `cmd/agent-channel` is architecturally closer to the second: a
small, long-running Go process with its own `main.go`, no HTTP server of its
own, and a reconnect-with-backoff loop — except its transport is MCP stdio
to Claude Code on one side and HTTP long-poll to `AGENT_API_URL` on the
other, rather than a websocket relay.

The domain model this binary proxies (`AgentAction`, `AgentProfile`,
`IncomingEvent`, action types `propose_reply` / `send_owner_summary` /
`request_owner_approval`, statuses `proposed -> pending_approval -> approved
-> executing -> executed`, policy decisions `allow` / `require_approval` /
`deny`) already exists in `internal/db/agent_actions.go`,
`internal/db/agent_domain.go`, and `internal/db/agent_events.go`. This
proposal does not change that model; it adds a new binary that talks to it
only through the HTTP API surface of #296, never through `internal/db`
directly (the binary is deployed separately from the DB-holding server, per
the issue: "no shell, no filesystem, no generic HTTP tool").

## User stories

- AS the `mctl-communication-agent` Claude Code runtime I WANT an MCP stdio
  server that exposes exactly the agent HTTP API as typed tools SO THAT I can
  act on Telegram conversations without holding Telegram credentials, a DB
  connection, or unrestricted network/file access.
- AS the `mctl-communication-agent` Claude Code runtime I WANT a wake-up
  notification the moment a new event is queued SO THAT I do not have to
  poll `get_event` on a fixed timer and can react promptly to new messages.
- AS a platform operator I WANT the bridge to be a narrow, auditable proxy
  with no shell/filesystem/generic-HTTP tools SO THAT a prompt-injected or
  compromised Claude Code session cannot escalate beyond the agent action
  surface #296 already policy-gates.
- AS a platform operator I WANT the bridge to never log
  `AGENT_API_TOKEN` or event/message bodies SO THAT the same data-handling
  bar as the rest of `mctl-telegram` (see `internal/audit/redact.go`) is
  upheld for this binary too.
- AS the container supervisor I WANT the process to exit non-zero only on
  fatal config errors and otherwise stay up through API/network errors SO
  THAT transient `AGENT_API_URL` outages do not flap the agent pod.

## Acceptance criteria (EARS)

- WHEN `cmd/agent-channel` starts with valid `AGENT_API_URL` and
  `AGENT_API_TOKEN` THE SYSTEM SHALL start an MCP stdio server (mcp-go
  `NewStdioServer`) on stdin/stdout and begin the long-poll loop against
  `GET /api/agent/v1/events`.
- WHEN `AGENT_API_URL` or `AGENT_API_TOKEN` is missing or malformed at
  startup THE SYSTEM SHALL log a startup error (without echoing the token
  value) and exit with a non-zero status before opening the stdio server.
- WHEN the long-poll call to `GET /api/agent/v1/events` returns one or more
  new events THE SYSTEM SHALL emit one `notifications/claude/channel`
  MCP notification per event, carrying a short human-readable wake-up text
  and the event's `event_id` in the notification `meta`, and SHALL NOT
  embed the event body/payload in the notification.
- WHEN Claude Code calls an agent tool (`propose_reply`, `save_job_lead`,
  `send_owner_summary`, `request_owner_approval`, `complete_agent_job`,
  `get_event`, `get_conversation_context`, `get_policy`,
  `pause_autopilot`, `get_lead`) THE SYSTEM SHALL forward the call 1:1 to
  the corresponding `/api/agent/v1/...` endpoint and translate the JSON
  response (success or error) into the matching MCP tool result.
- WHEN `GET /api/agent/v1/events` or a tool-proxy call receives an HTTP 5xx
  or a network error THE SYSTEM SHALL retry with exponential backoff
  (bounded, jittered) rather than exiting, and SHALL NOT surface the raw
  transport error to Claude Code as a fatal stdio failure.
- WHEN a tool-proxy call receives an HTTP 4xx (e.g. 401, 403, 409, 422)
  THE SYSTEM SHALL return that as a normal MCP tool error result (not a
  process-level failure), so Claude Code can see and reason about it.
- WHILE the process is running THE SYSTEM SHALL NOT log the value of
  `AGENT_API_TOKEN`, event bodies, message text, or proposed reply payloads
  at any log level, consistent with the redaction bar enforced elsewhere in
  the repo by `internal/audit/redact.go`.
- WHILE the long-poll loop is between requests THE SYSTEM SHALL hold at
  most one in-flight `GET /api/agent/v1/events` request and SHALL honor the
  configured poll timeout so the connection does not hang indefinitely.
- IF the notification for a given event fails to send (stdio write error,
  process about to exit, etc.) THEN THE SYSTEM SHALL rely on the
  server-side visibility-timeout requeue described in #298 to redeliver the
  event later, and SHALL NOT treat the notification itself as the durable
  record of the event.
- IF a fatal, non-recoverable config error occurs after startup (e.g. the
  API token was rotated and every retry now gets 401) THE SYSTEM SHALL keep
  retrying with backoff rather than exiting, because the issue specifies
  "exit non-zero only on fatal config errors" as a startup-time behavior;
  the container supervisor is the intended recovery path for a long-lived
  auth failure (see Open questions).
- THE SYSTEM SHALL expose no shell-execution tool, no filesystem-access
  tool, and no generic/arbitrary-URL HTTP tool — the complete MCP tool list
  SHALL be exactly the ten agent tools named in the issue, 1:1 mapped to the
  #296 API surface.
- THE SYSTEM SHALL be built as a distinct binary at `cmd/agent-channel` and
  packaged as an additional `COPY --from=builder` artifact in the existing
  multi-stage `Dockerfile`, without changing the image's default
  `ENTRYPOINT` (`mctl-telegram`, the HTTP server).

## Out of scope

- The `/api/agent/v1/...` HTTP surface itself (endpoints, auth, policy
  engine wiring) — that is issue #296, a hard prerequisite ("do not start
  until #296 is merged"). This proposal assumes that surface exists and is
  stable enough to design a 1:1 proxy against; exact request/response JSON
  shapes must be confirmed against the merged #296 implementation before
  coding.
- Any change to `internal/db/agent_actions.go`, `agent_domain.go`, or
  `agent_events.go` — the domain model is out of scope; this binary only
  consumes it through HTTP.
- The `mctl-communication-agent` Kubernetes deployment manifest, its Claude
  Code system prompt, or how it is wired to spawn this binary as a stdio
  subprocess — that lives in the deploy/gitops repo, not `mctl-telegram`.
- Any change to the existing `internal/mcp` (Telegram user-account tools)
  or `internal/bridge` (Local Bridge websocket relay) packages — this is a
  new, independent binary, not an extension of either.
- The `docs/claude-channels-spike.md` source document referenced by the
  issue lives in `mctl-claude-remote#32`, a different repository not
  present in this clone; this proposal's README task recreates the
  channel-contract documentation from the issue text and the #296 API
  shape as understood here, not by reading that spike doc directly.

## Open questions

- Exact `/api/agent/v1/...` request/response JSON schemas (field names,
  pagination for `get_event`/`get_conversation_context`, long-poll query
  params for `GET /api/agent/v1/events`) are not yet defined in this repo
  (#296 is unmerged; no `api/agent` routes exist in the current tree).
  Interpretation: design the proxy layer against a small internal
  `agentapi.Client` Go interface now, and treat wiring the exact JSON
  shapes as a task blocked on #296 landing, not as a reason to delay this
  proposal.
- The issue says "exit non-zero only on fatal config errors" but does not
  define the boundary between a fatal config error and a persistent runtime
  auth failure (e.g. token revoked mid-run). Interpretation: only
  startup-time validation (empty/malformed `AGENT_API_URL`, empty
  `AGENT_API_TOKEN`, invalid poll-timeout value) is treated as fatal;
  anything discovered after the stdio server is already up is retried with
  backoff and logged, leaving supervisor-level restart/alerting as the
  recovery path for sustained auth failure. Confirm this reading against
  #296's error semantics once it lands.
- mcp-go v0.54.0 (pinned in `go.mod`) is the target SDK version; its exact
  API for server-initiated notifications outside a request context (e.g.
  `MCPServer.SendNotificationToAllClients` vs. a session-scoped sender) was
  not verifiable in this environment (no network access to fetch the module,
  no local module cache). Interpretation: task 3 below includes a spike step
  to confirm the exact call before the notification-emission code is
  written; the design assumes *some* server-level "push a notification to
  the connected stdio client" primitive exists in this SDK version, which is
  a documented mcp-go feature as of the versions used elsewhere in the repo.
- Whether `notifications/claude/channel` needs to be declared as an
  experimental capability at server-init time (issue: "declaring the
  `claude/channel` experimental capability") in a way mcp-go's
  `NewMCPServer` options support directly, or whether it requires a raw
  capabilities-map override. Interpretation: treat as a task-3 spike item;
  if mcp-go has no first-class option for custom experimental capabilities,
  fall back to whatever escape hatch it exposes (e.g. a capabilities struct
  literal) and document the exact mechanism in the README once confirmed.
- Poll timeout units/bounds for the `AGENT_API_URL` long-poll config env var
  are unspecified. Interpretation: a `AGENT_POLL_TIMEOUT` env var, Go
  duration string (e.g. `25s`), default `25s`, capped below common
  reverse-proxy idle-timeout defaults (60s) to avoid the long-poll
  connection being killed mid-wait.
