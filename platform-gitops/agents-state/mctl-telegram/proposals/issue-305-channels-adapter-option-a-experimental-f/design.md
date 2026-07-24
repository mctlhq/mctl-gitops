# Design: issue-305-channels-adapter-option-a-experimental-f

## Current state

Read directly in this clone:

- `internal/agentapi/server.go` (package doc, lines 1-9): explicitly frames itself as "the
  restricted HTTP surface the communication agent's worker (whatever process invokes Claude — a
  headless Option-C worker today, an experimental Channels bridge later) talks to." This confirms
  the JSON API was designed worker-agnostic from the start and #305's job is to be the second
  consumer, not to add new server-side surface.
- `internal/agentapi/server.go` `Register()` mounts, relative to `/api/agent/v1`:
  `GET /events`, `GET /event/{eventID}`, `GET /conversations/{id}/context`,
  `GET /recruiters/{peer}`, `GET /leads/{id}`, `GET /policy`, `POST /actions/propose_reply`,
  `POST /leads`, `POST /actions/request_owner_approval`, `POST /notify/summary`,
  `POST /autopilot/pause`, `POST /jobs/{id}/complete`. This is the full agent tool surface #305
  must proxy 1:1.
- `internal/agentapi/events.go` `handleEvents`: `GET /events` long-polls
  `s.Queue.Claim(ctx, id.UserID, limit)` for up to `s.longPollTimeout` (default 20s,
  `defaultLongPollTimeout` in `server.go`), returning `{"jobs": [...]}` — always HTTP 200, an empty
  array is the documented "nothing due" case, not an error. Each `jobEnvelope` carries `job_id`,
  `event_id`, `conversation_id`, `attempt` (must be echoed back on complete), and an advisory
  `deadline`. The full event body is fetched separately via `GET /event/{eventID}`
  (`eventResponse`: kind, chat/sender/message ids, body, meta, created_at). This wake-up/fetch split
  is exactly the shape #305's issue text describes for the `claude/channel` notification
  (short wake-up text + `event_id` in `meta`, durable queue as source of truth).
- `internal/agentapi/events.go` `handleJobComplete`: `POST /jobs/{id}/complete` requires the
  `attempt` value from the claim and a `status` of `completed`/`failed`/`ignored`; `completed`
  additionally requires a durably persisted result (an `agent_actions` row or a lead) to already
  exist, returning 409 otherwise. Any worker (Option C or #305's Channels adapter) must therefore
  call the propose/lead endpoints before completing, not just move straight to complete.
- `internal/agentapi/tokenhandler.go`: agent credentials are JWTs with `aud=["agent"]`, minted by an
  admin via `POST /api/agent/token` (`NewAgentTokenHandler`), default TTL 30 days, capped at 90.
  There is no per-worker-type distinction in the token — the same kind of token used by #298's
  worker today is what `cmd/agent-channel` will hold as `AGENT_API_TOKEN`.
- `internal/config/config.go` lines ~117-141: `AgentEnabled` (`AGENT_ENABLED`) gates whether
  `/api/agent/v1` and `/api/agent/token` are mounted at all; `AgentKillSwitch` (`AGENT_KILL_SWITCH`)
  is a separate env-only global kill switch the server-side policy engine
  (`internal/agent/policy`) checks on every evaluated action. Both are off/false by default. This is
  the established pattern for "communication agent" feature gating in this repo, and #305's
  `AGENT_CHANNEL_ENABLED` should follow the same `envBool(..., false)` shape (see `config.go`'s
  `envBool` helper).
- `internal/mcp/server.go`: the only existing MCP server in this repo is the Telegram-tools
  streamable-HTTP server (`mcpserver.NewStreamableHTTPServer`, `mcpserver.NewMCPServer`, `addTool`
  pattern registering `mcplib.Tool` + `mcpserver.ToolHandlerFunc` pairs). There is no existing stdio
  MCP server in this codebase; #305 is the first user of `mcp-go`'s `NewStdioServer` path
  (`github.com/mark3labs/mcp-go v0.54.0`, per `go.mod`). The `addTool`/capability-registration
  pattern in `internal/mcp/server.go` is still the right shape to imitate for registering the
  `claude/channel` experimental capability and its notification emission, even though the transport
  differs.
- `cmd/local/main.go` + `cmd/local/daemon.go`: the closest structural precedent for #305. It is a
  separate `cmd/` binary (not part of `cmd/server`), with its own subcommands, that authenticates to
  the hosted server with a bearer token (`bridge_token`, obtained via `connect`), opens a
  long-running loop (`runDaemon`, websocket instead of long-poll HTTP, but same "long-running,
  reconnect on failure" shape), and is entirely optional / not part of the main server's startup
  path. `cmd/agent-channel` should follow the same separate-binary, separate-`main()`,
  environment-configured pattern, but over long-poll HTTP against `/api/agent/v1` rather than a
  websocket against `/api/bridge`.
- `internal/metrics/metrics.go`: existing agent metrics (`AgentEventsReceivedTotal`,
  `AgentJobsTotal`, `AgentDeadLetterTotal`) are all server-side, registered on the shared
  `*metrics.Registry`. `cmd/agent-channel` is a separate process/binary with no access to that
  registry; it should not try to import and share it. If per-adapter metrics are wanted later, that
  is a separate concern from this proposal (see Alternatives).
- `internal/audit/redact.go`: the slog handler that strips sensitive field names from all JSON logs.
  `AGENT_API_TOKEN` is a new secret this repo does not currently redact by name; it must be added to
  that handler's field list, and the adapter's own logging must never pass it as a bare value.
- `.env.example` and `AGENTS.md`/`CLAUDE.md`: no `AGENT_CHANNEL_*` or `AGENT_API_*` variables exist
  yet anywhere in the repo (verified by grep) — these are wholly new config surface.
- `internal/agentapi/server_test.go`: the existing test harness pattern for this package (a real
  `chi.Router`, `httptest`-style identity injection, fixed 32-byte crypto key). `cmd/agent-channel`'s
  own tests instead need `cmd/agent-channel` to be the *client* under test against a fake
  `httptest.Server` standing in for `/api/agent/v1` — the inverse direction, but the existing
  `agentapi` package's route names and JSON shapes (`jobEnvelope`, `eventResponse`,
  `completeJobRequest`, `policyResponse`) are the exact contract the fake must honor so the adapter's
  request/response structs stay honest.

## Proposed solution

Add two new, independent, opt-in Go binaries to this repo. Neither is wired into `cmd/server`,
`Dockerfile`, `docker-compose.yml`, or any deploy manifest under `deploy/` — consistent with the
issue's "not on the production critical path, not blocking MVP" framing and with `AGENT_ENABLED`'s
existing precedent of shipping agent surface area disabled-by-default rather than physically absent.

1. `cmd/agent-channel/main.go` (+ package files) — the adapter binary.
   - `internal/config`-style env loading, local to the command (mirroring how `cmd/local/config.go`
     keeps its own small config type rather than reusing `internal/config.Config`, since this
     binary's concerns — `AGENT_API_URL`, `AGENT_API_TOKEN`, poll timeout, `AGENT_CHANNEL_ENABLED` —
     do not overlap with the server's config surface).
   - Refuses to start unless `AGENT_CHANNEL_ENABLED=true`; refuses to start if `AGENT_API_URL` or
     `AGENT_API_TOKEN` is empty. Fails fast and loud (matches `cmd/local`'s `die()` convention).
   - An `agentapiClient` type wrapping `net/http.Client`, bearer-authenticating every request with
     `AGENT_API_TOKEN`, with one method per `/api/agent/v1` route already enumerated above
     (`GetEvents(limit)`, `GetEvent(id)`, `GetPolicy()`, `ProposeReply(...)`,
     `RequestOwnerApproval(...)`, `NotifySummary(...)`, `AutopilotPause(...)`, `SaveLead(...)`,
     `GetLead(id)`, `RecruiterProfile(peer)`, `ConversationContext(id)`, `CompleteJob(id, attempt,
     status, note)`). This client is the single place that knows the JSON API's wire shapes; it
     reuses the exact field names from `internal/agentapi` (not reinvented) so a future contract
     change in `agentapi` is a compile-time mismatch here, not a silent drift.
   - An `mcp-go` `server.NewStdioServer` wrapping an `mcpserver.NewMCPServer(...)` instance that
     declares the `claude/channel` experimental capability and registers one MCP tool per
     `agentapiClient` method — i.e. the same tool surface Option C's worker exposes to Claude, proxied
     1:1 onto the JSON API, with no independent policy/authorization logic added in this binary (the
     server-side `internal/agent/policy` engine remains the sole authority, exactly as
     `internal/agentapi/misc.go`'s `handlePolicy` doc comment already states for any caller).
   - A poll loop (`runEventLoop(ctx, client, notifier, pollTimeout)`) that calls `GetEvents` in a
     tight `for` bounded by `ctx`, and on each non-empty response emits one
     `notifications/claude/channel` MCP notification per job via the stdio server's notification
     channel, with `{"text": "<short wake-up>", "meta": {"event_id": ..., "job_id": ...}}` — no event
     body in the notification, matching the issue's "notifications are wake-ups only" requirement and
     the JSON API's own wake-up/fetch split. Claude is expected to call the `get_event`-proxying tool
     to fetch the body, same as Option C's worker would.
   - Backoff: a small `backoff` helper (exponential with jitter, capped) applied whenever any
     `agentapiClient` call returns 5xx or a transport error; 4xx responses (other than the documented
     empty-`jobs` 200) are logged and NOT retried as transient, since the JSON API's own tests
     (`server_test.go`) already establish 4xx as terminal-for-that-request (bad params, not-found,
     conflict).
   - Structured logging via `slog`, matching the rest of the repo; `AGENT_API_TOKEN` is added to
     `internal/audit/redact.go`'s field list so any accidental structured-log inclusion (e.g. via a
     wrapped HTTP error containing headers) is scrubbed the same way session strings and JWT secrets
     already are.

2. `cmd/agent-channel-harness/main.go` — the one-off PTY driver, a second, separate binary.
   - Not invoked by `cmd/agent-channel`, not started by any service manager, not referenced from
     `Dockerfile`/`docker-compose.yml`. Its only job: spawn
     `claude --dangerously-load-development-channels server:agent-channel` under a PTY (e.g.
     `github.com/creack/pty`, a small dependency addition), watch stdout for the "I am using this for
     local development" confirmation prompt, and write the confirming keystroke — the one interaction
     the issue says six `expect`-driven attempts in the spike could not reliably automate. Run
     manually, once, by a human operator to produce the round-trip proof artifact.
   - Its README/doc header explicitly states it is a manual verification tool, not a production
     component, echoing the issue's framing so nobody later "helpfully" wires it into CI.

3. `docs/agent-channel-harness-run.md` — the durable record of the one successful
   event -> Claude -> reply-tool cycle (dated, with a redacted transcript excerpt and the
   `event_id`/`job_id` involved), produced by running the harness once. This is the acceptance
   artifact the issue asks for ("Acceptance for this issue is the round-trip proof itself").

4. README.md addition: a new `## Channels adapter (experimental)` section (placed after
   "## Connecting to ChatGPT Apps" and before "## Operations: Canary account", alongside the repo's
   other "how a specific integration works" sections) documenting: what `cmd/agent-channel` is, that
   it is off by default (`AGENT_CHANNEL_ENABLED=false`), the env vars it reads, the notification
   contract, an explicit "experimental / not production, do not depend on this as a standing
   entrypoint" callout, and links to `docs/claude-channels-spike.md` (mctl-claude-remote#32) and the
   plan's (tranquil-sleeping-map) Transport decision.

5. Unit tests: `cmd/agent-channel/*_test.go` using `net/http/httptest.NewServer` to stand up a fake
   `/api/agent/v1` (only the routes the adapter calls, returning fixture JSON matching
   `internal/agentapi`'s real response shapes) and asserting: (a) each proxied tool call hits the
   expected method+path+body, (b) a claimed-job long-poll response produces exactly one
   `notifications/claude/channel` per job with the right `event_id` in `meta` and no event body, (c) a
   sequence of 5xx responses is retried with backoff (assert on elapsed time bounds or an injectable
   clock/sleep function, not a real multi-second sleep) before succeeding, and (d) missing
   `AGENT_CHANNEL_ENABLED`/`AGENT_API_URL`/`AGENT_API_TOKEN` fails startup with a clear error and no
   network call attempted.

## Alternatives

1. **Put the Channels bridge logic inside `cmd/server` as an optional goroutine, gated by
   `AGENT_CHANNEL_ENABLED`, instead of a separate binary.** Rejected: a stdio MCP server fundamentally
   needs to be the process Claude Code launches directly (`claude ... server:agent-channel`) via
   stdin/stdout — it cannot be a goroutine inside the long-running HTTP server, which has no stdio
   channel to a Claude Code process. A separate binary is a technical requirement here, not just a
   style preference, and matches the issue's explicit `cmd/agent-channel` naming.

2. **Give the adapter its own copy of `internal/agent/policy` and evaluate autonomy/rate rules
   locally before calling the JSON API, to reduce round trips.** Rejected: `internal/agentapi`'s own
   handlers (see `misc.go`'s `handlePolicy` doc comment) are explicit that `GET /policy` is advisory
   only and the server always re-evaluates via `policy.Evaluate` on every state-changing call. Adding
   a second, client-side copy of policy logic would let the two workers (#298, #305) drift and
   directly contradicts the issue's "proxying 1:1 onto the JSON API" requirement. Kept out.

3. **Reuse `internal/mcp` (the existing streamable-HTTP Telegram tool server) by adding a stdio
   transport option to it, rather than writing a new `cmd/agent-channel` package from scratch.**
   Rejected: `internal/mcp.Server` is wired specifically to `*telegram.ClientPool` /
   `*bridge.Hub` / raw MTProto tool semantics (send_message, get_media, etc.) — a completely
   different tool surface from the agent-facing propose_reply/request_owner_approval/notify surface
   `agentapi` exposes. Sharing the package would conflate two independent tool surfaces and two
   independent trust boundaries (end-user Telegram actions vs. autonomous-agent-with-policy-gating
   actions) for no real code reuse benefit beyond the `addTool`-style registration idiom, which is
   cheap to imitate without importing the package.

4. **Skip the separate harness binary and drive the PTY confirmation with a shell script (`expect`
   or similar) under `test/` or `docs/`.** Rejected per the issue's own account: six `expect`-driven
   attempts already failed on TUI timing in the spike (mctl-claude-remote#32). A small Go program
   using a proper PTY library gives byte-level control over the pseudo-terminal and structured
   timeout/retry handling that shell-level `expect` scripting does not, and keeps the harness in the
   same language/toolchain/test infra as the rest of the repo.

## Platform impact

- **Migrations**: none. No new DB tables, columns, or schema changes — the adapter is a pure HTTP
  client of the existing `internal/agentapi` surface built for #296/#298.
- **Backward compatibility**: fully additive. Two new `cmd/` binaries and one README section; no
  existing binary, route, config default, or DB behavior changes. `AGENT_CHANNEL_ENABLED` defaults to
  false, so a deployment that does not set it sees zero behavior change, exactly like `AGENT_ENABLED`
  and `AGENT_KILL_SWITCH` today.
- **Resource impact**: negligible for `cmd/server` (unchanged). `cmd/agent-channel` itself is a
  small, optional, manually-run process when used at all — it is explicitly not deployed as a
  standing service by this proposal, so no additional container, replica, or scheduled job is added
  to `deploy/`.
- **Risks**:
  - *Scope creep into a de-facto second production entrypoint.* Mitigated by: no Dockerfile/compose/
    deploy manifest wiring in this proposal; the feature flag defaults off; README explicitly labels
    it experimental/non-production; the harness binary is separate from the adapter binary so "run
    the harness once" cannot accidentally become "the adapter starts a harness on boot."
  - *Secret leakage of `AGENT_API_TOKEN`.* Mitigated by: bearer-only usage (never logged), addition
    to `internal/audit/redact.go`'s field list, and the existing `AGENT_API_TOKEN`-never-logged
    requirement carried directly from the issue text.
  - *Channels protocol drift (research-preview, Anthropic may change the CLI/protocol).* Mitigated
    by: keeping the notification payload minimal (text + event_id in meta) so there is little
    surface to break, and by treating the harness run as a one-time proof rather than an ongoing CI
    gate — a protocol change would fail the next manual harness run, not silently break production,
    since nothing production-facing depends on this adapter.
  - *Fake-API tests drifting from the real `internal/agentapi` contract over time.* Mitigated by:
    building the fake test server's fixtures directly from `internal/agentapi`'s real response
    structs (`jobEnvelope`, `eventResponse`, `policyResponse`, `completeJobRequest`) rather than
    hand-rolled JSON, so a future `agentapi` field rename breaks compilation in the test file, not
    just silently mismatches at runtime.
