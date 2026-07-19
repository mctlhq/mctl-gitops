# Tasks: issue-298-agent-channel-stdio-mcp-bridge-binary-co

- [ ] 0. Confirm #296 has merged and pin the exact `/api/agent/v1/...`
      request/response JSON shapes (events long-poll params/response,
      the ten tool endpoints' request/response bodies, error envelope
      shape, auth header format) — DoD: a short scratch note (or the #296
      PR/README itself) lists every endpoint path, method, request body,
      success response, and error response this binary will call; blocks
      all tasks below that touch `client.go`.

- [ ] 1. Scaffold `internal/agentchannel` package with `Config` +
      `LoadConfig()` (env vars `AGENT_API_URL`, `AGENT_API_TOKEN`,
      `AGENT_POLL_TIMEOUT`; following the `cmd/local/config.go` /
      `internal/config/config.go` doc-comment-per-field convention) — DoD:
      `LoadConfig()` returns a typed fatal error for empty/malformed
      `AGENT_API_URL`, empty `AGENT_API_TOKEN`, and an unparsable
      `AGENT_POLL_TIMEOUT`; a table-driven test in `config_test.go` covers
      each fatal case plus the happy path and the documented default poll
      timeout.

- [ ] 2. Implement `internal/agentchannel/client.go`: an `agentapi.Client`
      HTTP client (depends on 0) with one typed method per endpoint
      (`ProposeReply`, `SaveJobLead`, `SendOwnerSummary`,
      `RequestOwnerApproval`, `CompleteAgentJob`, `GetEvent`,
      `GetConversationContext`, `GetPolicy`, `PauseAutopilot`, `GetLead`,
      `PollEvents`), each setting `Authorization: Bearer <token>` and never
      logging the token or response bodies containing message text — DoD:
      `client_test.go` uses `net/http/httptest.Server` to fake each
      endpoint (success + a representative error status), asserts request
      method/path/headers/body and response parsing, and asserts (via a
      captured `slog` handler) that no log record emitted during a run
      contains the configured token string.

- [ ] 3. Spike + confirm the mcp-go v0.54.0 primitives needed for (a)
      declaring the `claude/channel` experimental capability at
      `NewMCPServer` construction and (b) sending an unsolicited
      `notifications/claude/channel` message to the connected stdio client
      outside of a tool-call request context — DoD: a short comment block
      at the top of `internal/agentchannel/server.go` names the exact
      mcp-go types/functions used and why, so a future reader does not have
      to re-derive it; blocks tasks 4 and 5.

- [ ] 4. Implement `internal/agentchannel/tools.go` and `server.go`: one
      builder function per of the ten tools (depends on 2, 3), each
      following the `internal/mcp/tools.go` "`(mcplib.Tool,
      mcpserver.ToolHandlerFunc)` builder" shape, wired into
      `Server.MCPServer()` which also declares the `claude/channel`
      experimental capability — DoD: unit tests in `tools_test.go` call
      each tool's handler directly against a fake `agentapi.Client` (or a
      fake HTTP server per task 2's pattern) and assert the MCP
      `CallToolResult` for both success and a representative error;
      a `server_test.go` test asserts `MCPServer().ListTools()` (or
      equivalent) returns exactly the ten named tools, no more, no fewer.

- [ ] 5. Implement `internal/agentchannel/poller.go`: long-poll loop against
      `PollEvents` (depends on 2, 3) with exponential backoff on
      network/5xx errors (base/max/jitter mirroring
      `cmd/local/daemon.go`'s `reconnectBase`/`reconnectMax` shape,
      resetting after a healthy session), emitting one
      `notifications/claude/channel` notification per returned event with
      `event_id` in `meta` and a short wake-up text (no event body) — DoD:
      `poller_test.go` uses `httptest.Server` to (a) return a sequence of
      events and assert one notification is emitted per event with the
      correct `event_id` and no body/payload text present, (b) return 5xx
      responses and assert backoff grows monotonically up to the cap and
      resets after a subsequent success, (c) assert context cancellation
      stops the loop promptly without leaking goroutines
      (`go test -race`).

- [ ] 6. Implement `internal/agentchannel/run.go` (`Run(ctx, Config) error`,
      depends on 4, 5): wires the client, builds the stdio server via
      `mcpserver.NewStdioServer(...)`, starts `Listen` on stdin/stdout and
      the poller concurrently, returns on `ctx.Done()` or a fatal error —
      DoD: an integration-style test drives `Run` against a fake
      `AGENT_API_URL` httptest server and a piped stdin/stdout pair,
      confirms the server responds to an MCP `initialize` + `tools/list`
      handshake and that cancelling the context stops `Run` within a
      bounded timeout.

- [ ] 7. Add `cmd/agent-channel/main.go` (depends on 1, 6): loads
      `Config` via `internal/agentchannel.LoadConfig()`, sets up an
      `slog` logger to stderr (never stdout, which is the MCP transport),
      calls `agentchannel.Run(ctx, cfg)` under
      `signal.NotifyContext(ctx, syscall.SIGINT, syscall.SIGTERM)` mirroring
      `cmd/local/main.go`'s signal-handling shape, and exits non-zero only
      when `LoadConfig()` fails — DoD: `go build ./cmd/agent-channel`
      succeeds; a `main_test.go` (mirroring `cmd/server/main_test.go`'s
      style if present, else a minimal smoke test) asserts a missing
      `AGENT_API_TOKEN` produces a non-zero exit before any stdio server
      starts, without needing a live process (test the extracted
      config-then-run split, not `os.Exit` itself).

- [ ] 8. Update `Dockerfile` (depends on 7): add a third `go build` line in
      the `builder` stage (`-o /mctl-telegram-agent-channel
      ./cmd/agent-channel`) and a matching `COPY --from=builder` line in
      the runtime stage; leave `ENTRYPOINT ["mctl-telegram"]` unchanged —
      DoD: `docker build .` succeeds locally/in CI and
      `docker run --rm <image> mctl-telegram-agent-channel` (with no env
      vars set) exits non-zero with a config error, not a panic or hang.

- [ ] 9. Write `docs/agent-channel.md` (depends on 4, 5, 6): the channel
      contract README section required by the issue — the ten tool names
      and their 1:1 endpoint mapping, the `notifications/claude/channel`
      wake-up-only contract and the visibility-timeout-requeue durability
      note, the `claude/channel` experimental capability, required env
      vars (`AGENT_API_URL`, `AGENT_API_TOKEN`, `AGENT_POLL_TIMEOUT`) and
      that the token is never logged, and an explicit "no shell, no
      filesystem, no generic HTTP tool" statement of the security
      boundary. Note inline that the canonical channel-contract source is
      `docs/claude-channels-spike.md` in `mctl-claude-remote#32` (a
      different repo, not available in this clone) and that this section
      should be reconciled against that spike doc by whoever has access to
      it — DoD: file exists under `docs/`, is linked from the top-level
      `README.md`'s docs index (matching how `docs/runbook.md` /
      `docs/slo.md` are already linked, if such an index exists — verify
      during implementation), and `docs/runbook_test.go`-style doc
      consistency tests (if applicable to new doc files) pass.

- [ ] 10. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run`, and the
      full `go test ./...` suite (depends on 1-9) — DoD: all green,
      matching `.github/workflows/build.yml`'s `go vet` / `go build` /
      `go test` steps; no new lint findings in `internal/agentchannel` or
      `cmd/agent-channel`.

## Tests

- [ ] T1. `internal/agentchannel/config_test.go` — fatal vs. happy-path env
      var combinations for `LoadConfig()` (task 1).
- [ ] T2. `internal/agentchannel/client_test.go` — httptest-backed proxying
      test per endpoint (success + error status), plus a token-non-logged
      assertion (task 2).
- [ ] T3. `internal/agentchannel/tools_test.go` — one test per tool handler
      covering success and error `CallToolResult` mapping (task 4).
- [ ] T4. `internal/agentchannel/server_test.go` — exact-ten-tools
      assertion and experimental-capability-declared assertion (task 4).
- [ ] T5. `internal/agentchannel/poller_test.go` — notification-per-event,
      backoff-on-5xx growth/cap/reset, and context-cancellation-stops-loop
      (task 5), run under `-race`.
- [ ] T6. `internal/agentchannel/run_test.go` — MCP `initialize`/`tools/list`
      handshake over piped stdio against a faked `AGENT_API_URL` (task 6).
- [ ] T7. `cmd/agent-channel/main_test.go` — missing-token fatal-exit path
      exercised without spawning a real OS process (task 7).
- [ ] T8. Manual/CI Docker smoke check: `docker run --rm <image>
      mctl-telegram-agent-channel` with no env vars exits non-zero
      (task 8), and with `AGENT_API_URL`/`AGENT_API_TOKEN` pointed at a
      throwaway fake server, the process stays up and responds to a
      `tools/list` request piped over stdin.

## Rollback

This is a purely additive change: a new package
(`internal/agentchannel`), a new binary (`cmd/agent-channel`), a new doc
file (`docs/agent-channel.md`), and two new lines in the `Dockerfile`. No
existing route, table, tool, or CLI subcommand is modified or removed, and
`cmd/server`'s `ENTRYPOINT` is unchanged, so `cmd/server`, `cmd/login`,
`cmd/canary`, and `cmd/local` are unaffected by construction.

- If the binary needs to be pulled from a bad release: revert the Dockerfile
  hunk (drop the `go build .../cmd/agent-channel` and matching `COPY`
  lines) and cut a new image; the `mctl-communication-agent` deployment
  (outside this repo) simply has nothing to spawn until the next good
  image, and no data migration or state cleanup is needed since the binary
  is stateless (holds no local DB, no local files beyond process memory).
- If a bug in the poller/notification logic causes it to hammer #296's API
  during an outage: the fastest mitigation is scaling the
  `mctl-communication-agent` deployment to zero replicas (outside this
  repo) — the binary has no side effects on `mctl-telegram`'s own DB or
  Telegram sessions, so stopping it is always safe.
- If `internal/agentchannel` or `cmd/agent-channel` needs to be deleted
  entirely (e.g. the workstream is abandoned): `git rm -r
  internal/agentchannel cmd/agent-channel docs/agent-channel.md`, revert
  the Dockerfile hunk — no other package imports `internal/agentchannel`
  by design (it is a leaf package consumed only by its own `main.go`), so
  this is a clean removal with no ripple into `internal/mcp`,
  `internal/bridge`, or `internal/db`.
