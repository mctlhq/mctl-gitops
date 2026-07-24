# Design: issue-298-headless-worker-option-c-production-tran

## Current state

**The agent HTTP surface (#296) is already complete and idle.** `internal/agentapi` (package doc,
`server.go:1-9`) is explicitly documented as "the restricted HTTP surface the communication
agent's worker (whatever process invokes Claude — a headless Option-C worker today, an
experimental Channels bridge later) talks to." `Server.Register` (`server.go:104-117`) mounts
every route this worker needs:

- `GET /events` — long-poll job claim (`events.go`'s `handleEvents`), returns
  `{"jobs": [{job_id, event_id, conversation_id, attempt, deadline}]}`.
- `GET /event/{eventID}` — full event body (`handleGetEvent`).
- `GET /conversations/{id}/context` — recent messages + saved lead (`conversations.go`'s
  `handleConversationContext`).
- `GET /recruiters/{peer}` — owner public profile, `501` until #297 wires an
  `OwnerProfileProvider` (`server.go:25-39`).
- `GET /leads/{id}` — `handleGetLead`.
- `GET /policy` — advisory policy snapshot (`misc.go`'s `handlePolicy`).
- `POST /actions/propose_reply`, `POST /leads`, `POST /actions/request_owner_approval`,
  `POST /notify/summary`, `POST /autopilot/pause` — all state-changing, all run through
  `internal/agent/policy.Evaluate` server-side (`actions.go`).
- `POST /jobs/{id}/complete` — terminal job status; `handleJobComplete` already **refuses**
  `status=completed` with a `409` unless `HasAgentActionForJob` or `HasJobLeadForJob` is true
  (`events.go:194-217`) — the "no complete without persisted result" rule from the issue is
  already a hard server-side invariant, not something #298 needs to re-implement client-side.

**Auth.** `POST /api/agent/token` (`tokenhandler.go`) mints a long-lived (`default 30d, max 90d`)
JWT with `aud="agent"` for one target `telegram_id` — this is the `AGENT_API_TOKEN` credential a
worker carries. It is admin-minted, not self-service, and is explicitly "NOT reachable by the
agent surface itself" (a worker cannot mint its own replacement).

**Job lifecycle.** `internal/agent/queue.Queue` (`queue.go`) wraps `internal/db`'s `agent_jobs`
table: `Claim` (SKIP LOCKED, returns `Attempts` as the fencing token echoed back on complete),
`Complete` (compare-and-set on `attempt`), `Retry`/`RequeueStale` (backoff and dead-letter).
Notably, **`Queue.Retry` (and `Store.RetryAgentJob`) is never called from any `agentapi` HTTP
handler** — grepping the package confirms the only caller is `queue.go` itself, with no route
wired to it. The only externally reachable terminal actions are `completed` / `failed` /
`ignored` via `POST /jobs/{id}/complete`, and the only way a job returns to `pending` after a
failed/incomplete attempt is the sweeper's `RequeueStale` after `AGENT_JOB_VISIBILITY` (default
5 min, `cmd/server/main.go`'s `sweeper.AgentJobs`) elapses. This confirms the issue's stated
model: workers don't get a client-triggerable "retry later" — they either finish the job (via a
model-issued `complete_agent_job` call) or they don't, and letting the claim lapse is the
supported failure path.

**Policy stays authoritative regardless of the model.** `handleProposeReply` and
`handleOwnerFacing` call `policy.Evaluate` unconditionally on every state-changing action
(`actions.go:193-202`, `:352-356`); `GET /policy` is explicitly "advisory only" (`misc.go:23-27`).
Nothing about running the model inside a headless `claude -p` process changes this — it is
already true for any future caller of this API.

**No consumer exists yet.** `cmd/server/main.go` wires `agentQueue`, `agentListener`
(producer side — ingests Telegram events into jobs) and, when `cfg.AgentEnabled`, mounts
`agentapi.New(...)` at `/api/agent/v1`. Nothing in the repo calls `GET /events`. Jobs enqueued by
`agent/listener` currently sit until `RequeueStaleAgentJobs` eventually dead-letters them.

**Existing precedents to build on:**
- `cmd/local/daemon.go`'s `runDaemon`/`daemonSession` (`main.go:98-256` in `cmd/local`) is this
  repo's canonical long-running-client reconnect loop: token refresh 5 min before expiry,
  exponential backoff (`reconnectBase=2s`, `reconnectMax=60s`) that resets after a session ran
  "long enough to indicate healthy connectivity," structured `slog` logging throughout. The
  worker's `GET /events` poll loop should follow the same shape.
- `cmd/canary/main.go` is this repo's precedent for a **black-box second binary**: "This binary
  has no imports from `github.com/mctlhq/mctl-telegram/internal/`. It is intentionally a
  black-box HTTP client so it validates the public surface" — config entirely from env vars, its
  own small local structs for wire shapes, built as a second `go build -o` line in the same
  Dockerfile builder stage and copied into the same final image (`Dockerfile:11-27`).
- `internal/mcp/server.go` shows the established way this repo exposes an MCP tool surface, using
  `github.com/mark3labs/mcp-go` (`go.mod`, already a dependency at `v0.54.0`):
  `mcpserver.NewMCPServer` + `mcplib` tool builders, currently wired to
  `mcpserver.NewStreamableHTTPServer`. `mcp-go` also supports a stdio server mode, which is what a
  `claude -p --mcp-config` subprocess consumes.
- `internal/mcp/format.go`'s `untrustedContentNotice` / content-wrapping convention (also
  duplicated in `cmd/local`'s daemon-side `wrapContent`, `cmd/server/main.go:26-48`) wraps
  Telegram-sourced text in `<telegram-content untrusted="true">...</telegram-content>` before it
  reaches a model, with escaping to prevent a message from injecting a fake closing tag. Checking
  `internal/agentapi/events.go`'s `handleGetEvent` and `conversations.go`'s
  `handleConversationContext`, **neither applies this wrapping** to `Body`/message text — this is
  a real gap relative to every other place this codebase hands Telegram content to a model.

## Proposed solution

Add `cmd/agent-worker/` as a new, mostly self-contained Go binary, architecturally a hybrid of the
two existing precedents: `cmd/local`'s reconnect-loop shape for the outer poll/backoff loop, and
`cmd/canary`'s black-box-HTTP-client shape for its dependency footprint (no `internal/db`,
`internal/agentapi`, or MTProto imports — only `internal/audit`'s redacting `slog` handler is
reused, since consistent secret redaction is worth the small coupling and the worker logs the
same categories of sensitive data — tokens, message bodies — that handler already exists to
protect).

**1. Poll loop (`cmd/agent-worker/main.go`, `poll.go`).** A `runWorker(ctx, cfg)` function
modeled directly on `cmd/local/daemon.go`'s `runDaemon`: loop `GET /events?limit=1` with the
configured `AGENT_API_BASE_URL` and `AGENT_API_TOKEN`; on a claimed job, process it serially
(see below); on transport-level failure (non-2xx unexpected status, connection error), back off
exponentially (base 2s, cap 60s, resetting after a sufficiently long healthy poll period) exactly
like `reconnectBase`/`reconnectMax` in `cmd/local`. An empty `{"jobs": []}` response is the normal
long-poll-timeout case (`events.go:96-101`) and simply loops immediately, matching the server's
`defaultLongPollTimeout` of 20s.

**2. MCP tool bridge (`cmd/agent-worker/tools.go`).** Build one `*mcpserver.MCPServer` (stdio
transport, `mcp-go`) registering exactly the 11 tools named in the issue. Each tool handler is a
thin, mechanical translator:

| MCP tool | HTTP call |
|---|---|
| `propose_reply` | `POST /actions/propose_reply` |
| `save_job_lead` | `POST /leads` |
| `send_owner_summary` | `POST /notify/summary` |
| `request_owner_approval` | `POST /actions/request_owner_approval` |
| `complete_agent_job` | `POST /jobs/{id}/complete` |
| `get_event` | `GET /event/{eventID}` |
| `get_conversation_context` | `GET /conversations/{id}/context` |
| `get_policy` | `GET /policy` |
| `pause_autopilot` | `POST /autopilot/pause` |
| `get_lead` | `GET /leads/{id}` |
| `get_recruiter_profile` | `GET /recruiters/{peer}` |

No shell, filesystem, or generic HTTP tool is ever registered on this server — this is a
structural guarantee (the `claude` CLI only sees whatever tools the `--mcp-config`-referenced
server advertises), not a prompt-level instruction. Each handler:
- Marshals the MCP tool's typed args to the matching JSON request body / path params (mirroring
  the request DTOs already defined server-side, e.g. `proposeReplyRequest`,
  `completeJobRequest`, `saveLeadRequest`, `ownerNotifyRequest` in `internal/agentapi`, redeclared
  locally rather than imported — see Alternatives).
- Sends the HTTP request with `Authorization: Bearer $AGENT_API_TOKEN`, retrying on 5xx with
  exponential backoff bounded by the remaining time to the job's `deadline` (passed into the tool
  bridge's context at job-start).
- For `get_event` and `get_conversation_context` specifically, wraps returned free-text fields
  (`body`, per-message `body`) in the same `<telegram-content untrusted="true">...` boundary
  `internal/mcp/format.go` uses, including the same `</telegram-content>` escape-on-injection
  treatment — closing the gap noted in Current State, without touching `internal/agentapi` itself.
- Returns the (now-wrapped, where relevant) JSON body as the MCP tool result, or an MCP tool-level
  error string on a non-2xx response after retries are exhausted.
- For `complete_agent_job` only: forwards verbatim and does nothing else. The worker process
  itself never calls `POST /jobs/{id}/complete` on its own initiative — only in direct response to
  the model invoking this tool. This is what makes "never complete merely after the local
  invocation returns" automatically true: there is no code path that calls `/complete` except
  this one relay, and it only fires on an explicit model tool call.

**3. Claude invocation (`cmd/agent-worker/claude.go`).** For each claimed job:
1. Compute a hard deadline from the job envelope's `deadline` (RFC3339) minus a safety margin
   (e.g. 30s, so the worker can still observe/log the outcome before the server-side visibility
   timeout would reclaim the job out from under it).
2. Start the MCP stdio server (in-process, same binary — `cmd/agent-worker` supports a hidden
   `agent-worker mcp-server` mode so `claude -p --mcp-config` can `exec` the same binary as its
   own tool-server subprocess, or equivalently the bridge runs as an in-process stdio pipe
   attached to the `claude` child — either wiring is an implementation detail, not a contract
   change).
3. Exec `claude -p "<seed prompt>" --mcp-config <path> --allowedTools propose_reply,save_job_lead,...`
   with a context bound to the deadline from step 1. The seed prompt embeds the **trusted**
   metadata the model needs to act (`job_id`, `attempt`, `event_id`, `conversation_id`) directly
   as plain instructions — these are worker/server-generated identifiers, not Telegram-sourced
   content, so they carry no prompt-injection risk and do not need the untrusted-content wrapper.
   The actual message body is deliberately *not* pre-embedded; the model fetches it itself via
   `get_event`/`get_conversation_context`, which is where the untrusted-content wrapping from
   step 2 above applies.
4. On process exit (clean, non-zero, or killed at the deadline), log the outcome (exit code,
   duration, whether `complete_agent_job` was observed) and return to the poll loop. No further
   action is taken — per the acceptance criteria, an incomplete job is left for the sweeper.

**4. Config (`cmd/agent-worker/config.go`).** Env-only, no `internal/config` import (that struct
is `cmd/server`'s and pulls in unrelated concerns): `AGENT_API_BASE_URL`, `AGENT_API_TOKEN`
(never logged — reuse `internal/audit.NewRedactingHandler` as `cmd/server/main.go` does),
`AGENT_WORKER_POLL_LIMIT` (default 1), `AGENT_WORKER_JOB_DEADLINE_MARGIN` (default 30s),
`CLAUDE_BIN` (default `claude`, override for test doubles).

**5. Docker (`Dockerfile`).** Add one more `go build` line in the existing builder stage
(`ARG APP_VERSION` already threaded through) producing `/mctl-telegram-agent-worker`, and one
more `COPY --from=builder` line into the final `alpine` stage, exactly matching how
`mctl-telegram-canary` was added. `ENTRYPOINT` stays `mctl-telegram` (the HTTP server); the worker
image is the same image, invoked with a different command in its Deployment spec (mirrors how
`mctl-telegram-login` and `mctl-telegram-canary` already ship in the same image without being the
default entrypoint).

**6. Tests (`cmd/agent-worker/*_test.go`).** An `httptest.Server` fake implementing the subset of
`/api/agent/v1/*` routes the worker calls (not a full `agentapi.Server` — a fake, per the issue's
"fake agent API (httptest)" requirement, so tests don't need a real `db.Store`/SQLite setup and
can assert exactly what the worker sent). Covers: each of the 11 tool-to-HTTP mappings; a 5xx
sequence that succeeds after N retries with backoff observed; and a scenario where `claude -p`
(faked via `CLAUDE_BIN` pointing at a test script) exits without calling `complete_agent_job` —
asserting the fake server's `/jobs/{id}/complete` endpoint is never hit.

**7. Docs (`docs/agent-worker.md`, linked from `README.md`).** Describes the job loop
(claim → spawn `claude -p` with the MCP bridge → relay tool calls → rely on the model's own
`complete_agent_job` call), the crash-safety argument (visibility timeout + fencing `attempt`
token means no worker-side crash recovery is needed), and cross-references
`docs/claude-channels-spike.md` in `mctl-claude-remote#32` for why the original Channels-bridge
design for this same issue was abandoned.

## Alternatives

1. **Two-phase dispatch: `claude -p --json-schema` produces one structured JSON action, the
   worker parses it afterward and performs the HTTP call(s) itself**, rather than giving the model
   live MCP tool access during the run. Dropped: this contradicts the issue's explicit "restricted
   agent MCP tools only" framing (structured-output-only means no tools at all), and it would push
   the "durably persisted before complete" bookkeeping into worker-side client logic that
   duplicates the `HasAgentActionForJob`/`HasJobLeadForJob` check `handleJobComplete` already
   performs server-side — strictly worse (two places to keep in sync) for no benefit. Recorded as
   an explicit open question/interpretation in `requirements.md` rather than silently assumed.

2. **Extract a shared `internal/agentapi/wire` (or similar) package with the request/response
   DTOs, imported by both `agentapi` and the new worker**, instead of the worker hand-declaring
   small mirror structs. Dropped for this proposal: `agentapi`'s own package doc frames the JSON
   HTTP contract itself as the decoupling boundary ("the ONLY way agent code reaches mctl-telegram
   data... every state-changing call still passes through policy"), and `cmd/canary` already
   establishes the norm in this repo of a black-box binary defining its own minimal wire structs
   rather than importing `internal/*` packages built for the server process. A shared types
   package is a reasonable follow-up refactor once a second HTTP-only consumer exists, but is not
   required to ship #298 and would add import-graph coupling (pulling `internal/db` status-string
   constants etc. into a lightweight worker binary) for marginal DRY benefit.

3. **Run the worker as a library goroutine inside `cmd/server` (in-process) instead of a separate
   binary/process**, avoiding a second Docker target and subprocess management entirely. Dropped:
   the issue explicitly specifies "ships in the mctl-telegram image as a second binary
   (multi-stage Dockerfile target)," and in-process execution would mean a `claude -p` subprocess
   crash/hang shares fate with the HTTP server process — exactly the blast-radius coupling the
   existing `cmd/local`/`cmd/canary`/`cmd/login` separate-binary precedent in this repo avoids.
   Running as its own process also lets the worker scale (or restart) independently per
   communication-agent account without touching `cmd/server`'s availability.

## Platform impact

- **Migrations:** none. No schema change — the worker is a pure consumer of `internal/agentapi`
  and the existing `agent_jobs`/`agent_actions`/`job_leads` tables via HTTP only.
- **Backward compatibility:** additive only. `AGENT_ENABLED` (server-side, default `false`)
  already gates the entire `/api/agent/v1` surface off by default; deploying this worker changes
  nothing for accounts where the communication agent isn't enabled. The worker itself fails
  closed (retries with backoff, never crash-loops) if `AGENT_ENABLED` is off or the target
  account has no `AgentProfile` (`GET /policy` 404s), per the acceptance criteria.
- **Resource impact:** one new process per active communication-agent account (see Open
  questions), each holding one MTProto-account-scoped JWT and spawning short-lived `claude -p`
  subprocesses (one at a time, serial). CPU/memory cost is dominated by the `claude -p` child
  process lifetime, not the Go worker itself, which stays close to idle between jobs (long-poll +
  occasional subprocess spawn). No new load on the Telegram MTProto pool (`internal/telegram`) —
  all Telegram sends still flow through the existing hosted pool via `agentapi`'s handlers, which
  the worker never bypasses.
- **Risks + mitigations:**
  - *Prompt injection via Telegram message content reaching the model.* Mitigated by applying the
    same `<telegram-content untrusted="true">` wrapping convention client-side in the worker's
    `get_event`/`get_conversation_context` tool relay (Current State identified this wrapping is
    currently missing from `agentapi`'s responses); the model is also instructed, via the same
    convention used elsewhere, to surface suspicious instructions rather than act on them.
  - *Leaked `AGENT_API_TOKEN`.* Mitigated by reusing `internal/audit`'s redacting `slog` handler
    and never interpolating the token into any log line, error message, or the `claude -p` prompt
    text itself (only the `Authorization` header carries it, exactly as `cmd/local`'s
    `refreshBridgeToken` treats its own bearer token).
  - *A worker that never calls `complete_agent_job` for a class of jobs (bug, or the model
    consistently refusing).* Bounded by the existing dead-letter path: `RequeueStaleAgentJobs`
    retries up to `max_attempts` before dead-lettering (`agent_jobs.go`), so a systematically
    broken worker surfaces as a growing `mctl_agent_dead_letter_total` metric rather than silently
    losing jobs forever — this is pre-existing infrastructure from #288, unchanged by #298.
  - *`claude -p` production auth/licensing unresolved (see Open questions in requirements.md).*
    No code-level mitigation possible from this repo; flagged for the operator/gitops side.
  - *Running one process per account may not scale past a handful of accounts.* Explicitly scoped
    as a future optimization (Open questions), not blocking this proposal, since the current
    Communication Agent workstream targets a small number of pilot accounts.
