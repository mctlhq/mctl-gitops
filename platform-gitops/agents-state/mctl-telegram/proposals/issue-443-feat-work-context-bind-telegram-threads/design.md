# Design: issue-443-feat-work-context-bind-telegram-threads

## Current state

### Telegram is the owner of investigation state

The communication agent's whole lifecycle is local to this service. The schema
lives in `internal/db/agent_schema.go` (`migrateAgent`, dual-dialect
`agentSchemaSQLite()` / `agentSchemaPG()`), and the relevant tables are:

- `conversations` — per-peer thread state (`peer_tg_id`, `peer_access_hash`,
  `state`, `autonomous_turns`), a recruiter-domain object, not a work object.
- `incoming_events` — one row per Telegram update, keyed by a deterministic
  `event_id`, with the body AES-GCM sealed under the owning user's derived key
  (`internal/db/agent_events.go`, `IncomingEvent`, `InsertIncomingEvent`
  returning `inserted=false` on duplicate).
- `agent_jobs` — the execution queue (`internal/db/agent_jobs.go`, `AgentJob`,
  `EnqueueAgentJob`, `ClaimAgentJobs`, `CompleteAgentJobWithResult`,
  `RequeueStaleAgentJobs`), with `UNIQUE (event_id)` providing enqueue
  idempotency and `claimed_by` / `claimed_at` providing a visibility lease.
- `agent_actions` — proposed sends and their approval lifecycle, including the
  tenant-scoped blind-indexed `approval_code_hash` and per-user encrypted
  `approval_code_encrypted`.

A worker claims jobs over the restricted HTTP surface in
`internal/agentapi/server.go` (`Server.Register` binds `/jobs/claim`,
`/jobs/{id}/complete`, `/actions/propose_reply`,
`/actions/request_owner_approval`, ...), authenticated with an `aud="agent"`
JWT and policed by `internal/agent/policy`. Nothing in this chain has an
identity outside `mctl-telegram`'s own database.

### The Telegram command surface

`internal/agent/control/command.go` parses `/mctl <sub> [arg]` from Saved
Messages into a `Command{Type, Arg}` with a closed `CommandType` set
(`status`, `leads`, `show`, `continue`, `pause`, `takeover`, `approve`,
`reject`, `conversations`). `Router.HandleSavedText`
(`internal/agent/control/router.go`) switches on the type, reads the store, and
replies through `Notifier.Reply`. Approvals go through the `Approver` interface
onto `internal/agent/executor`. The listener
(`internal/agent/listener/listener.go`) filters Saved Messages down to `/mctl`
text before the router is ever called.

There is a second, independent Telegram surface: the Bot API receiver in
`internal/bot` (`Receiver` polling `getUpdates`, `Registry` mapping update kind
to `Handler`, and `Store.DispatchOnce` in `internal/db/bot_updates.go` giving
exactly-once dispatch by running the handler and the processed-mark in one
transaction). `Delivery` deliberately carries routing facts only — no text, no
callback payload — so a handler cannot accidentally log or forward content.

### Cross-surface signalling already exists, reference-only

`internal/events` publishes `mctl.events/v1` envelopes to platform Valkey
Streams. Its package doc states the governing principle directly: "An event is
a signal, not a copy: the envelope names the account, chat and message, and the
consumer hydrates the text through this service's own MCP tools under its own
authorization." `BuildEnvelope` reads only identifiers from `db.IncomingEvent`,
never `ev.Body` or `ev.Meta`, and derives a deterministic envelope id from the
listener's `event_id` so a redelivery deduplicates downstream. Delivery is a
transactional outbox: `internal/db/event_outbox.go` (`insertOutboxTx`,
`AcquireOutboxLease`, `PendingOutbox`, `MarkOutboxPublished`) drained by
`internal/events/relay.go`.

### Identity and authorization

`auth.Identity` (`internal/auth/identity.go`) carries `UserID`, `Subject`
(canonically `tg:<telegram_id>`), `TelegramID`, `Groups`, `Scopes`, `ClientID`,
plus credential-revocation identity. `internal/auth/sharedhmac` verifies JWTs
*issued by* `mctl-api`; `internal/auth/localjwt` issues this service's own. The
important fact for this issue: **there is no outbound HTTP client to `mctl-api`
anywhere in this repo.** Every reference to `api.mctl.ai` in
`cmd/server/main.go` and `internal/auth/` is an expected-issuer string for
inbound verification. A call to a canonical WorkItem API is a new outbound
dependency, new egress, and a new failure mode.

`internal/db/reachability.go` already models "can the bot message this user" as
`client_bot_reachability`, separate from any grant, and
`internal/edgectx/edgectx.go` documents the same discipline for request headers:
"every field here is a header as RECEIVED. It is evidence for reading an audit
trail, never an authorization input."

### There is no thread or topic primitive anywhere in the repo

This is the single most consequential finding for #443. A grep across every
`.go` file returns zero hits for `message_thread_id`, `TopMsgID` or
`reply_to_msg_id`. `telegram.Message` (`internal/telegram/messages.go:31`)
carries `ID int`, `Peer`, `From`, `Text`, `Date`, media — no thread field. The
coarsest grouping that exists is `incoming_events.chat_tg_id` and
`conversations` with `UNIQUE (user_id, peer_tg_id)`, both of which are 1:1 with
a *peer*, not a thread. `bot.Update` (`internal/bot/update.go`) decodes only
`update_id`, `chat.id` and the update kind. So "bind Telegram threads" cannot
reuse an existing identifier — the thread dimension is net-new, and where it
cannot be observed it must degrade to a chat-level binding rather than be
faked.

### Migrations and configuration conventions

`db.Migrate` (`internal/db/db.go:73`) probes the dialect at runtime, applies
either `pgSchema()` (`db.go:773`) or `sqliteSchema()` (`db.go:542`) — two
hand-maintained parallel `[]string` lists of `CREATE TABLE IF NOT EXISTS` and
`CREATE INDEX IF NOT EXISTS` statements — then runs an idempotent additive
`addColumnIfMissing` pass (`db.go:513`), then delegates to `migrateAgent`
(`internal/db/agent_schema.go:22`, with its own
`agentSchemaSQLite()`/`agentSchemaPG()` pair). There is no versioned migration
file mechanism and no version table; `agent_migrations` exists but is only a
marker. **Both dialect lists must always be edited together.**

Configuration is environment-driven (`internal/config/config.go`, `config.Load`
at `:273`, helpers `envBool` / `envInt` / `envInt64` / `envDuration` /
`parseInt64CSV`), names are `SCREAMING_SNAKE_CASE` with no service prefix, and
every substantial subsystem ships behind a default-off flag: `AGENT_ENABLED`,
`BOT_RECEIVER_ENABLED`, `MCP_APPS_ENABLED`.

### Existing idempotency and outbound-client precedents

Three idempotency patterns are already established and should be reused rather
than reinvented:

1. **Unique index as the key** — `incoming_events.event_id` UNIQUE,
   `agent_jobs.event_id` UNIQUE, `agent_actions` UNIQUE
   `(job_id, action_type) WHERE job_id IS NOT NULL`, `bot_updates.update_id` PK,
   `broadcast_deliveries` PK `(campaign_id, user_id)` — whose comment states
   outright that "the primary key IS the idempotency key".
2. **`INSERT ... ON CONFLICT DO NOTHING ... RETURNING id`** yielding
   `sql.ErrNoRows` on duplicate — `InsertIncomingEvent`
   (`internal/db/agent_events.go:73`).
3. **Client-supplied key column** — `local_bridge_devices.idempotency_key`,
   uniquely indexed scoped to `(user_id, idempotency_key)` and to live rows only
   (`idx_local_bridge_devices_idem_live`, `db.go:656`). This is the closest
   existing analogue to what #443 needs.

Deterministic ids also have a precedent:
`eventIDForMessage(accountTGID, chatID, messageID, editDate, body)`
(`internal/agent/listener/extract.go:43`) produces
`evt:v1:<account>:<chat>:<message>[:e<edit_unix>:<12 hex>]`, and that format is
regexp-validated in `internal/events/envelope.go:109` — so it must not be
changed by this work.

For the outbound call, `internal/agentworker/client.go` is the in-repo template:
`Client{baseURL, token string, http *http.Client}` with
`NewClient(baseURL, token, hc)` (nil `hc` → default, trailing slash trimmed), a
single `do(ctx, method, path, body, out) error` applying
`Authorization: Bearer ...`, and a typed `APIError{StatusCode, Message}`.

## Proposed solution

Three new packages, one new table, one new command, one flag-gated MCP tool. No
existing table is altered and no existing code path changes behaviour when the
flag is off.

### 1. `internal/workitem` — the outbound port

A narrow interface describing only what the Telegram adapter needs of the
canonical API, so the unknown wire shape of mctl-api#227 is confined to one
adapter file:

```go
package workitem

type Ref struct {
    WorkItemID  string
    ExecutionID string
    SnapshotID  string
    State       string // canonical state, rendered verbatim; never interpreted
}

type OpenRequest struct {
    IdempotencyKey string
    ActorSubject   string // auth.Identity.Subject, e.g. "tg:123"
    Surface        string // "telegram"
    SurfaceRef     SurfaceRef
    Title          string // short, from the command argument only
}

type Client interface {
    CreateOrOpen(ctx context.Context, req OpenRequest) (Ref, error)
    StartExecution(ctx context.Context, workItemID string, req ExecRequest) (Ref, error)
    Resume(ctx context.Context, workItemID string, req ExecRequest) (Ref, error)
    Get(ctx context.Context, workItemID string) (Ref, error)
}
```

Two implementations, the real one modelled directly on
`internal/agentworker/client.go` (same `baseURL`/`token`/`do(...)`/`APIError`
shape, so a reviewer recognises it on sight):

- `workitem/httpclient` — the real adapter. Bounded `http.Client` timeout,
  bounded retry on idempotent verbs only, `WORK_CONTEXT_API_BASE_URL` and a
  `WORK_CONTEXT_API_TOKEN` bearer. 401/403 map to a distinct `ErrUnauthorized`
  sentinel so the router can surface the platform's refusal verbatim rather
  than reinterpreting it.
- `workitem.Disabled{}` — returns `ErrDisabled` from every method, and is what
  `cmd/server/main.go` wires when `WORK_CONTEXT_ENABLED` is false. This mirrors
  the `OwnerProfileProvider` nil-provider precedent in `internal/agentapi`,
  where an unimplemented dependency degrades to a defined refusal rather than a
  panic.

`Title` is the single piece of user-typed text that crosses the boundary, and
only the text the owner explicitly typed after `/mctl work`. No surrounding
transcript, no history, no `incoming_events` body ever reaches this client.

### 2. `internal/db` — `work_item_bindings`

One new table, created by a new `migrateWorkContext(ctx, dbConn, pg)` called
from `Migrate` alongside `migrateAgent`, with its own
`workContextSchemaSQLite()` / `workContextSchemaPG()` pair following the
existing dual-dialect `CREATE TABLE IF NOT EXISTS` convention (both lists edited
together, always):

```
work_item_bindings(
  id                 PK,
  user_id            FK users(id) ON DELETE CASCADE,
  surface            TEXT NOT NULL DEFAULT 'telegram',
  chat_tg_id         BIGINT NOT NULL,
  thread_id          BIGINT,            -- NULL for a non-forum chat
  root_message_id    BIGINT,            -- the message that opened the work
  idempotency_key    TEXT NOT NULL,
  work_item_id       TEXT NOT NULL,
  last_execution_id  TEXT,
  last_snapshot_id   TEXT,
  state              TEXT NOT NULL DEFAULT 'open',
  created_at, updated_at
)
UNIQUE (user_id, surface, chat_tg_id, thread_id_norm)
UNIQUE (user_id, idempotency_key)
INDEX  (user_id, work_item_id)
```

`thread_id_norm` is a stored `COALESCE(thread_id, 0)` column because SQL `NULL`
does not collide in a unique index, and a chat-level binding must collide with
itself. This is the same class of trap `idx_agent_jobs_event` avoids by keeping
`event_id` non-null, and `idx_local_bridge_devices_idem_live` avoids with its
live-rows predicate.

Because no thread identifier is extracted anywhere today, `thread_id` is
written as `NULL` in this slice and the binding is effectively chat-scoped.
The column exists now, with the collision guard already correct, so that
populating it later from the ingest path
(`internal/agent/listener/extract.go`) or from a widened `bot.Update` is a
value change rather than a schema-and-index change on a table that already has
production rows. Nothing in this proposal touches `eventIDForMessage` or its
`evt:v1:` format, which `internal/events/envelope.go:109` validates by regexp.

Every column is an identifier or a timestamp. There is no body column, no meta
JSON, and therefore nothing for `internal/audit/redact.go` to have to defend.
That is the deliberate contrast with `conversations` and `incoming_events`,
whose bodies are sealed precisely because they contain content.

Store methods, matching existing naming and error style:

- `UpsertWorkItemBinding(ctx, Binding) (Binding, created bool, err error)` —
  `INSERT ... ON CONFLICT DO NOTHING` followed by a read-back, the same
  "returns inserted=false on duplicate" shape as `InsertIncomingEvent` and
  `EnqueueAgentJob`. This is what makes a concurrent double-tap converge.
- `GetWorkItemBinding(ctx, userID, chatTGID, threadID)` → `ErrBindingNotFound`.
- `GetWorkItemBindingByWorkItem(ctx, userID, workItemID)` — the second-surface
  read path.
- `SetWorkItemBindingExecution(ctx, userID, id, executionID, snapshotID, state)`.
- `purgeWorkItemBindings` registered on the existing per-user purge hook next to
  `purgeAgentJobs`.

The idempotency key is derived deterministically, mirroring how the listener
derives `event_id`:
`sha256("telegram:" + userID + ":" + chatTGID + ":" + threadID)`, hex-truncated.
Because it is derived rather than stored-then-reused, a locally lost binding row
still produces the same key and the platform's own idempotency resolves it to
the same WorkItem — which is exactly the "handle already-open work items
idempotently" requirement, enforced on the side that owns the truth.

### 3. `internal/workctx` — the adapter service

The glue that the command router and the MCP tool both call, keeping both thin:

```go
type Service struct {
    Store  *db.Store
    Client workitem.Client
    Authz  Authorizer
    Events func(...)   // optional outbox enqueue
}

func (s *Service) OpenOrResume(ctx, actor Actor, ref SurfaceRef, title string) (workitem.Ref, bool, error)
func (s *Service) Inspect(ctx, actor Actor, ref SurfaceRef) (workitem.Ref, error)
```

`OpenOrResume` is the whole pilot flow:

1. `Authz.Check(ctx, actor)` — refuse early if the deployment's
   `WORK_CONTEXT_OPERATORS` allowlist excludes the actor. This can only narrow;
   it never grants. mctl-api remains authoritative and its 403 is passed
   through unchanged.
2. `GetWorkItemBinding`. If found and non-terminal, call `Client.Resume`
   (execution B against the same WorkItem) rather than `CreateOrOpen`.
3. Otherwise `Client.CreateOrOpen` with the derived idempotency key, then
   `UpsertWorkItemBinding`. Note the ordering: the remote call happens *first*,
   so a failure leaves no local row claiming work that may not exist. The remote
   is idempotent by key, so a crash between the call and the insert costs a
   retry, not a duplicate.
4. `Client.StartExecution` for the investigator, then
   `SetWorkItemBindingExecution` with the returned execution and snapshot ids.
5. Enqueue a reference-only envelope on the existing outbox so a second surface
   can discover the work without polling.

### 4. Command surface: `/mctl work`

Extend the closed `CommandType` set in `internal/agent/control/command.go` with
`CmdWork CommandType = "work"`, parsed like `CmdShow`/`CmdContinue` (argument
required for a new request, optional for a status read). `Router` gains a
`WorkContext *workctx.Service` field; `handleWork` calls `OpenOrResume` and
replies through the existing `Notifier` with a stable reference:

```
Work: <work_item_id>
Execution: <execution_id>
State: <canonical state>
```

When `WorkContext` is nil (flag off) the `case CmdWork` branch is unreachable
because `ParseCommand` is given a gated subcommand set — the parser keeps its
current closed-set behaviour and an unflagged deployment answers `/mctl work`
with the existing unknown-command help text, exactly as it does today.

Approval is display-only. When the canonical state is a pending-approval state,
the router renders it and stops. It does **not** mint an `agent_actions` row, an
approval code, or reuse `Approver`. `/mctl approve|reject` continue to mean what
they mean today (communication-agent actions) and are not overloaded.

### 5. Second surface: a flag-gated MCP tool

`internal/mcp` gains `get_work_context`, built to the package's standard recipe:
one `func (s *Server) toolGetWorkContext() (mcplib.Tool, mcpserver.ToolHandlerFunc)`
with an `outputSchema[T]()` option and a `ReadOnlyHint`, one registration block
in `newMCPServer()` (`internal/mcp/server.go:247`), and an `s.audit(...)` call
in the handler like every other tool. The registration block is guarded by
`WORK_CONTEXT_ENABLED`, so the seven v1.0-locked tools are unchanged for every
existing deployment. It reads the caller from `auth.From(ctx)`, scopes the
lookup to `Identity.UserID`, and returns
`{work_item_id, execution_id, snapshot_id, state, surface_ref}` — identifiers
only, no Telegram content. That is the concrete demonstration of the issue's
acceptance path: Telegram opens the WorkItem and runs execution A; an MCP client
reads the reference through this tool and resumes through the canonical API into
execution B, having never seen a Telegram message.

### Why this shape

The principle the codebase already committed to in `internal/events` — a
reference is a signal, not a copy — is the same principle #443 asks for, applied
one layer up from messages to work. Reusing it means the non-goals ("do not
persist the transcript", "do not make Telegram the WorkItem database") are
enforced structurally by the table's column list rather than by reviewer
vigilance. Putting the remote call before the local insert means the platform's
idempotency, not ours, is the arbiter of duplication, which is the only ordering
that survives a crash without forking work.

## Alternatives

**A. Add `work_item_id` columns to `conversations` and `agent_jobs`.**
Cheapest in lines of code, and it was the first thing considered. Dropped:
`conversations` is a recruiter-domain object with `peer_access_hash`,
`autonomous_turns` and takeover semantics, and `agent_jobs` is a claim queue
whose row lifetime is governed by `AGENT_RETENTION_DAYS` and `purgeAgentJobs`.
Binding canonical work identity to rows that a retention sweeper deletes would
silently orphan WorkItems. It would also couple the pilot to `AGENT_ENABLED`,
so the investigator path could not ship independently of the communication
agent.

**B. Publish-only: enqueue an outbox envelope and let a platform consumer create
the WorkItem asynchronously.** Attractive because it reuses
`internal/events` end to end and adds no outbound HTTP client at all. Dropped:
the user must be shown a stable reference in the reply, and "handle already-open
work items idempotently" requires reading current state back. Both need a
synchronous round trip. The outbox is kept, but as the *notification* channel
for the second surface, not the creation channel.

**C. Mirror WorkItem state locally and reconcile.** A local projection of
title/status/history would make replies fast and survive an mctl-api outage.
Dropped: it is precisely the "Making Telegram the WorkItem database" non-goal,
it creates a second source of truth that will drift, and it drags message-derived
content back into local storage. Degrading to "work tracking temporarily
unavailable" is the honest behaviour for an outage.

**D. Route the pilot through the Bot API surface (`internal/bot`) instead of
Saved Messages.** Dropped for this slice: `bot.Delivery` intentionally carries
no text, so a command argument cannot reach a handler without widening that
struct — a change the package doc explicitly says "must argue for itself". The
Saved Messages `/mctl` router already has an authenticated owner identity and a
reply channel. The Bot API path remains available as a follow-up once the
contract is proven.

## Platform impact

**Migrations.** One new table via `migrateWorkContext`, using the existing
idempotent `CREATE TABLE IF NOT EXISTS` dual-dialect pattern. No `ALTER` on any
existing table, so there is no `addColumnIfMissing` ordering hazard of the kind
documented for `job_leads.job_id`. An old binary running against the new schema
is unaffected — it simply never reads the table — which means the migration is
safe under the Recreate deployment strategy and under a rollback.

**Backward compatibility.** Every change is behind `WORK_CONTEXT_ENABLED`,
default false, matching `AGENT_ENABLED` and `BOT_RECEIVER_ENABLED`. With the
flag off: no new MCP tool is registered, `/mctl work` falls through to the
existing unknown-command help, `workitem.Disabled` makes an accidental call a
typed error rather than a network request, and no row is ever written. The seven
v1.0 MCP tools, the `agent_jobs` pipeline, `/api/agent/v1`, and the existing
approval flow are untouched in both states.

**New outbound dependency and egress.** This is the first outbound call from
`mctl-telegram` to `mctl-api`. It needs an egress allowance in the deployment
(the platform denies outbound internet egress by default for tenant workspaces),
a bounded `http.Client` timeout well under the router's 60s middleware timeout,
and bounded retries. Risk: an mctl-api outage degrading Telegram. Mitigation:
every failure path returns a user-visible "work tracking temporarily
unavailable" and leaves all other `/mctl` subcommands and the MCP tools working;
nothing in the existing request path awaits this client.

**Secrets.** `WORK_CONTEXT_API_TOKEN` is a new Vault-sourced secret. It must be
added to the redaction field list in `internal/audit/redact.go` alongside the
existing session/JWT names, and must never appear in a log line or an error
string. The `httpclient` adapter should scrub the `Authorization` header from
any error it wraps.

**Privacy.** The one content-bearing field crossing the service boundary is
`Title`, taken solely from the text the owner typed after `/mctl work`. It is
not persisted locally. Risk: an owner pastes something sensitive into a title.
Mitigation: cap the title length, document the behaviour in `SECURITY.md`'s data
flow table, and never echo the title back into an audit log.

**Resource impact.** Negligible. One small table, one row per Telegram work
thread, one outbound request per work command. No new poller, no new goroutine
beyond what the existing outbox relay already runs.

**Risks not fully mitigated.** The canonical contract (mctl-api#227) is not
readable from this repo, so the `httpclient` adapter is written against an
assumed shape and validated only by a contract fake. If the real shape differs,
the blast radius is one file plus the `Ref` mapping — the store, the router, the
MCP tool and the tests are written against the `workitem.Client` interface and
do not move.
