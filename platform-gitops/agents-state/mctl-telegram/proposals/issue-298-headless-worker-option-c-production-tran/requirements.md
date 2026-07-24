# Headless worker (Option C, production transport) for the communication agent

## Context
Issue #298 was originally scoped as a Claude Code Channels stdio bridge for the MCTL
Communication Agent (plan: tranquil-sleeping-map, workstream A-PR8). It was retitled and
rescoped on 2026-07-22: per the operator's review of the Channels spike
(`mctl-claude-remote#32`), the Channels/PTY research-preview feature is not viable as a
production transport — it is unstable and its per-launch
`--dangerously-load-development-channels` confirmation dialog has no non-interactive bypass
without a Team/Enterprise `allowedChannelPlugins` org policy, which mctlhq's claude.ai account
does not have. That experimental adapter moved to a separate issue. #298 is now specifically the
production transport: a plain headless Go worker process ("Option C") that polls the
transport-agnostic agent API built in #296 (`internal/agentapi`) and drives `claude -p` as a
non-interactive subprocess, with no dependency on Channels.

This matters because the agent API surface (#296) and the job queue/policy engine it sits on
(`internal/agent/queue`, `internal/agent/policy`) are already merged and idle without a consumer:
nothing currently claims jobs from `GET /api/agent/v1/events` or exercises the
propose/approve/send loop end to end. Without this worker, incoming Telegram DMs enqueue jobs
that sit until the visibility-timeout sweeper dead-letters them — the communication agent cannot
actually respond to anyone.

## User stories
- AS the mctlhq operator I WANT a headless worker process that claims communication-agent jobs
  and invokes Claude non-interactively SO THAT DMs get triaged and drafted without depending on
  the unstable Channels research-preview feature.
- AS the server-side policy engine (`internal/agent/policy`) I WANT every worker-driven action to
  still flow through the existing `/api/agent/v1/actions/*` HTTP surface SO THAT
  `policy.Evaluate` remains the sole authority regardless of what the model inside `claude -p`
  decides, and the model can never bypass approval/deny/kill-switch checks.
- AS an operator debugging a stuck job I WANT the worker to never double-ack a job and to rely on
  the existing visibility-timeout mechanism (#288, `sweeper.AgentJobs` /
  `queue.RequeueStale`) SO THAT a crashed worker process requeues safely with no bespoke
  crash-recovery code to maintain.
- AS a security reviewer I WANT the model's tool surface restricted to exactly the 11 agent JSON
  API tools (no shell, no filesystem, no generic HTTP) SO THAT a compromised or misbehaving
  worker invocation cannot execute arbitrary commands or exfiltrate data outside the audited API.
- AS the on-call engineer I WANT structured `slog` logs and metrics for job claim, dispatch,
  retry, and completion SO THAT worker failures are diagnosable the same way every other
  long-running process in this codebase already is (`cmd/local`'s daemon loop,
  `internal/metrics`).
- AS the owner of a connected Telegram account I WANT a drafted reply that requires my approval
  to actually wait for `/mctl approve` before sending, with an AI-disclosure line SO THAT the
  agent never sends on my behalf without my explicit say-so.

## Acceptance criteria (EARS)
- WHEN the worker process starts THE SYSTEM SHALL long-poll `GET /api/agent/v1/events` using the
  configured `AGENT_API_TOKEN` bearer credential and process claimed jobs, honoring each job
  envelope's `job_id`, `attempt`, and `deadline` fields exactly as returned (see
  `internal/agentapi/events.go`'s `jobEnvelope`).
- WHEN a job is claimed THE SYSTEM SHALL start a `claude -p` (print/non-interactive) child
  process whose only available tools are an MCP server exposing exactly the 11 agent tools:
  `propose_reply`, `save_job_lead`, `send_owner_summary`, `request_owner_approval`,
  `complete_agent_job`, `get_event`, `get_conversation_context`, `get_policy`,
  `pause_autopilot`, `get_lead`, `get_recruiter_profile`.
- WHILE `claude -p` is running THE SYSTEM SHALL NOT expose a shell tool, filesystem tool, or
  generic HTTP tool to the model — the only way the model reaches mctl-telegram or Telegram data
  is through the 11 tools, each a thin translation to one `/api/agent/v1/...` endpoint.
- WHEN the model invokes one of the 11 MCP tools THE SYSTEM SHALL translate the call into the
  corresponding `/api/agent/v1/...` HTTP request (`POST /actions/propose_reply`, `POST /leads`,
  `POST /notify/summary`, `POST /actions/request_owner_approval`, `POST /jobs/{id}/complete`,
  `GET /event/{eventID}`, `GET /conversations/{id}/context`, `GET /policy`,
  `POST /autopilot/pause`, `GET /leads/{id}`, `GET /recruiters/{peer}`) using `AGENT_API_TOKEN`
  in the `Authorization` header, and SHALL return the real HTTP response back to the model as the
  tool result.
- IF an `/api/agent/v1/...` call fails with a 5xx status THEN THE SYSTEM SHALL retry that call
  with exponential backoff, bounded by the remaining time until the job's `deadline`, before
  surfacing a tool error to the model.
- WHEN the model invokes `complete_agent_job` THE SYSTEM SHALL forward it verbatim to
  `POST /jobs/{id}/complete` with the `attempt` value from the original job envelope — the
  worker SHALL NOT synthesize its own completion call after `claude -p` merely exits, whether it
  exits successfully, with an error, or is killed at its deadline.
- IF `claude -p` exits without the model having called `complete_agent_job` THEN THE SYSTEM SHALL
  take no completion action and leave the job claimed; the existing visibility-timeout sweeper
  (`sweeper.AgentJobs` → `queue.RequeueStale`) SHALL be relied on to requeue it — no additional
  crash-recovery logic SHALL be implemented in the worker beyond not double-acking.
- WHEN `POST /jobs/{id}/complete` returns 409 (stale attempt, already completed under a newer
  claim) THE SYSTEM SHALL log the outcome and drop the job locally without retrying the complete
  call.
- WHERE the worker relays `get_event` or `get_conversation_context` results to the model THE
  SYSTEM SHALL wrap untrusted Telegram-derived text fields (event `body`, conversation message
  `body`) in the same `<telegram-content untrusted="true">` prompt-injection boundary that
  `internal/mcp/format.go` and `cmd/server/main.go`'s `wrapContent` already apply to hosted and
  Local Bridge MCP reads, since `internal/agentapi`'s `GET /event/{eventID}` and
  `GET /conversations/{id}/context` handlers do not apply that wrapping themselves.
- WHILE the worker runs THE SYSTEM SHALL NOT log the value of `AGENT_API_TOKEN` or any Telegram
  message body, matching this repo's redaction discipline (`internal/audit/redact.go`).
- WHEN a long-poll or tool-call HTTP request fails at the transport level (connection refused,
  timeout) THE SYSTEM SHALL retry with exponential backoff (mirroring `cmd/local/daemon.go`'s
  `runDaemon` reconnect-loop shape: base/cap backoff, reset after a sufficiently long healthy
  period) rather than crash-looping the process.
- WHEN the worker binary is built THE SYSTEM SHALL be added as a second `go build` target in the
  existing multi-stage `Dockerfile` (alongside `mctl-telegram`, `mctl-telegram-login`,
  `mctl-telegram-canary`) and copied into the same final `alpine` image as a distinct entrypoint
  binary (e.g. `mctl-telegram-agent-worker`).
- WHERE tests are concerned THE SYSTEM SHALL include Go unit tests against a fake agent API
  (`net/http/httptest`) covering: MCP tool invocation to HTTP call mapping for each of the 11
  tools, retry-with-backoff on 5xx responses, and the no-complete-without-a-model-issued-call
  behavior (i.e., the worker never calls `/jobs/{id}/complete` on its own initiative).
- WHERE documentation is concerned THE SYSTEM SHALL add a `docs/` section describing the worker's
  job loop and its relationship to the transport-agnostic agent API, cross-referencing
  `docs/claude-channels-spike.md` in `mctl-claude-remote#32` for why the Channels bridge design
  was replaced by this one.
- WHEN this proposal is considered implementation-complete THE SYSTEM SHALL have been exercised
  in one real end-to-end run: an inbound Telegram DM produces a claimed job, a draft reply is
  proposed, policy evaluates to `require_approval`, the pending-approval prompt reaches Saved
  Messages, an owner's `/mctl approve` command is applied, and the reply is sent with its AI
  disclosure line appended (per `policy.DisclosureSep` / the executor's disclosure convention).
- IF the target account's agent surface is disabled (`AGENT_ENABLED=false` server-side, or the
  worker's token/account has no agent profile — `GET /policy` 404s) THEN THE SYSTEM SHALL treat
  this as a retryable condition with backoff rather than exiting or crash-looping, since the
  worker cannot distinguish "not configured yet" from "temporarily disabled."

## Out of scope
- The Channels/PTY experimental adapter — moved to a separate issue; this proposal does not
  reintroduce a Channels dependency anywhere.
- Any changes to `internal/agentapi`, `internal/agent/policy`, or `internal/agent/queue` — #296
  is a precondition (must already be merged) and this worker is purely a consumer of that surface.
  The one exception noted above (client-side untrusted-content wrapping) is implemented in the
  worker, not by editing `agentapi`.
- `internal/agent/profile` / the recruiter public-profile provider (#297) — the worker only
  requires `GET /recruiters/{peer}` to exist as a route; it already degrades to `501` server-side
  without a wired `OwnerProfileProvider`, and the worker treats that the same as any other tool
  error surfaced to the model.
- Minting or rotating `AGENT_API_TOKEN` values — `POST /api/agent/token` (admin-only) already
  exists (`internal/agentapi/tokenhandler.go`); token provisioning/rotation for a deployed worker
  is an operational/gitops concern, not a code change in this repo.
- Multi-account fan-out from a single worker process (see Open questions).
- Kubernetes Deployment manifests, HPA, and dashboards for the new worker — this repo's `deploy/`
  directory only holds the canary CronJob and ingress config; per `CLAUDE.md`, actual deployment
  wiring is dispatched to the centralized `mctl-gitops` workflow, out of scope here beyond
  documenting the required environment variables.
- Any change to how `claude -p` itself is authenticated/licensed in production (Claude Code
  credentials) — flagged as an open question, not solved by this proposal.

## Open questions
- **One worker per account vs. multi-account fan-out.** The issue's singular `AGENT_API_TOKEN`
  env var implies one worker process (or replica) is bound to one owner's agent token, since a
  minted agent token authenticates as one specific `telegram_id` (see
  `tokenhandler.go`'s `mintAgentTokenRequest.TelegramID` comment: "the TARGET account... not the
  calling admin's own identity"). This proposal adopts **one worker process per connected
  account**, horizontally scaled by running one replica (or one lightweight goroutine loop with
  its own token) per active communication-agent account, as the simplest interpretation
  consistent with the issue text. Fan-out to N accounts from one process is a plausible future
  optimization but is not assumed here.
- **Structured output vs. live MCP tool calls.** The issue mentions both "the restricted agent
  MCP tools only... and `--json-schema` for structured output" and "parses the structured result,
  calls the corresponding endpoint." These two phrasings are in tension: if the model has live
  MCP tool access during the `claude -p` run, each tool call already hits the real endpoint
  synchronously — there is no separate "structured result" left to parse and re-dispatch
  afterward. This proposal resolves the tension in favor of **live MCP tool calls as the sole
  action-dispatch mechanism** (matching the concrete tool list given) and treats `--json-schema`
  (or an equivalent final-turn structured summary) as an **observability artifact only** — a
  machine-readable summary the worker logs/emits as a metric label, not a second dispatch path.
  This interpretation is what makes the "never complete merely after the local invocation
  returns" requirement trivially satisfiable: completion happens if and only if the model calls
  `complete_agent_job`, which IS the persisted `/jobs/{id}/complete` call.
- **Claude Code / `claude -p` production credentials.** Nothing in this repo indicates how a
  headless worker process authenticates to run `claude -p` in production (Claude Code account
  auth vs. an API key). This is assumed to be an operational secret supplied via the deploy
  environment (mirroring how `TG_API_ID`/`TG_API_HASH`/`ENCRYPTION_KEY` are supplied to
  `cmd/server` today) and is out of scope for code changes in this repo.
- **Per-job concurrency.** The issue's crash-recovery note ("no special crash-recovery logic
  needed... beyond not double-acking") reads most naturally as one job in flight at a time per
  worker instance, matching `GET /events`'s default `limit=1`. This proposal assumes **serial
  processing per worker process**; running multiple `claude -p` invocations concurrently within
  one process is left as a future optimization, not required here.
- If the issue's expectations differ from these interpretations, they are still the most
  reasonable reading of the text and the existing `internal/agentapi` contract; the proposal
  proceeds on this basis rather than blocking on clarification.
