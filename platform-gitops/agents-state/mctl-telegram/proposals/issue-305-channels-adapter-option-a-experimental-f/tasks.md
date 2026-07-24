# Tasks: issue-305-channels-adapter-option-a-experimental-f

- [ ] 1. Scaffold `cmd/agent-channel` package: `main.go` with env-based config loading
      (`AGENT_CHANNEL_ENABLED`, `AGENT_API_URL`, `AGENT_API_TOKEN`, `AGENT_CHANNEL_POLL_TIMEOUT`),
      fail-fast startup checks, and `slog` logging setup consistent with `cmd/local/main.go`'s
      pattern — DoD: `go build ./cmd/agent-channel` succeeds; running the binary with the flag unset
      or either required var empty exits non-zero with a clear stderr message and makes no network
      call.

- [ ] 2. Implement `agentapiClient` in `cmd/agent-channel` covering every route registered in
      `internal/agentapi/server.go`'s `Register()`: `GetEvents`, `GetEvent`, `GetPolicy`,
      `ProposeReply`, `RequestOwnerApproval`, `NotifySummary`, `AutopilotPause`, `SaveLead`,
      `GetLead`, `RecruiterProfile`, `ConversationContext`, `CompleteJob` (depends on 1) — DoD: each
      method sends the correct HTTP method/path/bearer-auth header, request struct field names match
      `internal/agentapi`'s handlers (`jobEnvelope`, `eventResponse`, `completeJobRequest`,
      `policyResponse`, etc.), and non-2xx responses surface a typed error distinguishing 4xx
      (terminal) from 5xx/transport (retryable).

- [ ] 3. Implement exponential-backoff-with-jitter retry wrapper around `agentapiClient` calls,
      applied only to 5xx/transport failures, capped at a sane max interval/attempt count
      (depends on 2) — DoD: unit-testable via an injectable sleep function (no real multi-second
      sleeps in tests); a 4xx response is never retried.

- [ ] 4. Wire an `mcp-go` `server.NewStdioServer` instance declaring the `claude/channel`
      experimental capability, with one MCP tool registered per `agentapiClient` method, proxying
      1:1 with no independent policy logic added (depends on 2) — DoD: `mcp-go`'s stdio transport
      starts and responds to a tool-list/tool-call round trip in a local smoke test; tool handler
      code contains no autonomy/rate/kill-switch logic beyond what it forwards to/from the JSON API.

- [ ] 5. Implement the long-poll event loop that calls `GetEvents`, and for each claimed job emits
      one `notifications/claude/channel` notification (short wake-up text + `event_id`/`job_id` in
      `meta`, no event body) over the stdio server, bounded by `ctx` and the poll-timeout config
      (depends on 3, 4) — DoD: loop runs until context cancellation (SIGINT/SIGTERM handled like
      `cmd/local/main.go`'s daemon), an empty `jobs` response causes an immediate clean re-poll (no
      error, no backoff), and each non-empty response produces exactly one notification per job.

- [ ] 6. Add `AGENT_API_TOKEN` to `internal/audit/redact.go`'s sensitive-field list and confirm no
      code path in `cmd/agent-channel` logs the raw token (depends on 1) — DoD: a redaction unit
      test (mirroring the existing tests in `internal/audit/redact_test.go`) asserts a log record
      containing an `agent_api_token`/`AGENT_API_TOKEN`-named field is scrubbed.

- [ ] 7. Scaffold `cmd/agent-channel-harness` (separate binary) that shells out under a PTY
      (e.g. `github.com/creack/pty`) to `claude --dangerously-load-development-channels
      server:agent-channel`, watches for the "I am using this for local development" confirmation
      prompt, and answers it programmatically; add a doc header stating this is a manual,
      one-off verification tool, never invoked by `cmd/agent-channel` or any deploy/CI path
      (depends on 4) — DoD: `go build ./cmd/agent-channel-harness` succeeds; the harness is not
      referenced from `Dockerfile`, `docker-compose.yml`, `deploy/`, or any GitHub Actions workflow.

- [ ] 8. Run the harness manually once (operator action, not automated by this task list) against a
      real or test Telegram account with the communication agent enabled, capturing one full
      event -> Claude -> reply-tool round trip; write `docs/agent-channel-harness-run.md` with a
      dated, redacted transcript excerpt and the `event_id`/`job_id` involved (depends on 5, 7) —
      DoD: the doc exists, contains no message bodies/phone numbers/session strings/tokens (per
      `internal/audit/redact.go`'s existing redaction rules, applied manually to the transcript
      before committing), and clearly states the run's outcome (success/failure and any follow-up
      needed).

- [ ] 9. Add the `## Channels adapter (experimental)` README section: what it is, off-by-default
      status, env vars, notification contract, explicit experimental/non-production callout, and
      links to `docs/claude-channels-spike.md` (mctl-claude-remote#32) and the plan's
      (tranquil-sleeping-map) Transport decision (depends on 1, 5) — DoD: section renders correctly
      in README.md, placed per design.md's proposed location (after "Connecting to ChatGPT Apps",
      before "Operations: Canary account").

- [ ] 10. Update `.env.example` with `AGENT_CHANNEL_ENABLED`, `AGENT_API_URL`, `AGENT_API_TOKEN`,
       `AGENT_CHANNEL_POLL_TIMEOUT` entries, each commented with purpose and default, matching the
       existing `AGENT_*` entries' style (depends on 1) — DoD: `.env.example` documents every new
       var the adapter reads; no real secret values committed.

## Tests

- [ ] T1. `cmd/agent-channel`: startup fails fast (no network call attempted) when
      `AGENT_CHANNEL_ENABLED` is unset/false, or `AGENT_API_URL`/`AGENT_API_TOKEN` is empty.
- [ ] T2. `cmd/agent-channel`: each `agentapiClient` method against an `httptest.Server` fake sends
      the expected method/path/headers/body and correctly parses a fixture response shaped like the
      real `internal/agentapi` handler output.
- [ ] T3. `cmd/agent-channel`: a fake long-poll response with N claimed jobs produces exactly N
      `notifications/claude/channel` emissions, each with the correct `event_id` in `meta` and no
      event body embedded.
- [ ] T4. `cmd/agent-channel`: a fake long-poll response with zero jobs (empty `jobs` array, HTTP 200)
      does not trigger backoff and results in an immediate re-poll.
- [ ] T5. `cmd/agent-channel`: a sequence of fake 5xx responses triggers increasing backoff delays
      (asserted via an injectable clock/sleep, not wall-clock sleeping) before a subsequent success is
      processed normally.
- [ ] T6. `cmd/agent-channel`: a fake 4xx response (e.g. 404 on `GetEvent`) is surfaced as a
      terminal error for that call and is not retried.
- [ ] T7. `internal/audit`: redaction test confirms `AGENT_API_TOKEN`-named fields are scrubbed from
      structured logs.
- [ ] T8. `go vet ./...` and `golangci-lint run` pass with the new packages included.

## Rollback

- The adapter and harness are additive, opt-in, and disconnected from the production entrypoint:
  rollback is `git revert` of the PR(s) that added `cmd/agent-channel`, `cmd/agent-channel-harness`,
  the README section, and the `.env.example`/`internal/audit/redact.go` additions. No DB migration
  exists to reverse.
- If a deployment somehow set `AGENT_CHANNEL_ENABLED=true` and the adapter misbehaves (e.g. hammers
  `/api/agent/v1` after a backoff bug), the immediate operational mitigation is unsetting
  `AGENT_CHANNEL_ENABLED` (or simply not running the `cmd/agent-channel` process — it is not managed
  by any deploy manifest in this proposal, so "rollback" is typically just "stop the manually-started
  process"). The existing `AGENT_KILL_SWITCH` also still applies server-side to any action the
  adapter attempts to propose, independent of the adapter's own state.
- `docs/agent-channel-harness-run.md` is a point-in-time record and does not need rollback; if it
  turns out to contain anything sensitive despite the redaction step, that is a follow-up doc-only
  fix (amend or remove the file), not a code rollback.
