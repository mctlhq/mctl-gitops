# Design: issue-872-feat-agent-760-slice-2-live-coalescing-b

## Current state

**Ingest.** `internal/agent/listener/listener.go:305` calls `queue.Ingest`, which calls
`Store.InsertEventEnqueueJobAndTouch` (`internal/db/agent_ingest_atomic.go`). That method
writes one `incoming_events` row and one `agent_jobs` row per message in one
transaction, and the write is idempotent on `event_id`. With operator routing on, it
writes no `event_outbox` row for a job-backed event (`if !s.operatorRouting || jobID == 0`).
`InsertEventAndEnqueueJob` (`internal/db/agent_jobs.go`) is the older variant of the same
write. The `agent_jobs` schema is in `internal/db/agent_schema.go` (CREATE TABLE near
line 464). New columns are added with `addColumnIfMissing`, as was done for `cost_usd`
and `result_lead_id`. The status column is free `TEXT` with no CHECK constraint. The
statuses are defined in `agent_jobs.go`: `pending`, `processing`, `completed`, `failed`,
`dead_letter`, `ignored`.

**Claim.** `Store.ClaimAgentJobs` (`internal/db/agent_jobs.go:305`) runs one
`UPDATE ... WHERE id IN (SELECT ... FOR UPDATE SKIP LOCKED)`. The `NOT EXISTS` clause
makes a job claimable only when no other job of its conversation is `processing` and
no earlier job of it is `pending`. So at most one job per conversation is in flight
across all replicas, and within one batch. Each claim opens an `agent_job_attempts`
row. `queue.Queue.Claim` wraps it with metrics.
`agentapi.handleClaimJobs` (`internal/agentapi/events.go`) long-polls with `?limit=`
(capped at 10). For each job it returns a `jobEnvelope{job_id, event_id,
conversation_id, attempt, deadline, job_token}`, and `mintJobToken` binds the job
token to the job, attempt and conversation. `handleGetEvent` allows a job-bound token
to read only `job.EventID`.

**Worker.** `internal/agentworker/worker.go` `Worker.Loop` calls `PollEvents(ctx, 1)`
and runs the claimed jobs one after another. Its comment calls the sequential design
"a deliberate simplification ... revisit if throughput becomes a real bottleneck".
`ClaudeInvoker` (`claudeinvoker.go`) runs one `claude -p` per job and passes
`AGENT_JOB_ID/ATTEMPT/EVENT_ID/CONV_ID` to the `--mcp-serve` child. The child's
`get_event` tool (`mcpserver.go:111`) returns `b.job.EventID`. `Health` uses
`sync/atomic` only, so it is safe to call from several goroutines.
`cmd/agent-worker/main.go` reads worker config from the environment (`requireEnv`,
`envFloat`), not from `internal/config`.

**Operator routing.** `internal/db/event_outbox.go` defines `RoutePolicyDeny`,
`RoutePolicyRequireApproval` and `RouteWorkerFailure`. `routeJobEventTx` loads one
`(user_id, event_id)` per job, and `insertRoutedOutboxTx` writes
`event_outbox ... ON CONFLICT (event_id) DO NOTHING`, so the first reason wins per
`event_id`. Routing is called from:
- `CompleteAgentJob` and `CompleteAgentJobWithResult` on `failed`;
- `RetryAgentJob` on dead-letter;
- `RequeueStaleAgentJobs` on dead-letter;
- the agent-action recording in `agent_actions.go:253` (deny or require_approval).

`internal/events/envelope.go` `BuildRoutedEnvelope` accepts only that closed set of
reasons. `internal/sweeper/sweeper.go` `AgentJobs` runs `RequeueStale` and
`ExpireStaleAgentActions` once a minute (started in `cmd/server/main.go:406`). Nothing
looks at `pending` jobs that were never claimed. That is the gap documented in the
`EventsOperatorRouting` comment (`internal/config/config.go:363-371`).

**Coalescer.** `internal/agent/turn/turn.go` is pure. `Config{QuietMS, MaxWaitMS,
MaxMsgs, MaxBytes}` requires every limit to be > 0. `Offer` joins an event to the open
turn only if it fits all four limits. An event at or over `MaxBytes` forms its own READY
turn. `Tick(now)` closes windows whose time has passed. `turnID` is
`turn:v1:` + the first 24 hex characters of sha256(sessionKey+firstEventID).
`SessionKey(userID, peerTGID)` is defined there. Slice 1 added no config for these
limits.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`:
  `AGENT_ENABLED: "true"`, `AGENT_KILL_SWITCH: "false"`,
  `EVENTS_OPERATOR_ROUTING: "true"`, `EVENTS_VALKEY_URL` set. Operator routing is
  live on preview, so the unclaimed gap is real there today.
- `$MCTL_GITOPS_ROOT/services/labs/agent-worker-preview/values.yaml`:
  `replicaCount: 1`, `AGENT_MAX_BUDGET_USD: "0.50"`, `AGENT_CREDENTIAL_DOMAIN_ID` set,
  no `AGENT_WORKER_CONCURRENCY`. One worker runs one job at a time.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml` (production): its own
  comment (around line 782) says the file sets no `AGENT_*` variables. The agent queue
  is not active in production, so new code defaults have no effect there.
- I did not call the mctl MCP tools. Runtime state (live pending-job counts, pod
  status) was not observed. This proposal does not depend on it.

## Proposed solution

### 1. Coalescing at claim time (server, `internal/db`)

Coalescing happens inside the claim transaction, over durable rows. It does not happen
in listener memory. Ingest is unchanged: still one `agent_jobs` row per event, and
dedup still keyed on `event_id`. That keeps the all-or-nothing ingest guarantee and
crash safety.

- **Schema** (`agent_schema.go`, `addColumnIfMissing`). Add these columns to
  `agent_jobs`:
  - `turn_id TEXT`;
  - `coalesced_into BIGINT/INTEGER`, with no FK, following the `agent_actions.job_id`
    precedent;
  - `body_bytes INTEGER`. This is the plaintext body length, a size only, never
    content.

  Add `idx_agent_jobs_coalesced_into` (partial, `WHERE coalesced_into IS NOT NULL`).
  Add the statuses `JobCoalesced = "coalesced"` and `JobRouted = "routed"`.
- **Ingest.** `InsertEventEnqueueJobAndTouch` and `InsertEventAndEnqueueJob` write
  `body_bytes = len(ev.Body)`.
- **Config** (`internal/config`):
  - `AgentTurnQuiet` (`AGENT_TURN_QUIET`, default 0 = coalescing off);
  - `AgentTurnMaxWait` (`AGENT_TURN_MAX_WAIT`, default 15s);
  - `AgentTurnMaxMsgs` (`AGENT_TURN_MAX_MSGS`, default 10);
  - `AgentTurnMaxBytes` (`AGENT_TURN_MAX_BYTES`, default 16384).

  When coalescing is on, `Validate` requires every limit to be > 0. The config is wired
  to the store with `Store.WithTurnCoalescing(turn.Config)` (nil or off means today's
  path), following the `WithOperatorRouting` style.
- **Claim** (`ClaimAgentJobs`). Coalescing off: the code path and SQL are unchanged.
  Coalescing on:
  1. SELECT candidate heads with today's predicates (`pending`, due, user-scoped,
     `NOT EXISTS`, `FOR UPDATE SKIP LOCKED` on Postgres), ordered as today, with
     `LIMIT` set to a fixed scan cap (`claimCandidateScan = 100`). A head that is still
     collecting must not take a slot from another conversation's ready head.
  2. For each candidate, in order, until `limit` jobs are claimed:
     - If the head already has `turn_id` (a retry or a stale requeue), it was coalesced
       before. Claim it with its frozen membership.
     - Otherwise, load the conversation's other `pending` jobs with `attempts = 0`,
       ordered by `id` (locked). Build `turn.New(cfg)` and `Offer` the head and then each
       follower, with `At = created_at`, `Bytes = COALESCE(body_bytes, 0)`, and
       `SessionKey = turn.SessionKey(user_id, incoming_events.chat_tg_id)`. Then call
       `Tick(now)`.
     - If the head's turn (the turn whose `SourceEventIDs[0]` is the head's event) is
       not READY, skip the head.
     - If it is READY, run `UPDATE` to claim the head (same columns as today, plus
       `turn_id`). Then run `UPDATE agent_jobs SET status='coalesced',
       coalesced_into=$head, turn_id=$tid WHERE id IN (members) AND status='pending'`,
       and open the attempt row as today.

     Jobs without a conversation are not coalesced: each is its own one-event turn.
  3. Return `AgentJob` with the new fields `TurnID` and `SourceEventIDs` (head first,
     arrival order).

  A `now` hook (`Store.now func() time.Time`, default `time.Now`) lets tests drive the
  windows deterministically. The `turn.Coalescer` is built per claim and thrown away
  afterwards. It is never shared, which suits its "not safe for concurrent use" rule.

  Results are deterministic. The membership and `turn_id` come only from event ids,
  their `created_at` values and the config. The time of the claim matters only through
  the "window has closed" gate, and `Offer` never joins an event outside its window. So
  replaying the same rows gives the same turn id. The retry path reuses the frozen
  membership.

  Coalesced members are neither `pending` nor `processing`, so they never block the
  `NOT EXISTS` rule. Membership moves only in the same transaction as the head's claim.
- **Completion and retry.** The head's status is authoritative, and members stay
  `coalesced`. `routeJobEventTx` changes to route every source event: it reads
  `SELECT user_id, event_id FROM agent_jobs WHERE id = $1 OR coalesced_into = $1
  ORDER BY id` and calls `insertRoutedOutboxTx` for each row. First reason still wins
  per `event_id`. `GetAgentJob` fills `SourceEventIDs`. `purgeAgentJobs` already
  deletes by user and covers members.
- **API** (`internal/agentapi/events.go`). `jobEnvelope` gains `turn_id` and
  `source_event_ids`. `event_id` stays the head's event, so older workers keep working.
  `handleGetEvent` allows a job-bound token to read any event in
  `job.SourceEventIDs`.
- **Worker** (`internal/agentworker`). `JobEnvelope` and `JobContext` gain `TurnID` and
  `SourceEventIDs`. `ClaudeInvoker` passes `AGENT_JOB_SOURCE_EVENT_IDS` (comma-joined;
  event ids contain no commas) to the child. `get_event` returns all the turn's events in
  arrival order (`{"events": [...]}`), fetched one by one from the API. With a single
  event the shape stays compatible: the head event is also returned in the old top-level
  fields. The prompt does not name event ids, as today (`claudeinvoker.go:292`).

### 2. Bounded worker pool (`internal/agentworker`, `cmd/agent-worker`)

- `cmd/agent-worker/main.go` reads `AGENT_WORKER_CONCURRENCY` with a new `envInt` helper
  (default 1, must be 1..10; 10 is the server's `?limit=` cap) and calls
  `NewWorker(...).WithConcurrency(n)`.
- `Worker.Loop` uses a slot semaphore (a buffered channel of size N):
  1. Wait for at least one free slot.
  2. Call `PollEvents(ctx, freeSlots)`.
  3. Start one goroutine per claimed job. Each goroutine has its own `ParsedDeadline`
     context and releases its slot when done.

  Logging and outcomes stay as they are. On ctx cancel, Loop stops polling and
  `WaitGroup.Wait()`s for in-flight jobs (each is still bounded by its own deadline),
  then returns. With N=1, the poll-then-run order matches today's behaviour.
- Per-conversation exclusion stays server-side and unchanged (`NOT EXISTS` against
  `processing`). As defence in depth, the worker keeps an in-flight
  `conversation_id -> struct{}` set. If a claimed job's conversation is already running,
  the worker logs an error and waits for that job to finish before starting the new one.
  It never runs the two together. This should never trigger, and a test pins that it
  does not.
- Every job already gets its own subprocess, job token and MCP child, so `ClaudeInvoker`
  holds no per-job mutable state. The pool tests run under `go test -race`.

### 3. Routing unclaimed jobs (`internal/db`, `internal/sweeper`, `internal/events`)

- Add `RouteWorkerUnclaimed = "worker_unclaimed"` to the closed set in `event_outbox.go`,
  and accept it in `events.BuildRoutedEnvelope`.
- Add `Store.RouteUnclaimedAgentJobs(ctx, after time.Duration) (int64, error)`. If
  operator routing is off or `after <= 0`, it does nothing. Otherwise, in one
  transaction:

  ```sql
  UPDATE agent_jobs SET status='routed', last_error='unclaimed past threshold, routed to operator', updated_at=$now
   WHERE status='pending' AND attempts=0 AND created_at < $cutoff
  RETURNING id
  ```

  It then calls `routeJobEventTx(ctx, tx, id, RouteWorkerUnclaimed)` for each returned
  id, commits, and runs `notifyOutbox`.
  - `attempts = 0` means "never claimed". A job claimed before the threshold is never
    routed as unclaimed, even if a retry or stale requeue later puts it back to
    `pending`.
  - The UPDATE and the claim's `UPDATE ... WHERE status = pending` serialize on the row
    lock. On SQLite the single connection serializes them. So exactly one of "routed" and
    "claimed" wins.
  - Moving the job to terminal `routed` is what enforces "no double handling": a worker
    that comes back cannot answer after the operator took over.
  - First reason wins through the existing `ON CONFLICT (event_id) DO NOTHING`. An event
    already routed for another reason gets no second row, but its job still leaves
    `pending`.
- `queue.Queue.RouteUnclaimed` counts `routed` in the metrics. `sweeper.AgentJobs` gains
  an `unclaimedAfter` argument and calls it each tick after `RequeueStale`.
  `cmd/server/main.go:406` passes `cfg.AgentUnclaimedRouteAfter`.
- Config: `AgentUnclaimedRouteAfter` (`AGENT_UNCLAIMED_ROUTE_AFTER`, default 5m).
  `Validate` refuses a value <= 0 when routing is on, and a value <= `AgentTurnMaxWait`
  when coalescing is on. Otherwise a job could be routed while its turn is still
  legitimately collecting.
- The `EventsOperatorRouting` comment drops the "Known gap" text. It now describes
  `worker_unclaimed`, the threshold, and the fact that routing worst-case latency is
  threshold + one sweep interval (1 minute).

## Alternatives

1. **Coalesce in the listener's memory (hold events, enqueue one job per turn).** Rejected.
   Events held only in memory are lost on a pod restart. That breaks the
   all-or-nothing ingest that `InsertEventEnqueueJobAndTouch` exists for, and it needs
   per-conversation timers across listener supervisors. Claim-time coalescing gets the
   same result over durable rows.
2. **Coalesce at ingest (attach each new event to an open pending job through a
   `agent_job_events` join table).** Rejected. It complicates the dedup transaction.
   Closing the window still needs a time gate at claim. Changing the 1:1
   `agent_jobs.event_id` relationship would break routing, the existing `event_id`
   uniqueness and older workers, all at once.
3. **Route unclaimed jobs but leave them `pending` (publish only).** Rejected. A worker
   that came back would then also answer, which is double handling and violates the
   owner's decision. Dead-lettering the job instead was also considered and rejected:
   `dead_letter` feeds `AgentDeadLetterTotal`, which means "the worker failed", and that
   is the wrong signal here.
4. **Concurrency through several worker replicas only.** Possible today, but each replica
   needs its own pod and resources, and the issue explicitly asks for an in-process
   bound.

## Platform impact

- **Migrations.** Additive only: three nullable columns and one partial index, added
  through `addColumnIfMissing` on both Postgres and SQLite. There is no backfill. Old
  rows have `body_bytes` NULL, which is treated as 0, and `turn_id` NULL, which is
  coalesced at first claim like any fresh job.
- **Backward compatibility.** Every new behaviour defaults off or to today's behaviour:
  coalescing off (`AGENT_TURN_QUIET=0`), concurrency 1, and unclaimed routing only with
  `EVENTS_OPERATOR_ROUTING` on (only preview sets it). The new envelope fields are
  additive. An old worker against a server with coalescing on would see only the head
  event, so the worker must be rolled out first. That ordering is noted in
  `docs/agent-worker.md`.
- **Preview behaviour change once this ships.** Preview already runs
  `EVENTS_OPERATOR_ROUTING=true`. Unclaimed routing turns on there with the 5m default
  even without the separate gitops PR. That is the intended fix, but it does change
  preview behaviour: a job that had been stuck pending for more than 5 minutes at deploy
  time is routed on the first sweep.
- **Resources.** The claim transaction does more work when coalescing is on: up to 100
  candidate heads plus their followers. These are indexed lookups, bounded per poll and
  per second. With concurrency N, a worker pod runs N `claude` processes at once, so
  memory, CPU and Anthropic spend scale with N. `AGENT_MAX_BUDGET_USD` stays per job.
  Raising N on preview is a separate gitops decision and needs a resource review.
- **Latency.** With coalescing on, every reply waits at least the quiet window.
- **Risks and mitigations.**
  - *A member event is lost from the turn.* Membership is written in the same
    transaction as the claim, and `source_event_ids` comes from the database. Routing
    covers every member.
  - *A routing-versus-claim race.* Both are status compare-and-sets on the same row
    (T3.4).
  - *Concurrency bugs.* The tests run under `-race`, there is the in-flight conversation
    guard, and the default stays N=1.
  - *Metric label drift.* `coalesced` and `routed` are new status labels. This is
    called out in the PR and the docs.
