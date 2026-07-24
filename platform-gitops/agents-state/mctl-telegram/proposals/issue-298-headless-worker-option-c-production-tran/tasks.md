# Tasks: issue-298-headless-worker-option-c-production-tran

- [ ] 1. Scaffold `cmd/agent-worker/` package (`main.go`, `config.go`) with env-only config
      (`AGENT_API_BASE_URL`, `AGENT_API_TOKEN`, `AGENT_WORKER_POLL_LIMIT`,
      `AGENT_WORKER_JOB_DEADLINE_MARGIN`, `CLAUDE_BIN`), `slog` JSON logging wrapped in
      `internal/audit.NewRedactingHandler` (same setup as `cmd/server/main.go`), and a
      `-version` flag consistent with the other `cmd/*` binaries — DoD: `go build ./cmd/agent-worker`
      succeeds; `AGENT_API_TOKEN` is never written to stdout/stderr even at debug log level
      (verified by a test that greps captured log output for the token value).

- [ ] 2. Implement the agent-API HTTP client (`cmd/agent-worker/client.go`): typed request/response
      structs mirroring `internal/agentapi`'s wire shapes for all 11 routes (deliberately
      hand-declared, not imported — see design.md Alternatives #2), bearer-auth header injection,
      and exponential-backoff retry on 5xx bounded by a caller-supplied deadline — DoD: each of the
      11 calls has a corresponding client method; retry/backoff logic is unit-testable in isolation
      from the MCP layer.

- [ ] 3. Implement the MCP tool bridge (`cmd/agent-worker/tools.go`) using `github.com/mark3labs/mcp-go`
      (depends on 2) — registers exactly the 11 tools (`propose_reply`, `save_job_lead`,
      `send_owner_summary`, `request_owner_approval`, `complete_agent_job`, `get_event`,
      `get_conversation_context`, `get_policy`, `pause_autopilot`, `get_lead`,
      `get_recruiter_profile`), each delegating to the matching client method from task 2 — DoD: a
      test enumerating the MCP server's registered tool names asserts the set is exactly these 11,
      no more, no fewer (guards against an accidental 12th tool creeping in later).

- [ ] 4. Add untrusted-content wrapping to the `get_event` / `get_conversation_context` tool
      handlers (depends on 3): wrap `body`/message-`body` text fields in
      `<telegram-content origin="telegram" peer=... untrusted="true">...</telegram-content>` with
      the same `</telegram-content>` escape-on-injection treatment as
      `internal/mcp/format.go` — DoD: a test feeds a fake event body containing a literal
      `</telegram-content>` sequence and asserts it is escaped, not able to close the boundary
      early.

- [ ] 5. Implement job processing (`cmd/agent-worker/claude.go`, depends on 3): given a claimed
      job envelope, compute the deadline-minus-margin context, start the MCP stdio bridge, exec
      `claude -p` (binary path from `CLAUDE_BIN`) with `--mcp-config`/`--allowedTools` restricted
      to the 11 tools and a seed prompt containing only trusted identifiers (`job_id`, `attempt`,
      `event_id`, `conversation_id`) — never pre-embedding message content — and log the outcome
      on exit — DoD: `complete_agent_job` is only ever invoked in response to the model calling
      that tool; a table-driven test with a fake `claude` script (via `CLAUDE_BIN`) that exits
      without calling any tool proves `POST /jobs/{id}/complete` was never hit.

- [ ] 6. Implement the outer poll loop (`cmd/agent-worker/poll.go`, depends on 5): long-poll
      `GET /events`, reconnect/backoff on transport errors mirroring `cmd/local/daemon.go`'s
      `runDaemon` shape (base 2s / cap 60s, reset after a healthy period), signal-aware shutdown
      (`signal.NotifyContext`, matching `cmd/server/main.go`) — DoD: `go run ./cmd/agent-worker`
      against a fake agent API claims and processes a job end-to-end in a smoke test; SIGTERM
      during an in-flight `claude -p` invocation lets that invocation finish or hit its deadline
      before the process exits, rather than being killed mid-tool-call.

- [ ] 7. Wire `cmd/agent-worker` into the Dockerfile (depends on 1): add a `go build` line in the
      builder stage producing `/mctl-telegram-agent-worker` and a `COPY --from=builder` line into
      the final `alpine` stage, matching the existing `mctl-telegram-canary` pattern — DoD:
      `docker build .` succeeds and `docker run <image> mctl-telegram-agent-worker -version`
      prints a version string.

- [ ] 8. Write `docs/agent-worker.md` (depends on 1-6): job-loop description, the
      "completion only follows a model-issued `complete_agent_job` call" durability argument, the
      crash-safety argument (visibility-timeout requeue, fencing `attempt` token, no bespoke
      recovery code), required env vars, and a cross-reference to
      `docs/claude-channels-spike.md` in `mctl-claude-remote#32` explaining why the original
      Channels-bridge design for this issue was replaced — DoD: linked from `README.md`'s docs
      index (matching how `docs/runbook.md`/`docs/hpa.md`/`docs/slo.md` are referenced today).

- [ ] 9. Real end-to-end run against a staging/pilot account (depends on 1-8, and on #296/#297
      being deployed): send a DM to a connected account, observe the job claimed, a draft
      proposed, `policy.Evaluate` returning `require_approval`, the pending-approval prompt
      landing in Saved Messages, apply `/mctl approve`, confirm the reply sends with its AI
      disclosure line appended — DoD: this run is documented (transcript or screenshot reference)
      and linked from the PR description; this is the issue's explicit "done" bar, not optional
      polish.

## Tests
- [ ] T1. Unit: each of the 11 MCP tool handlers, given valid args, issues exactly the expected
      HTTP method+path+body against a fake `agentapi`-shaped `httptest.Server`, and returns the
      fake's JSON response verbatim as the tool result.
- [ ] T2. Unit: a tool call against the fake server returning `500` twice then `200` succeeds via
      the retry/backoff path in task 2, with observed backoff delays increasing monotonically
      (using an injectable clock/sleep so the test doesn't sleep in real time).
- [ ] T3. Unit: a tool call against the fake server returning `500` past the job's deadline-minus-
      margin budget surfaces an MCP tool-level error rather than retrying forever.
- [ ] T4. Unit: no-complete-without-a-model-call — a fake `claude -p` process (via `CLAUDE_BIN`)
      that calls `propose_reply` then exits (without calling `complete_agent_job`) leaves the fake
      server's `/jobs/{id}/complete` endpoint uncalled; a second fake process that calls
      `propose_reply` then `complete_agent_job` results in exactly one `/jobs/{id}/complete` call
      carrying the original `attempt` value.
- [ ] T5. Unit: `get_event`/`get_conversation_context` responses containing a literal
      `</telegram-content>` in the body text are escaped in the tool result handed back to the
      model (task 4's wrapping).
- [ ] T6. Unit: a `409` response from `/jobs/{id}/complete` (stale attempt) is logged and does not
      trigger a retry of the complete call.
- [ ] T7. Unit: the outer poll loop backs off exponentially (bounded, capped, reset-after-healthy)
      on repeated transport failures from `GET /events`, matching `cmd/local/daemon.go`'s existing
      backoff test coverage style.
- [ ] T8. Integration/smoke (task 6's DoD): one full claim → process → complete cycle against the
      fake agent API, run via `go test` or a documented manual `go run` smoke script.
- [ ] T9. `go vet ./...` and `golangci-lint run` pass for the new package, per `CONTRIBUTING.md`.

## Rollback
- The worker is a new, independently deployed process/binary with no schema migration and no
  changes to `internal/agentapi`, `internal/agent/policy`, or `internal/agent/queue`. Rolling
  back is scaling the worker's Deployment to zero replicas (or simply not deploying the new image
  tag) — the server, MCP surface, and every existing tool continue to operate exactly as before,
  since nothing else in the codebase calls into `cmd/agent-worker`.
- If a bad worker build is already running and misbehaving (e.g., completing jobs incorrectly),
  the operator-facing kill switches already exist and require no code change: `AGENT_KILL_SWITCH`
  (process-wide, env-only, checked by `policy.Evaluate` on every action) or the per-account
  `pause_autopilot` / `autopilot_paused` flag (DB-backed) stop new actions from being authorized
  even if the worker keeps calling the API. Revoking the specific account's `AGENT_API_TOKEN`
  (re-minting invalidates the old JWT's practical use once rotated, since the signer/secret can be
  rotated — see `tokenhandler.go`) is the hard stop if the token itself is suspected compromised.
- Because the worker never persists anything the server doesn't already gate through
  `policy.Evaluate` and `handleJobComplete`'s durability check, there is no worker-specific data
  to clean up on rollback beyond whatever `agent_actions`/`job_leads` rows it legitimately wrote
  through the normal, already-audited API path.
