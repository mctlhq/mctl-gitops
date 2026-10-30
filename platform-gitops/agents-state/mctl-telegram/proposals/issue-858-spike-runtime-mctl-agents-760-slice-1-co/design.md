# Design: issue-858-spike-runtime-mctl-agents-760-slice-1-co

## Current state

Session plane:
- `internal/db/agent_schema.go` defines `conversations` (unique index `idx_conversations_user_peer` on `(user_id, peer_tg_id)`) and `agent_jobs` (`event_id` unique, `user_id`, `conversation_id`, `status`, `attempts`, `max_attempts`, `next_run_at`, `claimed_by`, `claimed_at`). This file is also where schema migrations live, as `CREATE ... IF NOT EXISTS` lists for SQLite and Postgres.
- `internal/db/agent_jobs.go` `Store.ClaimAgentJobs(ctx, replicaID, userID, limit)` claims due `pending` jobs for one user. Its `NOT EXISTS` subquery makes a job claimable only when no earlier job of the same conversation is `pending` or `processing`, so each conversation already runs one job at a time, in arrival order. Postgres adds `FOR UPDATE SKIP LOCKED`; SQLite runs one connection. There is no global or per-user concurrency cap. `RetryAgentJob` moves a job to `dead_letter` when `attempts >= max_attempts`. `CompleteAgentJob` accepts `completed`, `failed` or `ignored`. `RequeueStaleAgentJobs` can also dead-letter a job.
- `internal/agent/queue/queue.go` wraps these with metrics. `Queue.Ingest` calls `Store.InsertEventEnqueueJobAndTouch`.
- There is no turn or coalescing concept: one Telegram message is one `agent_jobs` row.

Agent API and token:
- `internal/agentapi/tokenhandler.go` `NewAgentTokenHandler` mints one long-lived (30-90 day) account-wide JWT: `aud=agent`, `sub=tg:<id>`, `tg_id`. It carries no job or conversation claim.
- `cmd/server/main.go` `selectAgentProvider` checks that token (`ExpectedAudience: "agent"`). Deployed mode is `local-jwt` with issuer `PublicBaseURL`. `shared-hmac` with issuer `https://api.mctl.ai` is also supported.
- `internal/agentapi/server.go` `Register` mounts `/conversations/{id}/context`, `/recruiters/{peer}`, `/leads/{id}`, `/leads`, `/policy`, `/jobs/{id}`, `/actions/propose_reply`, `/actions/request_owner_approval`, `/notify/summary`, `/autopilot/pause`, `/jobs/claim`, `/jobs/{id}/complete`, `/jobs/{id}/cost`, `/events` and `/event/{eventID}`.
- Handlers scope by `id.UserID` only. For example, `handleConversationContext` in `internal/agentapi/conversations.go` calls `Store.GetConversation(ctx, id.UserID, convID)`, so any conversation of the same user is readable. `handleProposeReply` (`actions.go` around line 209-222) checks that a body `job_id` belongs to the body `conversation_id`. That is a consistency check between two caller-supplied values, not a credential binding.
- Refusals are audited through `Server.audit(ctx, userID, tool, status, errMsg)` (`internal/agentapi/json.go`), which calls `Store.LogToolCall`. The existing refused-path precedent is `s.audit(ctx, id.UserID, tool, "denied", persisted.PolicyReasons)` in `actions.go`.
- Worker: `internal/agentworker/claudeinvoker.go` writes a 0600 mcp-config whose env block gives the `claude -p` MCP subprocess `AGENT_API_TOKEN` (the same account-wide token as the poller) plus `AGENT_JOB_ID`, `AGENT_JOB_ATTEMPT`, `AGENT_JOB_EVENT_ID` and `AGENT_JOB_CONV_ID`. `cmd/agent-worker/main.go` reads them. `internal/agentworker/mcpserver.go` keeps the conversation id out of the model's tool arguments, but the token itself would authorize any conversation id.
- Precedent for a scoped credential: `localjwt.Claims.DeviceID` (`internal/auth/localjwt/issuer.go`) and `auth.Identity.DeviceID` (`internal/auth/identity.go`) bind a token to one device row through an extra claim, with no schema change.

Event publication:
- `internal/events/envelope.go` `BuildEnvelope` maps `private_message` and `message_edit` to `telegram.message.created` / `.edited`. The envelope is reference-only: subject `kind`, `account_id`, `chat_id`, `message_id` and `peer`, all strings. The schema is `mctl.events/v1`, and `Marshal` caps it at 4096 bytes.
- `internal/db/event_outbox.go` `insertOutboxTx` writes the `event_outbox` row inside the ingest transaction (`InsertEventEnqueueJobAndTouch`, `internal/db/agent_ingest_atomic.go`). `event_outbox.event_id` is unique. `internal/events/relay.go` `Relay` XADDs pending rows to `mctl:events:telegram`. `cmd/server/main.go` wires `store.WithEventOutbox(events.OutboxBuilder(cfg.EventsStream))` only when `EVENTS_VALKEY_URL` is set.
- So today every message the worker will handle is also sent to the operator at ingest. That is the double handling decision 1 forbids.
- Policy decisions: `internal/agent/policy/policy.go` `Allow | RequireApproval | Deny`. Actions persist with `ActionDenied` / `ActionPendingApproval` (`internal/db/agent_actions.go`).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml` (production): `AUTH_MODE: local-jwt`, `replicaCount` 1, no `AGENT_ENABLED` and no `EVENTS_VALKEY_URL`. The comment near line 781 says the file sets no `AGENT_*` variables. Neither the agent API nor the outbox runs in production, so every change here is inert there.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`: `AUTH_MODE: local-jwt`, `AGENT_ENABLED: "true"`, `AGENT_KILL_SWITCH: "false"`, and `EVENTS_VALKEY_URL: redis://telegram-producer@valkey.platform-events.svc.cluster.local:6379/0`. This is the only environment where both the worker and the operator stream are live, so it is the one routing affects.
- `$MCTL_GITOPS_ROOT/services/labs/agent-worker-preview/values.yaml`: `replicaCount: 1`, `AGENT_API_BASE_URL: http://labs-mctl-telegram-preview-base-service:8080/api/agent/v1`, `AGENT_MAX_BUDGET_USD: "0.50"`, and `AGENT_API_TOKEN` supplied as a secret. One worker replica is consistent with the simulator staying test-only.
- mctl MCP tools were not used. Gitops values were enough for the config facts above. Live pod state and logs were not observed.

## Proposed solution

### 1. `internal/agent/turn`: ConversationTurn v1 coalescer (pure)

A new package that imports only the standard library (`errors`, `time`, `crypto/sha256`, `encoding/hex`, `strconv`).

```go
type State string // COLLECTING | READY | CLAIMED | DONE
type Config struct{ QuietMS, MaxWaitMS int64; MaxMsgs, MaxBytes int }
type Event struct{ ID, SessionKey string; At time.Time; Bytes int }
type Turn struct {
    TurnID, SessionKey string
    SourceEventIDs []string // arrival order
    WindowOpenedAt, LastEventAt time.Time
    QuietMS, MaxWaitMS int64; MaxMsgs, MaxBytes int // config snapshot per turn
    Bytes int; State State
}
func SessionKey(userID, peerTGID int64) string // "telegram:<user_id>:<peer_tg_id>"
func New(cfg Config) (*Coalescer, error)       // validates all limits > 0
func (c *Coalescer) Offer(ev Event) []Turn     // returns turns closed by this event
func (c *Coalescer) Tick(now time.Time) []Turn // closes by quiet_ms / max_wait_ms
func (c *Coalescer) Claim(turnID string) error // READY -> CLAIMED
func (c *Coalescer) Done(turnID string) error  // CLAIMED -> DONE
```

Rules:
- An event joins the open turn only if `ev.At - LastEventAt <= quiet_ms` and `ev.At - WindowOpenedAt <= max_wait_ms`, and the joined turn stays within `max_msgs` and `max_bytes`.
- Otherwise the open turn becomes `READY` and the event opens a new turn.
- A turn that reaches `max_msgs` becomes `READY` at once.
- A single event larger than `max_bytes` forms a one-event `READY` turn, so it is never dropped.
- `turn_id` = `turn:v1:` + hex(sha256(session_key + first source_event_id))[:24]. It is deterministic, so a replay of the same events gives the same id, which matches the listener's deterministic event ids.
- At most one `COLLECTING` turn exists per session. Invalid transitions return `ErrInvalidTransition`.

Time comes only from `Event.At` and `Tick(now)`, so the package does no I/O. Nothing in production imports it in this slice.

### 2. Admission simulator (test code, `internal/db/agent_admission_sim_test.go`)

A `simulator` type inside `package db` tests, using the existing SQLite test-store helper:
- Seed 10 conversations (sessions) over 4 synthetic users (`Alice`, `Bob`, `Carol`, `Dana` personas; ids checked with `git grep` first). Each session gets 3 pending jobs via `EnqueueAgentJob`, with `next_run_at` in the past.
- Each round:
  - Compute the free global slots, `max_concurrent_global - running`.
  - Walk users from a rotating cursor, so the user who started the last round goes last in the next.
  - For each user, call the real `ClaimAgentJobs(ctx, "sim", userID, min(perUserFree, globalFree))`.
  - Record the claimed jobs as running, then complete every job running since the previous round with `CompleteAgentJob(..., JobCompleted, ...)`.
- After each claim, assert the invariants from the database itself (`SELECT conversation_id, COUNT(*) ... WHERE status='processing' GROUP BY ...`), not only from the simulator's own bookkeeping:
  - global processing <= 5;
  - processing per conversation <= 1;
  - processing per user <= the per-user cap.
- Starvation: assert that every job reaches `completed` within `R_max` rounds. `R_max = ceil(total_jobs / 5) + jobs_per_session + users` is a provable bound for round-robin with per-conversation FIFO. Also assert each session's first claim happens within `users` rounds.
- Second case: one user with 10 sessions, so only the global and per-session caps apply.

Per-session concurrency of 1 comes from the existing `NOT EXISTS` clause. The test proves the clause holds under the caps; it does not re-implement it. The caps live only in the simulator.

### 3. Conversation-bound job token

No schema change: the binding lives in signed claims, the same pattern as `DeviceID`.
- `localjwt.Claims` gains `JobID int64 \`json:"job_id,omitempty"\``, `JobAttempt int \`json:"job_attempt,omitempty"\`` and `ConversationID int64 \`json:"conv_id,omitempty"\``. `auth.Identity` gains the same three fields, filled in by `localjwt.Provider.Authenticate`.
- Minting: `agentapi.Server` gains `WithJobTokenSigner(*localjwt.Issuer)`. It is wired in `cmd/server/main.go` with `OAUTH_JWT_SECRET` and this service's own issuer, `strings.TrimRight(cfg.PublicBaseURL, "/")`, in every auth mode. In `handleClaimJobs`, each `jobEnvelope` gets `JobToken string \`json:"job_token,omitempty"\``. The token has `aud=["agent-job"]`, the owner's `sub`/`tg_id`, `job_id`, `job_attempt`, `conv_id`, and TTL = claim deadline - now (`jobVisibility`). It inherits the parent's `Jti` and `OriginalIssuedAt`, as `/api/bridge/token` does, so revoking the worker token also revokes its job tokens. If the signer is unset, the field is omitted and behaviour stays as today.
- Verification: a new `selectAgentJobProvider` builds a `localjwt.Provider` with `ExpectedAudience: "agent-job"` and issuer `PublicBaseURL`. The agent mount's auth middleware tries the existing agent provider first, then the job provider. A small `auth.Provider` composite, or a chained middleware, keeps `aud=agent` tokens working unchanged.
- Enforcement: in `internal/agentapi/binding.go`, `func (s *Server) enforceBinding(w, r, id, tool string, convID, jobID int64, attempt int) bool`. It is a no-op when `id.ConversationID == 0` (the account token). Otherwise any non-zero mismatch writes 403 `{"error":"credential is bound to another conversation"}` and calls `s.audit(ctx, id.UserID, tool, "denied", "conversation binding: token conv=<a> request conv=<b>")`. It is called:
  - from `handleConversationContext` with the path id;
  - from `handleProposeReply`, `handleRequestOwnerApproval`, `handleNotifySummary` and `handleSaveLead` with the body `conversation_id` / `job_id` / `attempt`. When the body omits `conversation_id`, the token's value is used.
  - from `handleGetLead`, after loading the lead, with `lead.ConversationID`;
  - from `handleRecruiterProfile`, which must match the token conversation's `peer_tg_id`;
  - from `handleGetJob`, `/jobs/{id}/complete` and `/jobs/{id}/cost` with the job's id and conversation;
  - from `/event/{eventID}`, which must be the job's own event.
- A `requireAccountToken` guard rejects job tokens (403, audited) on `/jobs/claim` and `/events`, the claim and fan-out surfaces. A job token is narrower than the account token, never wider. Two account-scoped routes stay open to job tokens because the MCP subprocess calls them (`agentAPI` in `internal/agentworker/mcpserver.go`):
  - `GET /policy`, which returns owner policy, not conversation data;
  - `POST /autopilot/pause`, which the server already limits to pausing, since resuming is an owner `/mctl continue` decision.
  Neither exposes another conversation.
- Worker: in `internal/agentworker/client.go`, `jobEnvelope` / `Job` gains `JobToken`. In `claudeinvoker.go`, the mcp-config env block's `AGENT_API_TOKEN` gets `job.JobToken` when it is present and falls back to `c.APIToken` otherwise, so a newer worker still works against an older server. The worker's own complete/retry calls stay on the account token.

### 4. Operator routing

Config: `EVENTS_OPERATOR_ROUTING` (bool, default `false`), read in `internal/config`.
- `Store.WithEventOutbox` gains a routing mode. When the mode is on, `InsertEventEnqueueJobAndTouch` skips `insertOutboxTx` whenever the ingest actually enqueued a job. Today every published event kind there is job-backed, so nothing is published at ingest.
- New `Store.insertRoutedOutboxTx(ctx, tx, userID, eventID, reason string)`. It loads the `incoming_events` row by `event_id` (identifiers only), calls the outbox builder with a reason, and inserts with `ON CONFLICT (event_id) DO NOTHING`. It runs in the same transaction as the state change that causes it:
  - `policy_deny` and `policy_require_approval`: in the transaction that persists the `propose_reply` action with `ActionDenied` / `ActionPendingApproval` (`InsertAgentAction` and its callers in `internal/db/agent_actions.go`). Only for job-tied actions; the source event comes from `agent_jobs.event_id`.
  - `worker_failure`: in `RetryAgentJob` when the status becomes `JobDeadLetter`, in `RequeueStaleAgentJobs` for dead-lettered ids, and in `CompleteAgentJob` / `CompleteAgentJobWithResult` when the status is `JobFailed`.
  - `outboxNotify` is called after commit, as today.
- `events.OutboxBuilder` / `BuildEnvelope` take an optional reason. When set, `Subject["routing_reason"]` is one of the closed constants `policy_deny`, `policy_require_approval` or `worker_failure`. No policy reason text is included, keeping the reference-only guarantee. The `Type` and every other subject key are unchanged, so the operator consumer parses it exactly as before.
- Allowed replies and `ignored` jobs produce nothing: the suppressed happy path.

The DoD's mctl-claude-remote follow-up is filed separately if the consumer needs to read `routing_reason`; this repo does not change it.

### Contract findings to report to mctl-agents#760

Post these as a comment on mctl-agents#760, not just in docs here:
- `session_key` uses `users.id`, not the Telegram account id that the envelope `account_id` uses.
- A single oversized event becomes its own turn.
- `turn_id` is deterministic from the first event.
- Routing dedup is first-reason-wins per `event_id`.

## Alternatives

- **Store the binding in the database (an `agent_job_tokens` table keyed by jti).** This would allow revoking a single job token, but it adds a schema change and a database read on every agent API call. The issue allows a schema change only if task 3 needs one. Signed claims plus a TTL capped at the claim deadline, pinned to the attempt, and parent-jti revocation already contain a leak, so it was dropped.
- **Mint job tokens with `aud=agent` and an extra claim, verified by the existing provider.** This is simpler wiring, but a job token would then be accepted anywhere an account token is, and the binding would hold only where a handler remembers to check it. In shared-hmac mode it would also mean minting under the `https://api.mctl.ai` issuer. A distinct `agent-job` audience under this service's own issuer, plus an explicit account-only guard, fails closed. Dropped.
- **Route in the relay at publish time (filter outbox rows by job state).** No ingest change would be needed, but the relay would have to wait or poll for a job's terminal state, and a crash between decision and publish could lose or duplicate a forward. Writing the outbox row in the deciding transaction keeps the existing transactional-outbox guarantee. Dropped.
- **Wire the coalescer into the listener now.** Out of scope: it would change the runtime unit from message to turn before the contract is reviewed on mctl-agents#760.

## Platform impact

- **Migrations:** none. The binding is claim-based, routing reuses `event_outbox`, and the coalescer and simulator are code or tests only.
- **Backward compatibility:**
  - `aud=agent` tokens keep working everywhere they work today.
  - `job_token` is an additive JSON field. A worker that ignores it keeps today's behaviour, and a worker that expects it falls back when it is absent.
  - Routing is off by default, and the envelope adds one subject key only when routing is on.
- **Deployed impact:** production sets neither `AGENT_ENABLED` nor `EVENTS_VALKEY_URL`, so it is unaffected. Preview is affected only after `EVENTS_OPERATOR_ROUTING: "true"` is set in `services/labs/mctl-telegram-preview/values.yaml`, a separate gitops change made after the agent-worker-preview image that passes job tokens is deployed.
- **Resources:** one HMAC sign per claimed job and one extra provider verify on agent requests. Negligible.
- **Risks and mitigations:**
  - The operator stops seeing chats it relied on. Mitigations: the flag defaults off, the change is preview-only, and `worker_failure` covers every non-success terminal path, including stale-claim dead-letter.
  - The envelope schema rejects `routing_reason`. Mitigation: confirm against `mctlhq/.github` before enabling the flag (Open question). Consumers that validate a closed subject would drop the event.
  - Binding check misses one route. Mitigations: a table test iterates over every route in `Register`, and the account-only guard covers the routes that are not conversation-scoped.
  - The job token outlives a requeued claim. Mitigation: the attempt is pinned, and `CompleteAgentJob` / action inserts already reject a non-active attempt.
