# Design: issue-443-feat-work-context-bind-telegram-threads

## Current state

### There is no outbound mctl-api client

Every occurrence of `mctl-api` / `api.mctl.ai` in this tree is *inbound* JWT
verification: `internal/auth/sharedhmac/verifier.go:1` ("validates JWTs issued
by mctl-api ... we intentionally do NOT import mctl-api as a Go module"),
`verifier.go:64` and `cmd/server/main.go:754,:994,:1059`
(`ExpectedIssuer: "https://api.mctl.ai"`). `MCTL_API_TOKEN` and
`MCTL_SURFACE_*` do not exist in `internal/config/config.go` or `.env.example`.
Nothing in the repo implements `work-item`, `workitem`, `surface-actor` or
`SurfaceIdentity`; the only match is the pinned contract at
`docs/contracts/mctl-api-work-context.md`. The only existing platform egress is
Valkey Streams (`internal/events/relay.go`), not HTTP.

The closest typed HTTP client, and the shape to copy, is
`internal/agentworker/client.go`: `Client{baseURL, token string; http *http.Client}`
(:41), `NewClient(baseURL, token string, hc *http.Client)` (:55),
`do(ctx, method, path string, body any, out any) error` (:62) which sets
`Authorization: Bearer `+token (:75), and `APIError{StatusCode, Message}` (:28)
decoded from `{"error": ...}` (:88-98). It calls mctl-telegram's *own*
`/api/agent/v1`, not the platform. There is no `Idempotency-Key` header
anywhere in the repo; idempotency today is a server-side DB key
(`internal/agentapi/actions.go:251`).

### The Telegram command surface is MTProto Saved Messages, not the Bot API

`internal/bot` is transport only: `Registry` is keyed by update *kind*
(`registry.go:58`), `Delivery{UpdateID, Kind, ChatID}` (`registry.go:17`) is all
a handler receives, `Message` carries only `Chat` (`update.go:40`), and
`cmd/server/main.go:925` registers **zero** handlers. `internal/botapi`'s
`SendMessage(ctx, chatID int64, text string)` (`botapi.go:41`) sends only
`chat_id` and `text`.

The real command surface is `internal/agent/control`:

- `ParseCommand(text string) (Command, error)` — `command.go:53`, a pure
  function returning `Command{Type CommandType, Arg string}` (`command.go:28`)
  over the nine subcommands at `command.go:15-25`.
- `Router.HandleSavedText(ctx context.Context, userID int64, text string) error`
  — `router.go:44`, the `listener.CommandRouter` implementation, wired at
  `cmd/server/main.go:246` as `control.NewRouter(store, agentExecutor, agentNotifier)`.
- Replies go out through `Notifier.Reply(ctx, userID int64, text string) error`
  — `notifier.go:121`, over `SelfSender` (`notifier.go:45`) into Saved Messages.

The listener already has the per-message facts the binding needs, but drops
them before the router: `listener.ExtractMessage` (`extract.go:63`) builds
`db.IncomingEvent{ChatTGID, SenderTGID, MessageID, ...}`
(`internal/db/agent_events.go:33-44`), while `Extracted.SavedCommandText`
(`extract.go:22`) is handed to the router as bare `text`.

**There is no forum-topic concept in this repository.** `git grep` for
`message_thread_id|MessageThreadID|ThreadID|thread_id` returns nothing. The
Telegram surface is an MTProto *user account* (`internal/telegram/clientpool.go`),
so "thread" must be defined in terms this codebase actually has. The nearest
durable per-peer row is `db.Conversation` (`internal/db/agent_domain.go:479`),
unique on `(user_id, peer_tg_id)`.

### Schema, config, redaction

- Migrations are hand-rolled and idempotent: `Migrate` (`internal/db/db.go:73`)
  probes the dialect, execs `sqliteSchema()` (`db.go:542`) or `pgSchema()`
  (`db.go:773`), runs an `addColumnIfMissing` pass (`db.go:513`), then
  `migrateAgent` (`db.go:363`) over `agentSchemaSQLite()`
  (`agent_schema.go:278`) / `agentSchemaPG()` (`agent_schema.go:527`). Queries
  use `$N` placeholders on both dialects; runtime divergence goes through
  `(*Store).isPostgres` (`agent_jobs.go:97`). `agent_migrations`
  (`agent_schema.go:420`) is a one-shot marker, not a version ledger.
- Column conventions: `*_tg_id` / `tg_message_id`, `INTEGER` (SQLite) ↔ `BIGINT`
  (PG), `DATETIME` ↔ `TIMESTAMPTZ`, ownership via
  `user_id ... REFERENCES users(id) ON DELETE CASCADE`, per-user uniqueness as
  `CREATE UNIQUE INDEX idx_<table>_<purpose> ON t(user_id, ...)` (pattern:
  `idx_conversations_user_peer`, `agent_schema.go:359`). JSON is stored as
  `TEXT`, never `JSONB`.
- Feature flags: `envBool("NAME", false)` (`config.go:473`), assigned in the
  `Load()` literal (`config.go:297-320`: `AGENT_ENABLED`, `MCP_APPS_ENABLED`,
  `BOT_RECEIVER_ENABLED`), with dependent-field validation inline in `Load`
  (`config.go:345-349`), and gated at mount time in `cmd/server/main.go:566`.
- Secrets are kept out of logs by the `sensitiveKeys` set in
  `internal/audit/redact.go:30`.
- Identity: `Store.UserIDByTelegramID(ctx, tgID)` exists (`store.go:244`); the
  reverse lookup does not.

## Platform prerequisites (owner decision 2026-09-23)

A surface **requests** execution; it never **declares** execution identity. The
bot never sends `execution_id`, `engine` or `engine_ref`, and it never starts,
wakes or attaches an execution. Two platform pieces supply that, and #443
depends on both in the canonical roadmap:

- **mctl-api#368 — surface-originated execution requests.** The bot submits
  `POST /api/v1/work-items/{id}/execution-requests` (`kind: start|resume`,
  `expected_state_version`, optional `resumed_from_execution_id` / `intent_id`,
  idempotency) through the relay. Only the platform fulfils a request by
  attaching the canonical execution. `POST /work-items/{id}/resume` leaves the
  surface allowlist with that change, so the bot does not call it.
- **mctl-agents#461 — WorkItem execution dispatch.** The dispatcher claims the
  request, starts the investigator bound to the exact WorkItem and request, and
  creates the canonical execution. The bot only reads the result back through
  `GET /api/v1/work-items/{id}` (`latest_execution`, snapshot pointers).

The Telegram-side slice below can be built behind its flag before both land, but
its client targets the #368 request route (update
`docs/contracts/mctl-api-work-context.md` when #368 merges), and live end-to-end
acceptance waits for #368, #461 and their deployment.

## Proposed solution

Add a thin, flag-gated **surface adapter**: a new outbound client package, a
new binding table that can only hold identifiers, and four new `/mctl`
subcommands. No existing behaviour changes.

### 1. `internal/workctx` — the mctl-api work-context client

Modelled directly on `internal/agentworker/client.go`.

`client.go`:

```go
type Client struct {
    baseURL string        // MCTL_API_BASE_URL, default https://api.mctl.ai
    token   string        // MCTL_SURFACE_TELEGRAM_TOKEN
    tenant  string        // MCTL_WORK_ITEM_TENANT
    http    *http.Client
}

// relay performs one request as surface:telegram on behalf of actorTGID.
func (c *Client) relay(ctx context.Context, method, path string,
    actorTGID int64, idemKey string, body, out any) error
```

`relay` sets exactly three headers: `Authorization: Bearer <token>`,
`X-MCTL-Surface-Actor: strconv.FormatInt(actorTGID, 10)`, and
`Idempotency-Key: <idemKey>` when non-empty. Public methods map one-to-one onto
the six permitted routes and nothing else:

```go
func (c *Client) RedeemLink(ctx, actorTGID int64, code string) error
func (c *Client) CreateWorkItem(ctx, actorTGID int64, r CreateRequest) (*ItemView, error)
func (c *Client) GetWorkItem(ctx, actorTGID int64, id string) (*ItemView, error)
func (c *Client) AppendIntent(ctx, actorTGID int64, id string, r IntentRequest) error
func (c *Client) RequestExecution(ctx, actorTGID int64, id string, r ExecutionRequest) (*ExecutionRequestView, error)
func (c *Client) AddSurfaceRef(ctx, actorTGID int64, id string, r SurfaceRefRequest) error
```

`ExecutionRequest` carries `Kind` (`start`|`resume`), `ExpectedStateVersion`
and optional `ResumedFromExecutionID` / `IntentID` only — **no** `engine`,
`engine_ref` or `execution_id` field exists. The request structs deliberately
have **no** actor-shaped field either, so
`400 actor_not_accepted` is unreachable by construction rather than by
convention. `CreateRequest` has no `origin_surface` setter either — `relay`
hardcodes `"telegram"`.

`envelope.go` holds the `workitem/v1` types (`ItemView{SchemaVersion,
WorkItem{ID, Tenant, Title, State}, StateVersion, LatestExecution,
PendingApproval, LatestSnapshot}`, plus `ExecutionRequestView{ID, Kind, State,
ExecutionID}` for the mctl-api#368 request, whose `ExecutionID` is only ever
read back, never sent); decoding rejects any `schema_version`
other than `workitem/v1`.

`errors.go` maps mctl-api error codes onto sentinels the router renders as
owner-facing text — `ErrLinkNotFound`, `ErrLinkRevoked`, `ErrLinkExpired`,
`ErrRelayRequired`, `ErrChallengeInvalid`, `ErrLinkConflict`,
`ErrActorNotAccepted`, `ErrStateVersionConflict` — following the
`approverErrText` precedent at `router.go:359`.

### 2. `work_item_bindings` — identifiers only, by construction

New statements appended to `agentSchemaSQLite()` / `agentSchemaPG()`, using the
`bot_updates` template (`db.go:703` / `:948`), with a new store file
`internal/db/work_item_bindings.go` following the `agent_saved_commands.go`
shape:

```sql
CREATE TABLE IF NOT EXISTS work_item_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,   -- BIGSERIAL on PG
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chat_tg_id INTEGER NOT NULL,
    root_tg_message_id INTEGER NOT NULL,
    work_item_id TEXT NOT NULL,
    external_key TEXT NOT NULL,
    last_state TEXT NOT NULL DEFAULT '',
    last_state_version INTEGER NOT NULL DEFAULT 0,
    last_execution_id TEXT NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_work_item_bindings_thread
    ON work_item_bindings(user_id, chat_tg_id, root_tg_message_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_work_item_bindings_item
    ON work_item_bindings(user_id, work_item_id);
```

There is no body, text, title or handle column. The "do not persist the
transcript" requirement is enforced by the schema, not by reviewer vigilance —
the same argument `bot_updates` already makes in its own comment
(`db.go:690-702`). Nothing here needs `crypto.SealForUser`, because nothing
here is user content.

Store methods: `GetWorkItemBinding(ctx, userID, chatTGID, rootMsgID)`,
`LatestWorkItemBinding(ctx, userID, chatTGID)`, `UpsertWorkItemBinding(ctx, b)`,
`TouchWorkItemBindingState(ctx, userID, workItemID, state string, version int64, execID string)`.

**External key** is deterministic so mctl-api dedupes open work even if our row
is lost: `tg:v1:<chat_tg_id>:<root_tg_message_id>`. The `Idempotency-Key` is
`<external_key>:<op>` (and `:<state_version>` for resume), so a retry after a
timeout or crash is a no-op at the platform rather than a duplicate work item.

### 3. Widening the Saved Messages router context

`Router.HandleSavedText(ctx, userID, text)` cannot serve #443: it has neither
the Telegram user id needed for `X-MCTL-Surface-Actor` nor the message id
needed for the binding key. Change `listener.CommandRouter` to pass the facts
the listener already has:

```go
type SavedMeta struct {
    UserID     int64 // users.id, the owning account
    SelfTGID   int64 // Telegram user id of that account (Saved Messages self peer)
    ChatTGID   int64
    TGMessageID int64
}
func (r *Router) HandleSavedText(ctx context.Context, meta SavedMeta, text string) error
```

`listener` already computes `selfTGID` (`extract.go:63` takes it as a
parameter) and `MessageID`, so this is plumbing, not new extraction. `Router`
is the only production implementation (`cmd/server/main.go:246`); the churn is
confined to the fakes in `listener_test.go` and `router_test.go`.

`SelfTGID` is the actor for the relay header, cross-checked against a new
`Store.TelegramIDByUserID(ctx, userID)` (the reverse of `store.go:244`). If the
two disagree, or the store has no Telegram id, the adapter fails closed and
makes no call. The deployment allowlists (`TGLoginAdmins`, `TGLoginClients`,
`AutoApproveClients`) are **not** consulted for attribution — contract rule 5.

### 4. `/mctl` subcommands

`command.go` gains `CmdWork` and `CmdLink`, plus a `Sub string` field on
`Command` populated only for `work` (the existing nine subcommands keep an
empty `Sub`, so their parse results stay byte-identical):

- `/mctl link <code>` → `RedeemLink`. The code is never echoed and never logged.
- `/mctl work <title>` → reuse the thread's binding if its `last_state` is
  `active`/`waiting`, otherwise `CreateWorkItem` + `AddSurfaceRef` + upsert the
  binding.
- `/mctl work status` → `GetWorkItem`, render id, state, `latest_execution`,
  pending approval and snapshot pointer, and refresh the cached state.
- `/mctl work note <text>` → `AppendIntent`.
- `/mctl work resume` → `GetWorkItem` for a fresh `state_version`, then
  `RequestExecution{Kind: resume}` with `expected_state_version`; on 409,
  re-read and retry once. The reply says the request was accepted; execution
  state is read later via `/mctl work status`.

A new `internal/agent/control/work.go` holds these handlers, keeping
`router.go` a dispatcher. The router gains one nilable field, `Work *WorkHandler`.

### 5. Flag gating

`internal/config/config.go`: `WorkContextEnabled` ← `envBool("WORK_CONTEXT_ENABLED", false)`,
plus `MCTLAPIBaseURL` (`MCTL_API_BASE_URL`, default `https://api.mctl.ai`),
`MCTLSurfaceTelegramToken` (`os.Getenv`, no default, matching the
`TG_API_HASH` secret pattern at `config.go:288`) and `WorkItemTenant`
(`MCTL_WORK_ITEM_TENANT`). Inline validation in `Load` mirrors the
`DEMO_REVIEWER_ENABLED` companion check (`config.go:345-349`): enabled with an
empty token or tenant is a `Load` error.

`cmd/server/main.go` constructs the client and sets `agentRouter.Work` only
when the flag is on, next to the `cfg.AgentEnabled` block. When off, `Work` is
nil and `command.go` returns `ErrUnknownCommand` for `work`/`link`, so
`/mctl work` produces exactly today's unknown-command reply — literally no
behaviour change.

`mctl_surface_telegram_token` is added to `sensitiveKeys`
(`internal/audit/redact.go:30`). New metrics on the `metrics.Registry`:
`WorkContextRequestsTotal{route,outcome}` and `WorkContextBindingsTotal{result}`.

### Cross-surface pilot path

`/mctl work "<title>"` creates the item (`origin_surface: telegram`),
registers the Telegram thread as a surface ref and submits a `start` execution
request → the platform dispatcher (mctl-agents#461) claims it, starts the
investigator and attaches execution A through the platform-only fulfil route
of mctl-api#368 and seals ContextSnapshot v1 → `/mctl work status`
shows `latest_execution` and the snapshot pointer → a human opens the same
`work_item_id` from the CLI/MCP or web surface and resumes → execution B,
ContextSnapshot v2 → `/mctl work status` in Telegram reflects the new execution.
No Telegram history is replayed at any step; the bot only ever moves ids.

## Alternatives

**Store `work_item_id` on the existing `conversations` row instead of a new
table.** Cheapest change — one `addColumnIfMissing` call. Dropped:
`conversations` is keyed `(user_id, peer_tg_id)` (`agent_schema.go:345`) and
models the recruiter-DM domain of the communication agent, whose C1 rollout is
still gated (`docs/plans/communication-agent.md`). One conversation legitimately
spawns many work items over time, so a single column cannot express the
mapping, and reusing the row would couple #443's rollout to a gate it has no
business waiting on. A separate table also lets the schema forbid text columns,
which the shared row cannot.

**Let the bot call `/work-items/{id}/executions` and `/snapshot` to correlate
the investigator run.** This is the most direct reading of the acceptance
criterion "correlated to WorkItem + execution identity + ContextSnapshot".
Dropped: those routes are explicitly on the forbidden list
(`docs/contracts/mctl-api-work-context.md:48-55`) and are service-principal
only. The same correlation is available read-only through the
`latest_execution` and snapshot pointers on `GET /work-items/{id}`, which is
what the design uses.

**Extend `internal/bot` (Bot API) with a command router and real forum-thread
support.** Attractive because `message_thread_id` is a genuine Bot API concept.
Dropped: `internal/bot` has no handlers, no message text, no from-user id and
no thread-aware sender, so this means widening `Update`/`Message`
(`update.go:40-56`), `Delivery` (`registry.go:17`), `db.PendingUpdate` and the
`bot_updates` DDL, plus changing `botapi.SendMessage` and therefore
`broadcast.Sender` (`internal/broadcast/worker.go:50`). That is a large,
separately-reviewable change to a surface that does not yet exist in
production, and it is #438/#571 territory. The MTProto Saved Messages surface
is live today and already carries the ids we need.

**Mirror the Telegram transcript into the work item as canonical state.**
Dropped: an explicit non-goal in the issue, and it would defeat the "resume
without replaying Telegram history" acceptance criterion.

## Platform impact

**Migrations.** One new table, two indexes, appended to
`agentSchemaSQLite()`/`agentSchemaPG()`. `CREATE TABLE IF NOT EXISTS` is a
no-op on existing deployments; there is no backfill, no `ALTER`, no lock on a
populated table, and no data to migrate. Rollout order is free — the table can
ship dark, ahead of the flag.

**Backward compatibility.** With `WORK_CONTEXT_ENABLED=false` (the default) the
client is never constructed, no socket is opened, and every existing `/mctl`
subcommand parses and behaves identically. The only compile-level break is
`listener.CommandRouter.HandleSavedText`'s signature, which is internal to this
module and has one production implementation.

**Resource impact.** Negligible: a handful of outbound HTTPS requests per owner
command, no background loop, no polling. The binding table grows by one small
row per Telegram-originated work item. Mutating calls spend the linked human's
20/min mctl-api write budget, which bounds us naturally.

**Risks and mitigations.**

- *Actor spoofing.* If the relay header could ever be influenced by message
  content, a Telegram user could act as someone else. Mitigated by deriving it
  only from `SavedMeta.SelfTGID` cross-checked against
  `Store.TelegramIDByUserID`, plus a unit test asserting the header is
  digits-only and a reflection test asserting no request struct carries an
  actor-shaped field.
- *Surface token leaking into logs.* Mitigated by adding
  `mctl_surface_telegram_token` to `internal/audit/redact.go` and never logging
  request headers.
- *Duplicate work items from retries.* Mitigated by the deterministic
  `external_key` plus `Idempotency-Key`; both are derived from the thread key,
  so they survive a lost binding row.
- *mctl-api not yet released with the surface principal.* Every non-2xx maps to
  a typed sentinel with owner-facing text, and the flag stays off until the
  release lands. The adapter never blocks or fails the Saved Messages listener.
- *Egress.* This is the repo's first outbound HTTPS to `api.mctl.ai`. The
  communication-agent plan records that the `labs` namespace is
  `allowInternetEgress: true` namespace-wide, so it should work, but the
  operator must confirm the NetworkPolicy for the deployed namespace before
  enabling the flag.
- *`state_version` churn.* A busy work item could 409 repeatedly on resume.
  Mitigated by one bounded re-read-and-retry, then an explicit message to the
  owner; the bot never loops.
