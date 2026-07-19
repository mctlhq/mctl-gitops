# Design: issue-298-agent-channel-stdio-mcp-bridge-binary-co

## Current state

`mctl-telegram` currently ships MCP over two transports, both in-process with
the main HTTP server, and one detached daemon binary with no MCP server at
all:

- `internal/mcp/server.go` (`Server.HTTPHandler`) builds an `mcpserver.NewMCPServer("mctl-telegram", "0.7.0", ...)`
  and registers ~20 Telegram-account tools via `srv.AddTool(tool, handler)`,
  gated through `s.addTool` / `toolPassesFilter` (an operator-level
  read-only filter). It is served over `mcpserver.NewStreamableHTTPServer`,
  mounted into the chi router from `cmd/server/main.go`. This is HTTP
  transport, in-process with the DB and Telegram client pool — not the
  pattern this issue asks for.
- `internal/mcp/tools.go` shows the house style for a tool: a `func (s *Server) toolX() (mcplib.Tool, mcpserver.ToolHandlerFunc)` builder, flood-wait/retry handling (`borrowWithRetry`), and structured error mapping via `internal/mcp/errorcatalog.go` (`mtprotoErrCatalog`, `toolErr`/`formatErr`). The 1:1 API-proxy tools this issue needs are far simpler (no MTProto retry policy) but should keep the same "one builder function per tool, explicit `mcplib.Tool` + handler pair" shape for consistency and testability.
- `cmd/local/` is the closest architectural sibling: a **separate binary**
  (`cmd/local/main.go`) with its own subcommands, no HTTP server, and a
  persistent reconnect loop in `cmd/local/daemon.go` (`runDaemon`):
  exponential backoff (`reconnectBase = 2s`, `reconnectMax = 60s`), signal
  handling via `signal.Notify(sigs, syscall.SIGINT, syscall.SIGTERM)`, and a
  clean `context.Context` cancellation path. `cmd/agent-channel` should copy
  this shape (own `main.go`, own reconnect/backoff loop, no shared HTTP
  server) rather than the `internal/mcp/server.go` shape, but it needs
  **no** websocket, DB, or Telegram client pool at all — its two edges are
  MCP-stdio-to-Claude-Code and HTTP-to-`AGENT_API_URL`.
- `internal/config/config.go` is the env-var-loading convention for the
  main server (`Config` struct, `config.Load()`, doc comments naming the
  env var next to each field). `cmd/local/config.go` shows the parallel,
  self-contained convention for a standalone binary (its own small config
  struct + loader, not reusing `internal/config`, because the local binary
  has a different deployment context). `cmd/agent-channel` should follow
  the `cmd/local` pattern: a small package-local config loader reading
  `AGENT_API_URL`, `AGENT_API_TOKEN`, `AGENT_POLL_TIMEOUT` directly from
  `os.Getenv`, not extending the server's `Config` struct (this binary is
  never deployed alongside `cmd/server` and does not need its 30+ unrelated
  fields).
- `internal/audit/redact.go` (`RedactingHandler`, `sensitiveKeys` map) is
  the repo-wide log redaction mechanism, but it is wired only into
  `cmd/server/main.go`'s `slog.SetDefault`. `cmd/local/main.go` uses a plain
  `slog.NewTextHandler` and instead avoids logging secrets by construction
  (e.g. `wrapMsgs`/`sanitize` before any log call). Since `cmd/agent-channel`
  is a new, independent binary, it will not automatically inherit
  `RedactingHandler`; it needs its own equivalent discipline: never pass
  `AGENT_API_TOKEN`, event bodies, or payload text as log attributes, and
  add a request-log helper that logs only method/path/status/duration.
- `Dockerfile` is a two-stage build: `builder` runs three `go build`
  invocations (`./cmd/server` -> `/mctl-telegram`, `./cmd/login` ->
  `/mctl-telegram-login`, `./cmd/canary` -> `/mctl-telegram-canary`), then
  the `alpine:3.20` runtime stage does three `COPY --from=builder` lines and
  sets `ENTRYPOINT ["mctl-telegram"]`. `cmd/local` is deliberately **not**
  in this Dockerfile — it is a separately distributed CLI for the user's own
  machine. `cmd/agent-channel`, by contrast, per the issue "ships in the
  mctl-telegram image as a second binary" — it belongs inside this
  Dockerfile alongside `cmd/server`, `cmd/login`, `cmd/canary`, but must not
  change the image's `ENTRYPOINT`, since the `mctl-communication-agent`
  deployment spawns it as a stdio subprocess of Claude Code, not as the
  container's own PID 1 process.
- No `/api/agent/v1/...` HTTP routes exist anywhere in the current tree
  (confirmed by grep) — #296 has not landed in this clone. The domain types
  and state machine this API surface will front already exist:
  `internal/db/agent_actions.go` (`AgentAction`, action types
  `ActionTypeReply` / `ActionTypeOwnerSummary` / `ActionTypeOwnerApproval`,
  statuses `ActionProposed` -> ... -> `ActionExecuted`, policy decisions
  `PolicyAllow` / `PolicyRequireApproval` / `PolicyDeny`),
  `internal/db/agent_domain.go` (`AgentProfile`, agent modes
  `AgentModeObserve` / `AgentModeGuarded` / `AgentModeOff`, conversation
  states), and `internal/db/agent_events.go` (`IncomingEvent`, event kinds,
  the `EventID` dedup key format `evt:v1:<account_tg_id>:<chat_id>:<message_id>[:e<edit_ts>]`).
  This gives high confidence about the *shape* of what `get_event`,
  `get_conversation_context`, `get_policy`, `get_lead` will return once
  #296 exposes them, even though the JSON wire format is not yet fixed.
- `internal/mcp/server.go`'s `mcpserver.NewMCPServer(..., mcpserver.WithToolCapabilities(true))`
  is the only capability-declaration call site in the repo; there is no
  existing precedent for declaring a custom experimental capability
  (`claude/channel`) or for server-initiated notifications
  (`notifications/...`) in mcp-go v0.54.0 as currently used — this is new
  ground for the codebase (see design's Open questions carry-over in
  requirements.md).

## Proposed solution

Add a new, fully independent binary `cmd/agent-channel/main.go` plus a small
internal package `internal/agentchannel` that holds the logic so it is unit
testable without an MCP transport in the loop (mirroring how
`internal/mcp` holds the tool logic while `cmd/server` just wires it up).

```
cmd/agent-channel/
  main.go            — flag/env parsing, logger setup, wires internal/agentchannel.Run

internal/agentchannel/
  config.go          — Config struct + LoadConfig() reading AGENT_API_URL,
                        AGENT_API_TOKEN, AGENT_POLL_TIMEOUT from os.Getenv;
                        validates and returns typed errors for fatal cases
  client.go          — agentapi.Client: thin HTTP client for the ten
                        /api/agent/v1/... endpoints + the long-poll events
                        endpoint. One method per endpoint, request/response
                        structs colocated. Owns the Authorization header
                        (Bearer AGENT_API_TOKEN) and never logs it.
  tools.go            — one builder function per MCP tool
                        (toolProposeReply, toolSaveJobLead,
                        toolSendOwnerSummary, toolRequestOwnerApproval,
                        toolCompleteAgentJob, toolGetEvent,
                        toolGetConversationContext, toolGetPolicy,
                        toolPauseAutopilot, toolGetLead), each translating
                        mcplib tool args -> Client call -> mcplib.CallToolResult,
                        matching the internal/mcp/tools.go builder shape.
  server.go           — Server.MCPServer() builds the mcpserver.NewMCPServer
                        with the claude/channel experimental capability and
                        registers the ten tools (mirrors internal/mcp/server.go's
                        HTTPHandler, but returns an *mcpserver.MCPServer
                        for stdio use instead of an http.Handler).
  poller.go           — long-poll loop: GET /api/agent/v1/events with the
                        configured poll timeout, backoff-with-jitter on
                        error/5xx (mirrors cmd/local/daemon.go's
                        reconnectBase/reconnectMax constants and backoff
                        shape), emits one notifications/claude/channel
                        message per event via the stdio server's
                        notification-send primitive, tracks a resume
                        cursor/ack per the #296 long-poll contract.
  run.go              — Run(ctx, Config) error: wires client + server +
                        poller, starts mcpserver.NewStdioServer(...).Listen
                        on stdin/stdout in one goroutine and the poll loop
                        in another, returns when ctx is cancelled or a
                        fatal error occurs.
```

Key decisions:

1. **New package, not an extension of `internal/mcp`.** `internal/mcp` is
   wired to `*db.Store` / `*telegram.ClientPool` / `*bridge.Hub` throughout
   (`Server` struct in `internal/mcp/server.go`); this binary must have
   none of those — it is a pure HTTP-to-MCP proxy with zero DB/Telegram
   access, which is the whole point of the issue's "no shell, no
   filesystem, no generic HTTP tool" constraint applied *inward* too (the
   bridge itself should not be able to touch the DB even if compromised).
   Reusing `internal/mcp.Server` would make that guarantee much harder to
   see and enforce by inspection.

2. **1:1 tool-per-endpoint, no generic dispatch.** Each of the ten tools
   gets its own builder function and its own typed request/response struct
   in `client.go`, following `internal/mcp/tools.go`'s one-function-per-tool
   convention. A generic "call any agent endpoint" tool was considered and
   rejected — it would violate the issue's explicit "no generic HTTP tool"
   requirement and erase the tool-level `Annotations`
   (`ReadOnlyHint`/`DestructiveHint`) that `internal/mcp/server.go`'s
   `toolPassesFilter` pattern shows the repo already relies on for
   operator-level gating; keeping that possible here (even if unused
   initially) costs nothing.

3. **Config is package-local, not `internal/config.Config`.** Following
   `cmd/local/config.go`'s precedent: this binary is deployed standalone
   (a different pod, different env, different lifecycle from
   `cmd/server`), so folding it into the 30-plus-field server `Config`
   would create false coupling — a `cmd/agent-channel` env change should
   never risk affecting `cmd/server`'s `config.Load()` parsing, and vice
   versa.

4. **Long-poll + notification, not push.** The issue is explicit that
   "notifications are wake-ups only — the durable queue is the source of
   truth; a lost notification is recovered by the server-side
   visibility-timeout requeue." The poller therefore treats notification
   delivery as best-effort: if the stdio pipe write fails or the process is
   mid-restart, the design does nothing special to guarantee delivery — the
   next long-poll cycle (after this process or its replacement restarts)
   will see the event again via `GET /api/agent/v1/events`, and #296's
   requeue is the actual durability mechanism. This keeps `poller.go` simple
   (no local outbox/ack bookkeeping duplicating server-side state).

5. **Backoff mirrors `cmd/local/daemon.go`.** Same constants shape
   (`reconnectBase`/`reconnectMax`-equivalent, e.g. `pollBackoffBase = 2s`,
   `pollBackoffMax = 60s`), same "reset backoff after a session that ran
   long enough to indicate healthy connectivity" behavior, applied to HTTP
   long-poll retries instead of websocket reconnects. This keeps the two
   reconnect/backoff implementations in the repo recognizably the same
   shape for anyone who has read one of them.

6. **Logging discipline without `RedactingHandler`.** Rather than trying to
   reuse `internal/audit.NewRedactingHandler` (which is tuned for the
   server's attribute vocabulary — `text`, `body`, `session`, etc.), the new
   package follows `cmd/local`'s approach: construct log lines that never
   include the raw token or event body in the first place (log
   `event_id`, `status_code`, `duration_ms`, `retry_count`, not
   `Authorization` or `payload`). A short `internal/agentchannel/config.go`
   comment documents the same constraint the issue states in prose ("never
   logged"), and a unit test (mirroring
   `cmd/local/daemon_test.go`'s `TestWrapMsgs_RedactsTelegramLoginSecrets`)
   asserts no log line captured during a fake-401 run contains the
   configured token value.

7. **Experimental capability + notification mechanism: confirmed at
   implementation time, not guessed here.** The design commits to *where*
   this logic lives (`server.go`, `poller.go`) and *what* it must do
   (declare `claude/channel`, emit `notifications/claude/channel` with
   `event_id` in `meta`), but the exact mcp-go v0.54.0 call
   (`mcpserver.WithCapabilities(...)` vs. a raw map;
   `MCPServer.SendNotificationToAllClients` vs. a stdio-session-scoped
   sender) needs to be confirmed against the vendored source once a
   network-enabled environment is available — task 3 in tasks.md is a
   dedicated spike for this before the poller/notification code is
   written, so the uncertainty does not block the rest of the design.

8. **Dockerfile: additive, no behavior change to the existing entrypoint.**
   Add one more `go build ... -o /mctl-telegram-agent-channel ./cmd/agent-channel`
   line to the `builder` stage and one more `COPY --from=builder
   /mctl-telegram-agent-channel /usr/local/bin/mctl-telegram-agent-channel`
   line to the runtime stage, leaving `ENTRYPOINT ["mctl-telegram"]`
   untouched. The `mctl-communication-agent` deployment (outside this repo)
   overrides the container command to run
   `mctl-telegram-agent-channel` as the stdio subprocess Claude Code spawns;
   that wiring is out of scope here (see requirements.md Out of scope) but
   the binary must exist at a stable, documented path in the image for it
   to be possible.

## Alternatives

1. **Extend `internal/mcp.Server` with agent-channel tools and let it run
   over stdio as an optional mode of the existing binary.** Rejected: the
   existing `Server` is structurally wired to `*db.Store`,
   `*telegram.ClientPool`, `*bridge.Hub`, `*audit.RateLimiter` — adding a
   stdio/no-DB code path would mean either (a) threading a lot of
   nil-checks through already-dense code (`internal/mcp/server.go` already
   has six `With*` optional-dependency setters), or (b) building a second,
   parallel `Server`-like type inside the same package anyway, at which
   point it should just be its own package. It would also blur the "no DB
   access" security property this binary is supposed to have by
   construction — mixing it into a package whose whole reason to exist is
   DB/Telegram access invites a future accidental `s.Store.X()` call from
   the agent-channel code path.

2. **Have the agent-channel binary talk to `internal/db` directly instead
   of the #296 HTTP API**, skipping the network hop. Rejected: the issue is
   explicit that this binary proxies to "the restricted HTTP surface from
   #296" — the whole design intent of #296 is to put a policy-gated HTTP
   boundary between the Claude-Code-driven agent process and the DB, so a
   compromised/prompt-injected agent session cannot bypass policy checks by
   getting the model to construct raw SQL-adjacent calls. Direct DB access
   would also require shipping DB credentials and driver code into a
   process whose entire value proposition is a minimal, auditable tool
   surface, and would couple this binary's deployment to DB network
   reachability, which the issue does not ask for.

3. **Server push via websocket (reuse `internal/bridge.Hub`/`coder/websocket`,
   as `cmd/local`/`internal/bridge` already do) instead of HTTP long-poll +
   stdio notification.** Rejected: the issue explicitly specifies
   "long-poll `GET /api/agent/v1/events`" as the transport into this
   binary, matching #296's HTTP-only surface; introducing a second,
   websocket-based channel would require #296 to also expose a websocket
   endpoint (out of scope, and not requested) purely to save one network
   round-trip pattern already proven to work in this codebase via
   `internal/bridge`. Long-poll is also the right fit for the "notification
   is a wake-up only" durability model — an at-most-one-in-flight polling
   loop is simpler to reason about and test with `httptest` than a
   persistent bidirectional socket.

## Platform impact

- **Migrations:** none. This binary has no DB access and defines no schema.
- **Backward compatibility:** additive only — a new `cmd/agent-channel`
  binary and a new `internal/agentchannel` package. No existing package,
  route, or CLI is modified except the `Dockerfile` (new `go build`/`COPY`
  lines, `ENTRYPOINT` unchanged) and `docs/` (a new README section).
  `go vet ./...` / `go build ./...` / `go test ./...` (per
  `.github/workflows/build.yml`) continue to cover the new package and
  binary once added, with no changes needed to the workflow file itself.
- **Resource impact:** one additional binary in the built image (a few MB,
  same `golang:1.26.5-alpine` -> `alpine:3.20` toolchain already in use);
  no additional runtime resource impact on `cmd/server`'s own pods, since
  this binary is not started by `cmd/server` and is not part of its
  `ENTRYPOINT`. The `mctl-communication-agent` deployment that spawns it is
  itself out of scope (lives in the gitops repo).
- **Risks + mitigations:**
  - *Token leakage via logs.* Mitigated by the logging-discipline design
    point above plus a dedicated unit test asserting the token never
    appears in captured log output (mirrors the existing
    `TestWrapMsgs_RedactsTelegramLoginSecrets` pattern in `cmd/local`).
  - *Tool surface creeping beyond the ten named tools* (e.g. a future PR
    adding a "debug" or "raw HTTP" tool for convenience). Mitigated by a
    unit test that asserts the registered tool-name set on the constructed
    `*mcpserver.MCPServer` is exactly the ten names from the issue, so an
    accidental/unreviewed addition fails CI.
  - *Long-poll thundering/backoff bugs causing hammering of #296's HTTP
    surface on an outage.* Mitigated by porting the proven backoff shape
    from `cmd/local/daemon.go` (base/max/jitter, reset-after-healthy-session)
    and a table-driven test asserting backoff grows and caps correctly
    across a sequence of injected 5xx/network errors (httptest server).
  - *mcp-go v0.54.0 API surface for experimental capabilities/notifications
    turning out not to match what the design assumes*, discovered only
    once implementation starts. Mitigated by making that confirmation its
    own task (task 3, blocking tasks 4-6) rather than an assumption baked
    silently into the poller/server code.
  - *Coupling to #296's not-yet-finalized JSON shapes.* Mitigated by
    isolating all wire-format knowledge inside `internal/agentchannel/client.go`
    behind a small `agentapi.Client` interface with one method per
    endpoint, so a shape change in #296 after this proposal is written
    means editing one file's request/response structs, not the tool
    handlers or the poller.
