# Design: issue-297-saved-messages-control-plane-approval-ex

## Current state

The communication-agent storage layer already exists and this proposal
builds strictly on top of it — no schema changes are required:

- `internal/db/agent_schema.go` (`migrateAgent`) creates `agent_profiles`,
  `incoming_events`, `conversations`, `conversation_messages`,
  `agent_actions`, `job_leads`, `owner_notifications`, `tg_update_state`,
  `tg_channel_state` for both SQLite and Postgres.
- `internal/db/agent_domain.go` defines `AgentProfile` (mode: `observe` /
  `guarded` / `off`, `AutopilotPaused`, `ListenerEnabled`,
  `MaxAutonomousTurns`, etc.), `Conversation` with states `active` /
  `paused` / `taken_over` / `closed`, and CAS-safe mutators
  (`SetConversationState`, `IncrementAutonomousTurns`,
  `ResetAutonomousTurns`).
- `internal/db/agent_actions.go` defines `AgentAction`, the action-type
  constants (`propose_reply`, `send_owner_summary`,
  `request_owner_approval`), the full status set (`proposed` →
  `pending_approval` → `approved` → `executing` → `executed`, plus
  `rejected` / `expired` / `denied`), `allowedActionTransitions` (a map
  enforced inside `UpdateAgentActionStatus`), `SetAgentActionExecuted`
  (dedicated `executing` → `executed` CAS that also stamps
  `executed_tg_message_id`), and `ExpireStaleAgentActions` (TTL sweep off
  `updated_at`, keyed on `pending_approval`). `GetAgentActionByCode` already
  does the `(user_id, approval_code)` lookup the `/mctl approve` handler
  needs. `OwnerNotification` (`agent_actions.go`) and its
  `InsertOwnerNotification` / `MarkOwnerNotificationSent` /
  `MarkOwnerNotificationFailed` CAS pair are the persistence home for
  everything the notifier sends.
- `internal/db/agent_events.go` defines `IncomingEvent` with kind
  `EventKindSavedCommand` — i.e. the DB layer already anticipates that
  owner Saved-Messages text will be captured as a distinct event kind by
  the (not-yet-built) listener, separate from `EventKindPrivateMessage`.
- `internal/telegram/agentruntime.go` defines the `AgentRuntime` interface
  and `ClientPool.WithAgentRuntime` / `Pin` / `Unpin` — the hook a future
  `internal/agent/listener` package (out of scope here) will use to keep a
  pinned MTProto connection alive per agent-enabled user and feed it
  updates. This proposal's notifier and executor do not implement
  `AgentRuntime`; they only need a borrowed `*telegram.Client` per send,
  exactly like the existing MCP tools in `internal/mcp/tools.go`
  (`s.Pool.Borrow` / `s.borrowWithRetry`).
- `internal/telegram/sendself.go` provides `SendToSelf(ctx, c, text)` (wraps
  `SendToInputPeer` with `tg.InputPeerSelf{}`) and `SendToInputPeer(ctx, c,
  peer, text)` for sending to an already-resolved peer — exactly the two
  primitives the notifier (→ self) and the executor (→ conversation peer)
  need. Neither takes a peer *string*, by design, per the doc comment: "the
  communication agent's executor derives the peer from the conversation
  row (never from model output)".
- `internal/audit/redact.go` already redacts `text`, `body`,
  `proposed_text`, `payload`, and `code` (case-insensitive) from every slog
  attribute through `RedactingHandler`, and `ScrubText` masks `@handles`/
  phone-like digit runs in free-form error strings. This already covers
  approval codes and draft/message bodies as long as this proposal's code
  logs them under those attribute keys (or adds new ones to
  `sensitiveKeys` if a new field name is introduced).
- `internal/config/config.go` follows a flat `Config` struct + `envOr` /
  `envBool` / `envInt` / `envDuration` helper pattern; `AgentRetentionDays`
  (`AGENT_RETENTION_DAYS`) is the most recent example of an agent-specific
  setting added this way. No `AGENT_ENABLED` / `AGENT_KILL_SWITCH` /
  `AGENT_PROFILE_PATH` fields exist yet in this clone (consistent with the
  issue's "do not start until #296 is merged" note — #296 is expected to
  introduce the first of these; this proposal adds the remainder needed for
  its own packages if #296 has not already).
- `internal/sweeper/sweeper.go` is the established place for background
  loops: each sweep (`Sessions`, `AuditLog`, `RefreshTokens`,
  `AgentRetention`) is a `ticker`-driven function taking `(ctx, store,
  ...)`, run once immediately then on an interval, logging only row counts.
  `AgentRetention` (added alongside the agent schema) is the closest
  precedent for the new approval-TTL sweep.
- `internal/mcp/server.go`'s `Server` struct holds `Store *db.Store`, `Pool
  *telegram.ClientPool`, `Metrics`, etc., and `internal/mcp/tools.go` shows
  the `Pool.Borrow` / `borrowWithRetry` pattern (flood-wait aware) used for
  every outbound Telegram call — the executor reuses this pattern rather
  than inventing a new client-acquisition path.
- No `internal/agent/*` package exists yet in this clone. No
  `internal/agent/policy` package (and therefore no `DisclosureSep`)
  exists — see Open Questions in requirements.md.
- `go.mod` already carries `gopkg.in/yaml.v2`, `go.yaml.in/yaml/v2`, and
  `github.com/go-faster/yaml` as *indirect* dependencies (pulled in
  transitively). None is a direct dependency yet, so the profile loader
  needs to promote one to direct (`go.yaml.in/yaml/v2` recommended — this is
  the actively maintained fork; standard `yaml.Unmarshal` API).

## Proposed solution

Three new packages under `internal/agent/`, all gated by
`AGENT_ENABLED` at the point they are wired into `cmd/server/main.go` (each
package itself stays a pure library — the gate is "do we start/call this
code at all", not an internal flag threaded through every function):

### `internal/agent/control`

- `ParseCommand(text string) (Command, error)` — pure, table-driven. `text`
  is the raw Saved Messages body already stripped of the `saved_command`
  envelope by the listener (out of scope). Recognises:
  `status`, `leads`, `show <id>`, `continue <id>`, `pause`,
  `takeover <id>`, `approve <code>`, `reject <code>`. Returns a small
  `Command` struct: `{Kind CommandKind; ActionID int64; ApprovalCode
  string}` (fields populated per kind), or a typed `ParseError` for
  anything else (empty, missing prefix, unknown verb, non-numeric id,
  missing code) — deliberately no partial/loose matching, since a
  misparsed `/mctl` command acting on the wrong conversation is worse than
  an "unrecognised command" reply.
- `Notifier` — a small struct holding a `*db.Store` and (per-call) a
  `*telegram.Client`, with methods:
  - `NotifyOwnerSummary(ctx, userID int64, summary string) error` —
    inserts an `OwnerNotification{Kind: NotificationSummary}`, sends via
    `telegram.SendToSelf`, then `MarkOwnerNotificationSent` /
    `MarkOwnerNotificationFailed`. Insert-then-send-then-mark (not
    send-then-insert) so a crash between insert and send still leaves a
    `pending` row an operator can see, instead of losing the intent to
    notify entirely.
  - `RequestApproval(ctx, userID int64, action db.AgentAction) error` —
    formats the approval message (summary + draft reply body + `/mctl
    approve <code>` / `/mctl reject <code>` lines), same
    insert/send/mark sequence, `Kind: NotificationApproval`,
    `ActionID: action.ID`.
  - Both methods are the *only* place in this proposal that constructs the
    text that reaches `SendToSelf` — keeping the formatting logic (and the
    "never include a restricted profile field" invariant) in one place.
  - Message formatting lives in an unexported `formatApproval` /
    `formatSummary` pair of pure functions so they are table-driven-testable
    without a DB or Telegram client, mirroring `internal/mcp/format.go`'s
    separation of "build the string" from "send it".
- Command *execution* (what happens when e.g. `pause` or `approve <code>`
  is parsed) is a `Handler` type in the same package:
  `HandleCommand(ctx, store *db.Store, notifier *Notifier, userID int64,
  cmd Command) (reply string, err error)`. It is intentionally thin and
  delegates every state mutation to existing `Store` methods:
  - `status` → `store.GetAgentProfile` + a small conversation/action count
    query (added as `Store.CountAgentActionsByStatus` or reusing
    `ListJobLeads`-style listing — see tasks.md; kept minimal per
    "Out of scope").
  - `leads` → `store.ListJobLeads`.
  - `show <id>` → `store.GetConversation` + `store.ListConversationMessages`.
  - `continue <id>` → `store.SetConversationState(..., ConversationActive)`
    + `store.ResetAutonomousTurns`.
  - `pause` → `store.SetAgentAutopilotPaused(ctx, userID, true)`.
  - `takeover <id>` → `store.SetConversationState(...,
    ConversationTakenOver)`.
  - `approve <code>` / `reject <code>` → `store.GetAgentActionByCode` then
    `store.UpdateAgentActionStatus(ctx, userID, action.ID,
    db.ActionPendingApproval, db.ActionApproved|db.ActionRejected)`. The
    CAS's `false, nil` return (race lost / already resolved) maps to a
    "this code was already used or has expired" reply rather than an
    error — approving twice must be a no-op, not a crash.
  - Every handler returns a short owner-facing reply string; the caller
    (listener, out of scope) is responsible for sending it back to Saved
    Messages via the same `Notifier`/`SendToSelf` path. Keeping the "what do
    I say back" logic here (not in the listener) keeps it unit-testable
    alongside the parser.

### `internal/agent/executor`

- `Executor` struct: `Store *db.Store`, `Pool *telegram.ClientPool`,
  `Enabled func() bool` (kill-switch + `AGENT_ENABLED` check, injected so
  tests can flip it mid-flow without touching real env vars),
  `DisclosureSep string` (wired from `policy.DisclosureSep` once #296
  lands, or a local constant otherwise — see Open Questions).
- `Run(ctx, pollInterval)` — a `sweeper`-style ticker loop
  (`internal/sweeper/sweeper.go` pattern) that lists `approved` actions
  (new `Store.ListAgentActionsByStatus(ctx, db.ActionApproved, limit)`,
  small addition alongside `agent_actions.go`) and calls `ExecuteOne` for
  each. Loop is best-effort per row: one row's error is logged and does
  not stop the sweep.
- `ExecuteOne(ctx, action db.AgentAction) error` — the state machine core,
  fully unit-testable without a ticker:
  1. **Kill-switch re-check**: `if !e.Enabled() { return
     ErrKillSwitchActive }` (no status mutation — action stays `approved`
     so it can run once the switch flips back).
  2. **Profile re-check**: `profile, err :=
     store.GetAgentProfile(ctx, action.UserID)`; bail (no mutation) if
     `profile.Mode == db.AgentModeOff` or `profile.AutopilotPaused`.
  3. **Conversation re-check**: `conv, err :=
     store.GetConversation(ctx, action.UserID, action.ConversationID)`;
     bail (no mutation) unless `conv.State == db.ConversationActive`
     (a `paused`/`taken_over`/`closed` conversation must not receive a
     stale approved reply — this is the mid-flight-pause guarantee from the
     issue).
  4. **CAS to executing**: `ok, err :=
     store.UpdateAgentActionStatus(ctx, action.UserID, action.ID,
     db.ActionApproved, db.ActionExecuting)`; `!ok` means another
     executor/replica already claimed it — return nil, no-op (this is what
     makes the executor safe to run on more than one replica/poll tick
     concurrently).
  5. **Compose text**: draft payload (`action.Payload`, already decrypted
     by `GetAgentAction`) + `DisclosureSep` + `profile.DisclosureText`.
  6. **Send**: `pool.Borrow(ctx, action.UserID, func(c) error { msgID, err
     = telegram.SendToInputPeer(ctx, c, resolvePeer(conv), text); ...
     })` — the peer is built from `conv.PeerTGID` via `tg.InputPeerUser`
     (needs `AccessHash`; see Platform impact) — never from
     `action.Payload` or any executor input, matching the doc comment on
     `SendToInputPeer`.
  7. **On success**: `store.SetAgentActionExecuted(ctx, action.UserID,
     action.ID, msgID)` (dedicated `executing`→`executed` CAS) and
     `store.IncrementAutonomousTurns(ctx, action.UserID,
     action.ConversationID)`.
  8. **On send failure**: do **not** call any transition method. The row
     stays `executing` forever, by design — this is the issue's explicit
     "never auto-retry from executing" requirement. The function returns
     the send error; the sweep loop logs it at `slog.Error` with the action
     id (not the payload) so an operator can find and manually resolve it
     (e.g. via a future admin tool, out of scope). A metric counter
     (`agent_executor_stuck_executing_total` or similar, following
     `internal/metrics`'s existing registry pattern) is recommended so this
     is observable, not just logged.
  9. Every step logs at most `action_id`, `user_id`, `conversation_id`,
     `from_status`, `to_status` — never `payload`/`text`/`approval_code`
     (already redacted by `internal/audit/redact.go` as defense in depth,
     but the executor should not rely solely on the handler for this).
- A second, independent function `ExpireApprovals(ctx, store, ttl
  time.Duration)` simply calls `store.ExpireStaleAgentActions(ctx, ttl)` on
  a `24h` default (issue-specified), run from the same or a sibling ticker
  loop in `internal/sweeper` (new `sweeper.AgentApprovalExpiry`, matching
  the existing `AgentRetention` shape) so all background loops stay in one
  package and `main.go` keeps wiring them the same way. `internal/agent/
  executor` exports the pure "what to do" step; `internal/sweeper` keeps
  owning "when to do it".

### `internal/agent/profile`

- `Profile` struct mirrors the YAML sections: `Identity`,
  `PublicProfile`, `Skills []string`, `Preferences map[string]string`, and
  an unexported `restricted map[string]RestrictedField` where
  `RestrictedField{Value string; ApprovalRequired bool; NeverAutoSend
  bool}`.
- `OwnerProfileProvider` — loads and caches the YAML file at
  `AGENT_PROFILE_PATH` (mtime-checked reload on each `Get`, matching a
  "mounted file, may change via ConfigMap update" deployment model without
  needing a filesystem watcher).
- Public accessor surface intentionally has **no** method that returns the
  `restricted` map or any `RestrictedField`. `Get(ctx) (PublicProfile,
  error)` returns only identity/public_profile/skills/preferences plus
  `DisclosureText` (sourced from `db.AgentProfile.DisclosureText`, i.e. the
  DB row, not the YAML file — disclosure text is operator/owner-tunable at
  runtime today per `UpsertAgentProfile`, unlike the YAML file which needs a
  redeploy/remount). This is a structural guarantee, not a filter applied
  at call time: restricted fields never enter the returned struct, so no
  future caller can accidentally leak them by forgetting to strip a field.
- A second, deliberately narrow accessor,
  `RestrictedFieldPolicy(key string) (approvalRequired, neverAutoSend bool,
  ok bool)`, lets the (out-of-scope) policy engine ask "if the model wants
  to disclose X, what's the rule" without ever handing back the *value* —
  only the two booleans and whether the key exists. This satisfies "IF a
  restricted field is marked approval_required/never_auto_send THEN...
  never eligible for guarded-mode auto-send" without giving policy code a
  way to accidentally forward the value into a draft.
- YAML parse errors, missing file, or `AGENT_PROFILE_PATH` unset all
  produce a typed `ErrProfileUnavailable` rather than a panic; callers
  (executor, control) that need `DisclosureText` fall back to the DB row's
  `AgentProfile.DisclosureText` when the YAML profile can't be loaded, since
  disclosure is a compliance requirement that must not silently disappear
  because a ConfigMap mount hiccuped.

### Wiring (`cmd/server/main.go`)

Follows the existing `sweeper.AgentRetention(ctx, store, ...)` /
`go sweeper.X(...)` pattern already in `main.go`:

```go
if cfg.AgentEnabled {
    profileProvider := profile.NewOwnerProfileProvider(cfg.AgentProfilePath)
    notifier := &control.Notifier{Store: store, Pool: pool}
    exec := &executor.Executor{
        Store: store, Pool: pool,
        Enabled: func() bool { return cfg.AgentEnabled && !cfg.AgentKillSwitch },
        DisclosureSep: policy.DisclosureSep,
    }
    go exec.Run(ctx, executorPollInterval)
    go sweeper.AgentApprovalExpiry(ctx, store, 24*time.Hour)
    // notifier/profileProvider handed to whatever #296 wires as the
    // Saved-Messages command dispatcher (listener, out of scope here).
}
```

`AGENT_KILL_SWITCH` is re-read live (via `cfg` or a small atomic-bool
watcher, TBD by #296) on every `Enabled()` call, not captured once at
startup, so an operator can flip it without a restart — this is the whole
point of a kill switch.

## Alternatives

1. **Push the executor's state-machine re-checks into
   `Store.UpdateAgentActionStatus` itself** (a DB-layer "conditional CAS
   with business rules" instead of the app-layer sequence above). Rejected:
   `allowedActionTransitions` is deliberately dumb (state-shape only, no
   business logic) per its own doc comment ("A caller passing a (from, to)
   pair not listed here is a programming error"); teaching the DB layer
   about kill switches and profile modes would blur the layer boundary the
   existing code already establishes, and would make the "which check
   failed" reason harder to surface to logs/notifications than a plain Go
   `if` chain in `executor.ExecuteOne`.

2. **Have the notifier synthesize approval codes and put code-generation in
   `internal/db`** instead of `internal/agent/control`. Rejected: code
   generation is a presentation/UX concern (short, human-typeable,
   collision-avoidance against `idx_agent_actions_code`), not a storage
   concern; `InsertAgentAction`/`UpdateAgentActionStatus` already accept an
   `ApprovalCode` field, so the DB layer stays a dumb store and
   `control.Notifier` (or whatever transitions an action to
   `pending_approval`, likely shared with #296) owns generation + retry-on-
   collision by attempting the insert/update and checking the unique-index
   error.

3. **Single `internal/agent` package instead of three sub-packages.**
   Rejected: the issue explicitly names three packages with three distinct
   responsibilities and three distinct trust boundaries (parsing owner
   input, executing approved sends, reading a profile file) — the same
   split the existing codebase uses elsewhere (`internal/auth` has one
   `Provider` interface with `sharedhmac`/`localdev`/`localjwt`
   sub-packages rather than one flat package). Splitting also lets
   `internal/agent/profile` have zero dependency on `internal/db`, which
   matters for unit-testing it against a fixture YAML file without a test
   database.

4. **Executor consumes a queue/channel fed directly by the approve-command
   handler** instead of polling `approved`-status rows. Rejected for this
   proposal: the DB row *is* the durable queue (that's why `executing` is a
   documented trap state — it only makes sense if the source of truth is
   the row, not an in-memory channel that a crash would drop). A polling
   sweep is also what every other background job in this codebase already
   does (`internal/sweeper`), so it composes with existing
   ops/observability rather than introducing a new concurrency primitive.
   A future optimization could add a best-effort in-process wakeup channel
   to cut latency between "approved" and "executing" without changing the
   durability model, but that is not required by the issue.

## Platform impact

- **Migrations**: none. All required tables/columns/indexes already exist
  (`internal/db/agent_schema.go`, committed with #289). This proposal may
  add a small number of new *read* helper methods to `internal/db`
  (`ListAgentActionsByStatus`, a lightweight action/lead count query for
  `/mctl status`) but no new tables, columns, or migrations.
- **Backward compatibility**: fully additive. `AGENT_ENABLED` (or
  equivalent gate from #296) defaults to off/false, so existing deployments
  see no behavior change until an operator opts in and provisions
  `AGENT_PROFILE_PATH`. No existing MCP tool, HTTP route, or DB method
  changes signature.
- **Resource impact**: one new ticker goroutine per process for the
  executor poll loop and one for the approval-TTL sweep, both following the
  existing lightweight `sweeper` pattern (single DB query per tick, no
  connection pool growth). The executor additionally calls
  `pool.Borrow` per approved action — bounded by however many actions are
  `approved` at once, which is itself bounded by
  `AgentProfile.MaxAutonomousTurns`/owner behavior, not unbounded traffic.
- **Multi-replica safety**: the executor's CAS-based claim (`approved` →
  `executing`, step 4 above) is what makes it safe to run the poll loop on
  every replica simultaneously without a leader election — only one
  replica's `UpdateAgentActionStatus` call will see `RowsAffected() > 0`.
  This must be preserved; any future optimization (e.g. `SELECT ... FOR
  UPDATE SKIP LOCKED` for efficiency) must not weaken this guarantee.
- **Peer resolution risk**: `SendToInputPeer` needs a `tg.InputPeerUser`
  with both `UserID` and `AccessHash`; `Conversation` only stores
  `PeerTGID`. The access hash must come from somewhere (likely
  `internal/telegram/peercache.go`, given its existence). This is called
  out explicitly as an implementation risk in tasks.md — if the peer cache
  does not have a fresh-enough hash for a conversation partner who has not
  messaged recently, the executor's send can fail with `PEER_ID_INVALID`,
  which is exactly the class of failure that must land the row in the
  `executing` trap state rather than silently drop the reply.
- **Kill switch latency**: because `Enabled()` is checked per-`ExecuteOne`
  call (not cached at process start), flipping `AGENT_KILL_SWITCH` takes
  effect within one poll interval for actions not yet claimed, and
  immediately blocks new claims — but cannot recall a send already in
  flight inside step 6, which is the same "can't un-send a message"
  limitation the issue already accepts via the no-auto-retry rule.
- **Risk: restricted-field leakage via disclosure text or draft payload.**
  Mitigation: `profile.Profile`'s public accessor never exposes restricted
  fields (structural, not filtered), and the executor only ever appends
  `DisclosureText` (a single operator-authored string from the DB row) —
  it never interpolates arbitrary profile fields into the outgoing text,
  so there is no code path where a restricted field could leak through the
  send path even if a future caller mis-scopes something upstream.
