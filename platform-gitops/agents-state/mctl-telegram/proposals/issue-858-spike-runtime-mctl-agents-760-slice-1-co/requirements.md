# Runtime slice 1 for mctl-agents#760: ConversationTurn v1 coalescer, admission simulator, conversation-bound job token, operator routing

## Context

mctl-agents#760 is a spike on per-conversation persistent sessions with bounded execution and burst coalescing. Its architecture comment found that most of the session plane already exists in mctl-telegram: the `conversations` table (unique on `(user_id, peer_tg_id)`), the `agent_jobs` queue, and the `ClaimAgentJobs` `NOT EXISTS` clause in `internal/db/agent_jobs.go`, which already serializes each conversation. So the first execution slice lands here. The issue (mctl-telegram#858) asks for four things: a pure `ConversationTurn v1` coalescer, an admission simulator over the existing claim path (test code only), a job token bound to its conversation on the server, and operator routing. With routing, the operator stream gets only the messages the conversation worker did not handle.

Three owner decisions recorded on mctl-agents#760 bind this slice. First, no double handling: only the `agent_jobs` worker answers a chat message, and the operator gets only deny, require_approval and worker-failure events. Second, the worker keeps the cold `claude -p` run with database context; there is no per-chat `--resume`. Third, the token must be bound to its conversation on the server in this slice. Today every worker job, and the `claude -p` MCP subprocess it spawns, uses one long-lived account-wide `aud=agent` token (`AGENT_API_TOKEN`, see `internal/agentworker/claudeinvoker.go`). The relay also publishes every `telegram.message.*` envelope at ingest (`internal/db/agent_ingest_atomic.go` -> `insertOutboxTx`). Both are what this proposal changes.

## User stories

- AS a platform architect I WANT a pure, table-tested `ConversationTurn v1` coalescer SO THAT the turn contract for mctl-agents#760 is checked in code before any runtime uses it.
- AS a platform architect I WANT an admission simulator over the real `ClaimAgentJobs` path SO THAT global and per-user concurrency caps can be shown to keep one turn per session and starve no session, without deploying a worker pool.
- AS an account owner I WANT each job's credential limited to the conversation it is answering SO THAT a prompt-injected model in one chat cannot read or write another of my chats through the agent API.
- AS the operator session in mctl-claude-remote I WANT only the chat events the worker did not take, with the reason SO THAT I never reply twice to a message the worker already answered.

## Acceptance criteria (EARS)

Coalescer (`internal/agent/turn`):
- WHEN a message event arrives for a `session_key` that has no turn in `COLLECTING` state THE SYSTEM SHALL open a new turn with `window_opened_at` set to the event time and the event id as the first entry of `source_event_ids`.
- WHEN a message event arrives for a session whose `COLLECTING` turn received its last event no more than `quiet_ms` earlier, and adding it would not exceed `max_msgs` or `max_bytes`, THE SYSTEM SHALL append the event id to that turn's `source_event_ids` in arrival order.
- WHEN `quiet_ms` has passed since a `COLLECTING` turn's last event THE SYSTEM SHALL move that turn to `READY`.
- WHEN `max_wait_ms` has passed since `window_opened_at` THE SYSTEM SHALL move the turn to `READY`, even if events keep arriving inside the quiet window.
- WHEN a turn reaches `max_msgs` events, or adding an event would exceed `max_bytes`, THE SYSTEM SHALL close the window (`READY`), and a later or overflowing event SHALL open a new turn.
- WHEN three events arrive inside one quiet window THE SYSTEM SHALL produce exactly one turn with three `source_event_ids` in arrival order. An event after the window closes SHALL produce a new turn.
- THE SYSTEM SHALL allow only the transitions `COLLECTING -> READY -> CLAIMED -> DONE` and SHALL reject any other transition with an error.
- THE SYSTEM SHALL implement the coalescer without I/O, clocks or goroutines: time is passed in by the caller, and the package imports only the standard library.
- THE SYSTEM SHALL derive `session_key` as `telegram:<user_id>:<peer_tg_id>`, where `user_id` is `users.id`, which matches the `conversations(user_id, peer_tg_id)` unique key.

Admission simulator (test code):
- WHILE the simulator runs 10 sessions with `max_concurrent_global = 5` THE SYSTEM SHALL never have more than 5 jobs in `processing` at once.
- WHILE the simulator runs THE SYSTEM SHALL never have more than one `processing` job per conversation.
- WHILE the simulator runs with a `max_concurrent_per_user` cap THE SYSTEM SHALL never have more than that many `processing` jobs per user.
- WHEN the simulation ends THE SYSTEM SHALL have completed every session's jobs within a bounded number of rounds, and the test SHALL assert that bound.
- THE SYSTEM SHALL drive admission only through `Store.ClaimAgentJobs` / `CompleteAgentJob` against a SQLite fixture, and SHALL NOT add a production worker pool.

Conversation-bound job token:
- WHEN `POST /api/agent/v1/jobs/claim` returns a job THE SYSTEM SHALL include a short-lived job token. The token carries the job's `job_id`, `attempt`, `conversation_id` and the owner's Telegram id, uses the audience `agent-job`, and expires no later than the job's claim deadline.
- WHEN a request authenticated by a job token names a conversation id other than the token's `conversation_id`, whether in the URL path, the JSON body, or through a job, lead or action that belongs to another conversation, THE SYSTEM SHALL reject it with HTTP 403. It SHALL record the refusal through `Server.audit` with status `denied` and a reason naming the conversation mismatch.
- WHEN a request authenticated by a job token names a `job_id` or `attempt` other than the token's THE SYSTEM SHALL reject it with HTTP 403 and audit it the same way.
- IF a job token is presented to `POST /jobs/claim` or `GET /events` THEN THE SYSTEM SHALL reject it with HTTP 403 and audit it as `denied`, so a job token can never claim or list work. The only account-scoped routes a job token may call are `GET /policy` and pause-only `POST /autopilot/pause`, which the MCP subprocess uses today and which expose no other conversation.
- WHEN a request authenticated by a job token stays within its own conversation THE SYSTEM SHALL behave exactly as it does today for the account token.
- WHEN the worker spawns `claude -p` for a job THE SYSTEM SHALL give the MCP subprocess (`AGENT_API_TOKEN` in the mcp-config env block) the job token, never the account-wide worker token.
- THE SYSTEM SHALL keep accepting the existing account-wide `aud=agent` token on every route it accepts today, so an older worker keeps working during rollout.

Operator routing:
- WHILE operator routing is enabled THE SYSTEM SHALL NOT write an `event_outbox` row at ingest for a `telegram.message.*` event that was enqueued as an `agent_jobs` row.
- WHEN the policy decision for a job's `propose_reply` action is `deny` THE SYSTEM SHALL write exactly one outbox envelope for the job's source event with subject `routing_reason = policy_deny`.
- WHEN the policy decision for a job's `propose_reply` action is `require_approval` THE SYSTEM SHALL write exactly one outbox envelope for the job's source event with subject `routing_reason = policy_require_approval`.
- WHEN a job reaches `dead_letter`, or is completed with status `failed`, THE SYSTEM SHALL write exactly one outbox envelope for the job's source event with subject `routing_reason = worker_failure`.
- WHEN a job completes with an executed (allowed) reply, or with `ignored`, THE SYSTEM SHALL write no outbox envelope for its source event.
- THE SYSTEM SHALL keep the envelope reference-only, as `BuildEnvelope` in `internal/events/envelope.go` does today: no message body, no policy reason text, only the closed `routing_reason` enum.
- IF operator routing is disabled (the default) THEN THE SYSTEM SHALL publish exactly as it does today.

## Out of scope

- Per-chat `--resume`, Temporal topology, deploying a worker pool, attention semantics (mctl-agents#757, parked), and any change to the operator session itself.
- Wiring the coalescer into the listener or the claim path. In this slice it is a pure, tested package that production code does not call.
- Changes to mctl-claude-remote. If consuming the reduced stream needs one, it is filed there as a separate issue.
- Enforcing `max_concurrent_global` / `max_concurrent_per_user` in production `ClaimAgentJobs`.
- Revoking a job token before it expires (it is short-lived and attempt-pinned).

## Open questions

- Envelope reason field: the canonical schema `mctlhq/.github events/schemas/event-envelope.v1.schema.json` is described as closed, and its subject rules could not be read from this clone. This proposal adds `subject.routing_reason` (string enum). If the schema does not allow an extra subject key, the schema needs a v1 minor addition in mctlhq/.github first, or the reason moves to the envelope `type` instead (for example `telegram.message.routed`). Reviewer: confirm which.
- `require_approval` forwarding: decision 1 forwards `require_approval` to the operator, but the owner also gets an approval notification today. The proposal forwards it as a signal, not a reply request. Whether the operator should act on it is an operator-session concern and out of scope here.
- Dedup when one event both ends in `require_approval` and later fails: the outbox has a unique `event_id`, so only the first reason is forwarded. The proposal accepts that (the first reason already gives the event to the operator). Report this back to mctl-agents#760 as a contract finding.
- Rollout gate: the proposal adds `EVENTS_OPERATOR_ROUTING` (default `false`). Without it, merging would silently cut the operator stream in preview, where both `AGENT_ENABLED` and `EVENTS_VALKEY_URL` are set.
- Per-user cap semantics in the simulator: the issue gives `N=5` only for the global cap. The proposal uses 10 sessions over 4 synthetic users with `max_concurrent_per_user = 2`, and also tests the degenerate one-user case.
