# Design: issue-443-feat-work-context-bind-telegram-threads

## Current state

`mctl-telegram` has no concept of canonical, cross-surface work state today.
What exists, read directly from the clone:

- **Command surface.** The owner's only control channel is their own
  Telegram Saved Messages dialog. `internal/agent/listener/listener.go`
  polls/pushes updates through `gotd/td`, `internal/agent/listener/extract.go`
  classifies a message as a command via `classifySavedCommand` (owner-authored,
  not forwarded, `PeerID == selfTGID`, and matching `isMCTLCommand`), and
  dispatches the raw text to `CommandRouter.HandleSavedText`. The concrete
  router, `internal/agent/control.Router` (`router.go` + `command.go`),
  parses a closed set of subcommands (`status`, `leads`, `show`, `continue`,
  `pause`, `takeover`, `approve`, `reject`) and replies through
  `internal/agent/control.Notifier`.
- **Thread-like state.** The nearest existing "thread" abstraction is
  `db.Conversation` (`internal/db/agent_domain.go`), keyed by
  `(user_id, peer_tgid)`, used exclusively by the communication agent to
  track auto-reply state (`ConversationActive/Paused/TakenOver/Closed`,
  `MaxAutonomousTurns`, etc.). It has no notion of an external work
  reference, and its schema is purpose-built for auto-reply policy, not for
  correlating to another system's task id.
- **Sub-chat threading.** The only sub-thread concept this codebase reads
  from MTProto is Telegram's Saved Messages "saved peer" bucket
  (`msg.GetSavedPeerID()` in `extract.go`), used only to reject commands
  that leaked in from a saved-peer other than the primary self chat. There
  is no forum-topic (`thread_id`) handling anywhere in `internal/telegram`.
- **Identity.** `internal/auth.Identity` (`internal/auth/identity.go`) is the
  canonical caller identity used by the MCP middleware, with `Subject`
  formatted as `tg:<telegram_id>` for Telegram-issued tokens
  (`Subject`/`TelegramID` fields). This is the actor identity this proposal
  reuses — it already existed before this feature and is not being
  invented for it.
- **Outbound HTTP client pattern.** `internal/agentworker/client.go`
  (`agentworker.Client`) is the one example in this repo of a small,
  bearer-token-authenticated HTTP client wrapping a JSON API
  (`/api/agent/v1/...`), with a typed `APIError` for non-2xx responses. It
  is a client of `mctl-telegram`'s own agent API, not of an external
  service, but its shape (constructor takes `baseURL, token, *http.Client`;
  trims trailing slash; typed errors) is the right template to follow for a
  new client of `mctl-api`'s WorkItem contract.
- **Migrations.** `internal/db/agent_schema.go`'s `migrateAgent` runs two
  parallel lists of `CREATE TABLE IF NOT EXISTS` statements (SQLite and
  Postgres dialects), applied additively — the file's own comment
  (`db.go:92`) is explicit that existing `CREATE TABLE` statements must not
  be modified in place, only extended with new tables/columns, to avoid
  breaking already-deployed schemas.
- **Config.** `internal/config/config.go` has no `mctl-api` base URL, token,
  or any outbound-service configuration today — every existing env var is
  either Telegram/OIDC/DB/self-serving. This integration requires new config
  surface.

## Proposed solution

Add a new internal package, `internal/workcontext`, that owns exactly the
correlation the issue asks for and nothing more, plus a thin platform client
behind an interface so the concrete `mctl-api`/`mctl-agents` HTTP contract
can be filled in once `mctl-api#227` and `mctl-agents#267` land without
touching command routing, storage, or tests that don't care about HTTP
specifics.

1. **`workcontext.PlatformClient` interface** (in
   `internal/workcontext/client.go`), the seam between this repo and the
   external contract:

   ```go
   type OpenWorkItemRequest struct {
       IdempotencyKey string // deterministic per (user, thread, topic)
       Actor          string // "tg:<telegram_id>"
       Surface        string // "telegram"
       Topic          string // raw command argument, platform interprets it
   }
   type WorkItemRef struct {
       WorkItemID   string
       ExecutionID  string
       SnapshotVer  string
       Status       string // platform-reported, opaque to us
       ResumeURL    string // stable cross-surface reference to show the owner
   }
   type PlatformClient interface {
       OpenWorkItem(ctx context.Context, req OpenWorkItemRequest) (WorkItemRef, error)
       GetWorkItem(ctx context.Context, workItemID string) (WorkItemRef, error)
   }
   ```

   `OpenWorkItem` is the single idempotent entry point for both "create" and
   "reopen" — the platform, not the bot, decides whether an existing
   non-terminal WorkItem matches the idempotency key (this keeps duplicate
   suppression logic in one place, the canonical service, rather than
   racing a local check against a remote create). A concrete
   `httpPlatformClient` implementation follows the `agentworker.Client`
   shape (bearer token, `baseURL` trimmed, typed `APIError`) and is wired in
   `cmd/server/main.go` only when `MCTL_API_BASE_URL` and
   `MCTL_API_WORKER_TOKEN` (new config fields, empty by default) are set.

2. **New table `work_context_bindings`**, added to both dialect blocks in
   `internal/db/agent_schema.go` alongside the existing `agent_*` tables,
   following the same additive `CREATE TABLE IF NOT EXISTS` pattern:

   ```sql
   CREATE TABLE IF NOT EXISTS work_context_bindings (
       id               INTEGER PRIMARY KEY AUTOINCREMENT, -- BIGSERIAL on pg
       user_id          BIGINT NOT NULL,
       chat_tgid        BIGINT NOT NULL,
       saved_peer_tgid  BIGINT NOT NULL, -- 0 when the command was in the primary self-chat itself
       idempotency_key  TEXT NOT NULL,
       work_item_id     TEXT NOT NULL,
       execution_id     TEXT NOT NULL,
       snapshot_version TEXT NOT NULL DEFAULT '',
       status           TEXT NOT NULL DEFAULT '',
       trigger_message_id BIGINT NOT NULL,
       created_at       TIMESTAMP NOT NULL,
       updated_at       TIMESTAMP NOT NULL,
       UNIQUE (user_id, chat_tgid, saved_peer_tgid),
       UNIQUE (user_id, idempotency_key)
   );
   ```

   Only correlation metadata is stored: Telegram identifiers, the
   platform-assigned `work_item_id`/`execution_id`/`snapshot_version`
   strings, and the last known status string for display. No message body,
   no transcript. This directly satisfies "persist only surface correlation
   metadata" and "do not replay the complete Telegram transcript as
   canonical task state." A `db.Store` method set
   (`internal/db/work_context.go`, mirroring the existing
   `EnsureConversation`/`GetConversation` pair in `agent_domain.go`) provides
   `UpsertWorkContextBinding`, `GetWorkContextBinding`.

3. **New `/mctl` subcommands**, additive to
   `internal/agent/control/command.go` and `router.go`:
   - `/mctl investigate <topic or issue URL>` — resolves (or creates) the
     binding for the current thread (chat + saved-peer), calls
     `PlatformClient.OpenWorkItem` with `Actor = "tg:" +
     strconv.FormatInt(identity's TelegramID, 10)` (the Router gains access
     to the calling identity the same way `HandleSavedText` already receives
     `userID` today — this proposal threads the resolved `*auth.Identity`
     through the listener call instead of just `userID`, since `Subject` is
     already computed once at auth time and should not be re-derived), and
     `Surface = "telegram"`.
   - `/mctl work [id]` — with no argument, shows the binding for the current
     thread (if any); with an id, calls `GetWorkItem` directly. Renders
     whatever `Status`/`SnapshotVer` the platform returns verbatim (plus the
     `ResumeURL`) — this is the "surface pending approval/result state
     without duplicating approval logic" requirement: the router does not
     interpret `Status`, it just displays it, same as `handleStatus` today
     displays `AgentProfile.Mode` without re-deriving policy.
   - Both are absent from the existing `ParseCommand` unknown-command
     help text update; `router.go`'s error-path help string is extended, not
     replaced, so existing subcommands are unaffected.

4. **Idempotency across delivery duplicates.** `IdempotencyKey` is computed
   deterministically as `sha256(user_id, chat_tgid, saved_peer_tgid,
   normalized topic)` truncated to a stable length — same shape the code
   already uses for `db.IncomingEvent.EventID` in
   `internal/agent/listener/extract.go` (`eventIDForMessage`, itself a hash
   of stable fields). Because `HandleSavedText` is invoked from
   `agent_saved_command_cursors`-tracked, at-least-once delivery (see
   `listener.go`'s durable cursor polling), the same triggering message can
   be redelivered; `UpsertWorkContextBinding` is a single `INSERT ... ON
   CONFLICT (user_id, idempotency_key) DO UPDATE` (Postgres) /
   `INSERT OR REPLACE`-with-guard (SQLite, matching this repo's existing
   dual-dialect upsert helpers in `agent_domain.go`), and `OpenWorkItem` is
   itself called with the same idempotency key on redelivery, so the
   platform call is also safe to repeat.

5. **Feature gate.** With `MCTL_API_BASE_URL` unset, `workcontext.New`
   returns a client whose methods return a sentinel
   `ErrPlatformNotConfigured`; `router.go`'s new handlers translate that into
   an owner-facing "Work-context integration is not configured on this
   deployment yet." reply rather than propagating an error up through
   `HandleSavedText` (which today logs and, per `listener.go`'s existing
   error handling, does not crash the listener loop — this proposal keeps
   that contract). This is what makes the feature safely mergeable and
   deployable before `mctl-api#227`/`mctl-agents#267` ship: the code path
   exists and is tested, but is inert by default.

6. **Auth boundary.** No new authorization decision is made locally.
   `OpenWorkItem`/`GetWorkItem` calls carry the Telegram-derived `Actor`
   subject and rely entirely on the platform's own authorization of that
   subject; a 401/403 from the platform is surfaced to the owner as-is
   (`"Not authorized to open work on the platform for this account."`)
   rather than mapped into any local allow/deny state. This keeps the
   existing principle in `internal/auth` intact: Telegram-side reachability
   (passing `classifySavedCommand`'s owner-authored gate) is necessary but
   never sufficient for a platform-side action.

## Alternatives

1. **Store the full command/response transcript per WorkItem for local
   display, instead of calling `GetWorkItem` on demand.** Rejected: this is
   exactly the "replay the complete Telegram transcript as canonical task
   state" anti-pattern the issue explicitly rules out, and it would create a
   second, driftable copy of state the platform already owns. `/mctl work`
   always re-fetches live status instead.
2. **Model the binding as a new column on the existing `conversations`
   table** rather than a new `work_context_bindings` table. Rejected:
   `conversations` is keyed by `(user_id, peer_tgid)` and its whole row
   shape (autonomous turn counters, agent mode) is communication-agent
   policy state; overloading it would couple two unrelated lifecycles
   (auto-reply policy vs. work-item correlation) and make the additive-only
   migration discipline (`db.go:92`) harder to honor cleanly. A dedicated
   table keeps the blast radius of this feature to itself and lets it be
   dropped/rolled back independently.
3. **Have the bot compute/track WorkItem "status" and "approval" state
   itself (e.g. mirror the existing `agent_actions` pending_approval/code
   machinery) instead of treating platform status as an opaque string.**
   Rejected: the issue explicitly calls out "without duplicating approval
   logic in the bot" as a requirement, and the communication agent's
   approval-code system (`internal/agent/executor`) is deliberately
   Telegram-send-specific (crash-safe `random_id` handling) — it is not a
   generic approval engine to extend to a different service's workflow.
4. **Bind at the raw `chat_tgid` only, ignoring Saved Messages saved-peer
   sub-threads.** Considered simpler, and viable if `mctl-api#227` turns out
   to want coarser granularity, but `(user_id, chat_tgid, saved_peer_tgid)`
   costs nothing extra to store now and gives natural fan-out later (a
   separate saved-peer bucket per topic of investigation, matching how the
   owner already organizes their own Saved Messages) — recorded instead as
   an open question, not fully dropped, since the correct granularity is
   ultimately the platform contract's call.

## Platform impact

- **Migrations.** One additive table (`work_context_bindings`) in both
  SQLite and Postgres dialect blocks of `migrateAgent`. No changes to any
  existing table or statement — follows the file's own stated backward-
  compatibility discipline. Purely additive, safe to deploy with zero
  downtime; no backfill needed since there is no prior data to migrate.
- **Backward compatibility.** All existing `/mctl` subcommands, the
  communication agent's conversations/approval flow, and every existing MCP
  tool are untouched. The new commands are pure additions to
  `ParseCommand`'s switch and `Router.HandleSavedText`'s switch. With the
  feature gate off (default, no `MCTL_API_BASE_URL`), the only observable
  change is that `/mctl investigate`/`/mctl work` now return a clear "not
  configured" message instead of "Unknown command" — an improvement, not a
  regression, and does not affect the general unknown-command help text
  format.
- **Resource impact.** One new small table with two unique indexes; a new
  outbound HTTP client used only when explicitly configured, gated by the
  router's existing at-least-once, low-frequency Saved Messages command
  path (no polling loop added). Negligible.
- **Risks + mitigations.**
  - *Risk:* the eventual `mctl-api#227`/`mctl-agents#267` contract shape
    differs from the `PlatformClient` interface assumed here (field names,
    idempotency semantics, sync vs. async execution start).
    *Mitigation:* the interface is intentionally narrow (two methods) and
    entirely isolated in `internal/workcontext`; only the concrete
    `httpPlatformClient` needs to change, not the DB schema, the router, or
    the command parser, when the real contract lands.
  - *Risk:* a stuck/slow platform call from inside `HandleSavedText` could
    block the listener's saved-command processing loop.
    *Mitigation:* the HTTP client is built with an explicit request
    timeout (matching `agentworker.Client`'s pattern of an injected
    `*http.Client`), bounded well under the listener's own processing
    cadence; a timeout is surfaced to the owner as a normal error reply,
    not a hang.
  - *Risk:* leaking Telegram message content into the platform call.
    *Mitigation:* only the raw command argument text (the "topic", already
    owner-authored and already treated as command input rather than private
    content by `classifySavedCommand`) is ever sent; no historical messages,
    no other participants' content, matching `internal/audit/redact.go`'s
    existing prohibition on logging message bodies (this proposal does not
    log the topic string either, only structured field names).
  - *Risk:* idempotency-key collisions across unrelated topics in the same
    thread silently reusing a stale WorkItem.
    *Mitigation:* the key is scoped to `(user_id, chat_tgid,
    saved_peer_tgid, normalized topic)`, and `GetWorkItem`'s returned status
    is always shown back to the owner on open/reopen, so a wrong reuse is
    immediately visible rather than silent.
