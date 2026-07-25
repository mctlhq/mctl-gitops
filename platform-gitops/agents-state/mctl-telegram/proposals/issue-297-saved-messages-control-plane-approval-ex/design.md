# Design: issue-297-saved-messages-control-plane-approval-ex

## Current state

The communication-agent spine already exists; this proposal fills three
named gaps in it plus the load-bearing pieces those gaps depend on.

**Already built and reusable as-is:**

- `internal/agent/policy/policy.go` — `Evaluate(Input) Result` is a pure
  function. It already denies on `GlobalKill`, `Profile.Mode == off`,
  `AutopilotPaused`, `Conversation.State` (`taken_over`/`closed`/`paused`
  all deny), blocked senders, URL/credential content, and rate/allowlist
  checks producing `RequireApproval`. This is the exact mechanism the
  issue asks the executor to call a second time immediately before the
  send RPC — no new policy logic is needed, only a second call site with
  freshly-fetched inputs.
- `internal/db/agent_actions.go` — `AgentAction` lifecycle constants,
  `InsertAgentAction` (idempotent per `(job_id, action_type)`),
  `UpdateAgentActionStatus` (CAS via `allowedActionTransitions`),
  `SetAgentActionExecuted` (dedicated CAS `executing -> executed`),
  `ExpireStaleAgentActions` (TTL sweep, already invoked hourly-minutely by
  `sweeper.AgentJobs` at `internal/sweeper/sweeper.go:190-204` using
  `cfg.AgentApprovalTTL`). **However** `allowedActionTransitions`
  (`agent_actions.go:266-270`) only permits
  `proposed -> {pending_approval, denied, approved}`,
  `pending_approval -> {approved, rejected}`, and
  `approved -> {executing}`. There is no path to `denied` from
  `pending_approval` or `approved`, and the doc comment on `executing`
  explicitly states "nothing auto-retries from executing... double-
  messaging a human is worse than not sending" (`agent_actions.go:36-40`).
  Both of these are precisely what this issue revises.
- `internal/telegram/sendself.go` — `SendToInputPeer`/`SendToSelf` already
  generate a random `RandomID` **inside** the call before issuing
  `MessagesSendMessage`; there is no parameter to supply a pre-generated,
  persisted one, which the crash-retry design requires.
- `internal/agent/listener/listener.go` + `extract.go` — the `Extracted`
  struct already produces `SavedCommandText` for any Saved-Messages text
  starting with `/mctl` (`isMCTLCommand`, `extract.go:45-48,68-84`), and
  `Listener.persist`'s `EventKindSavedCommand` case already dedupes on the
  event id and calls `l.Router.HandleSavedText(ctx, userID, text)` when a
  router is set (`listener.go:213-229`). `cmd/server/main.go:93` currently
  constructs the listener with `nil` for that router. Separately,
  `EventKindOwnerOutgoing` handling **already** flips
  `Conversation.State` to `taken_over` the moment the owner sends anything
  in a tracked chat (`listener.go:193-211`) — this is the exact mechanism
  the issue's "concurrent owner reply cancels pending" requirement needs,
  and it is already merged and working. The executor's obligation is
  simply to re-fetch `Conversation` right before sending so it observes
  that flip.
- `internal/agentapi/server.go` — `OwnerProfileProvider` interface and
  `Server.Profile`/`WithProfile` are already stubbed; `handleRecruiterProfile`
  in `misc.go` already 501s when `Profile == nil` and otherwise calls
  `s.Profile.PublicProfile(peerTGID)`. The interface's own doc comment
  names this issue as the PR that wires a real implementation in.
- `internal/metrics/metrics.go` — a `Registry` struct constructed once via
  `New()`, with a "Communication agent (M6)" section already holding
  `AgentEventsReceivedTotal`, `AgentJobsTotal`, `AgentDeadLetterTotal`. New
  metrics for this issue slot into the same struct/registration pattern.
- `internal/config/config.go` — `AgentEnabled`, `AgentKillSwitch`,
  `AgentApprovalTTL`, `AgentJobVisibility` are already loaded from env.
  `AGENT_PROFILE_PATH` does not exist yet.
- `internal/sweeper/sweeper.go`'s `AgentJobs` already ticks every minute
  and already calls `ExpireStaleAgentActions`; it does not notify the
  owner about expiries today — nothing consumes that transition.

**Does not exist yet (confirmed by directory listing):**
`internal/agent/control`, `internal/agent/executor`,
`internal/agent/profile`. No `random_id` column on `agent_actions`. No
`tg.UpdateDeleteMessages` dispatcher in the listener (only `OnNewMessage`/
`OnEditMessage` are registered in `listener.go:140-149`), so message
deletion is currently invisible to the whole agent pipeline.

## Proposed solution

### 1. Schema additions (`internal/db/agent_schema.go`, `agent_actions.go`)

Additive, `addColumnIfMissing`-style migrations (same idiom already used
repeatedly in `db.go`/`agent_schema.go`):

- `agent_actions.random_id` (nullable BIGINT/INTEGER) — the persisted
  Telegram `random_id` for the pending/in-flight send.
- `agent_actions.source_event_id` (nullable TEXT, referencing
  `incoming_events.event_id`) — records which incoming event the draft was
  derived from, so the executor can detect "this event was superseded by
  an edit/delete since the draft was written."
- `agent_actions.approved_at` (nullable TIMESTAMP/TIMESTAMPTZ) — stamped
  only on the `pending_approval -> approved` transition (or on direct
  guarded-mode auto-approval insert), so approve-to-executed latency can be
  computed without conflating it with the generic `updated_at` column that
  every transition overwrites.

`allowedActionTransitions` gains two entries so denial is reachable from
both places the issue requires it (owner takeover / rate-limit flip caught
at pending time; edit-delete or re-check-fails caught at approved/executing
time):

```
ActionPendingApproval: {ActionApproved, ActionRejected, ActionDenied}
ActionApproved:        {ActionExecuting, ActionDenied}
```

The `approved <-> executing` crash-retry step is deliberately **not**
modeled as a same-from/to entry in that generic map (a CAS's `from == to`
reads oddly and the map already reserves special transitions for dedicated
methods — see `SetAgentActionExecuted`, `ExpireStaleAgentActions`). Instead
a new dedicated method, `ClaimAgentActionForSend(ctx, userID, id) (randomID
int64, alreadyExecuting bool, err error)`, is added: if the row is
`approved`, it generates a fresh `random_id`, persists it, and CASes to
`executing`, returning `alreadyExecuting=false`; if the row is already
`executing` (crash recovery), it returns the existing persisted
`random_id` unchanged with `alreadyExecuting=true` and touches nothing.
This one method is the entire "self-heal" mechanism the issue asks for —
the executor's per-tick loop calls it uniformly for both fresh approvals
and stuck rows, so there is exactly one send code path, not two.

A second dedicated method, `InvalidateAgentAction(ctx, userID, id, reason
string) (bool, error)`, CASes `{pending_approval, approved, executing} ->
denied`, used by: the pre-send policy re-check failing, and edit/delete
invalidation. Kept as its own method (not routed through the generic
transition map, which is single-`from`) because it accepts any of three
source statuses atomically in one guarded UPDATE
(`WHERE status IN (...)`), mirroring the multi-purpose but tightly scoped
style of the existing dedicated methods.

To claim work across multiple server replicas without double-sending, a
`ClaimApprovedAgentActions(ctx, replicaID string, limit int) ([]AgentAction,
error)` method is added, modeled directly on the existing
`ClaimAgentJobs` SKIP LOCKED pattern used for `agent_jobs` — selecting
`approved` and `executing` rows account-wide (not scoped to one listener
account, since the executor is a single process-wide loop, unlike the
per-account listener pool).

### 2. `internal/agent/control` — parser + notifier + router

- `command.go`: `type Command struct { Verb, Arg string }` and
  `ParseCommand(text string) (Command, bool, error)` — pure, table-driven,
  matching the style of `internal/agent/policy/policy_test.go`'s
  table-driven `TestEvaluate_DenyRules`. The bool return distinguishes
  "not a command at all" (ordinary Saved Messages note — already filtered
  upstream by `isMCTLCommand`, but the parser stays defensive) from a
  recognized verb.
- `notifier.go`: `Notifier{ Store *db.Store, Send func(ctx, userID int64,
  text string) (int, error) }` — `Send` is a narrow function type (not the
  concrete `*telegram.Client`), mirroring the existing narrow-interface
  pattern (`agentapi.OwnerProfileProvider`) so `control` does not import
  `gotd/td` directly; `cmd/server/main.go` wires it to a closure over the
  client pool's `Borrow` + `telegram.SendToSelf`. Formats summaries and
  approval requests (draft + `/mctl approve <code>` / `reject <code>`
  lines) and marks `owner_notifications` sent/failed.
- `router.go`: implements `listener.CommandRouter.HandleSavedText`.
  Dispatch table:
  - `status` -> aggregate open conversations + pending approvals count via
    existing store queries, reply via Notifier.
  - `leads` -> `Store.ListJobLeads`, reply with a compact list.
  - `show <id>` -> `Store.ListConversationMessages` for that conversation
    id, reply with a short transcript excerpt.
  - `continue <id>` -> `Store.SetConversationState(active)` +
    `Store.ResetAutonomousTurns` (see Open Questions).
  - `pause` -> `Store.SetAgentAutopilotPaused(true)` (account-wide,
    reusing the exact method `internal/agentapi/misc.go`'s
    `handleAutopilotPause` already uses for the MCP-facing pause tool).
  - `takeover <id>` -> `Store.SetConversationState(taken_over)` directly.
  - `approve <code>` / `reject <code>` -> `Store.GetAgentActionByCode` then
    `Store.UpdateAgentActionStatus` CAS `pending_approval -> approved` (on
    approve, also stamps `approved_at`) / `-> rejected`.
  - Every branch replies through `Notifier` with a short confirmation.
  - Unrecognized/malformed command -> a help confirmation, never an error
    surfaced to the owner as a stack trace.

### 3. `internal/agent/executor` — poll loop

A single ticker loop (same shape as `sweeper.AgentJobs`), each tick:

1. `ClaimApprovedAgentActions` (SKIP LOCKED, this replica).
2. For each claimed row: reload `AgentProfile` and `Conversation` fresh
   from the store (never reuse values captured earlier in the pipeline).
3. Reconstruct `policy.Action{Type: ActionTypeReply, Intent, Text: payload,
   PeerTGID: conversation.PeerTGID}` and call `policy.Evaluate` again.
4. If the source event was superseded — a newer `incoming_events` row for
   the same `(chat, message_id)` exists with a later edit-marker, or the
   message is now flagged deleted (see listener addition below) — call
   `InvalidateAgentAction(..., "source message edited/deleted")` and stop.
5. Else if `Evaluate` != `Allow`, call `InvalidateAgentAction` with the
   policy reasons and stop. This is also where "owner replied concurrently"
   resolves for free: `Conversation.State` is now `taken_over` (set by the
   listener's existing `EventKindOwnerOutgoing` path, or by `/mctl
   takeover`), so `Evaluate` denies without any bespoke concurrency
   plumbing in the executor.
6. Else call `ClaimAgentActionForSend` to obtain the persisted
   `random_id` (freshly minted, or the existing one on a crash-retry pass),
   append `policy.DisclosureSep + profile.DisclosureText` to the payload,
   and send via a new `telegram.SendToInputPeerWithRandomID(ctx, c, userID,
   peer, text, randomID)` (an additive variant alongside the existing
   `SendToInputPeer`/`SendToSelf` in `sendself.go`, extracting the shared
   body so the existing functions become thin wrappers that generate their
   own id and call the new one). The peer is resolved from
   `conversation.PeerTGID` through the existing
   `telegram.ResolvePeerCached`/peer-cache machinery (`peers.go`,
   `peercache.go`) rather than inventing new peer-resolution logic.
7. On RPC success: `SetAgentActionExecuted`, `IncrementAutonomousTurns`,
   `InsertConversationMessage(direction=agent_outgoing)`.
8. On RPC failure that is not a dedup-relevant error: leave the row
   `executing` for the next tick's retry-by-`random_id` (this is the
   intended self-heal path, not a failure to handle specially).

Rows still `executing` after N ticks (a small constant, e.g. 3, comfortably
longer than one send RPC's worst-case latency) increment the
`executing_stuck` gauge — expected to stay at 0.

### 4. Listener addition required by edit/delete invalidation

`internal/agent/listener/listener.go`'s `dispatcherFor` gains
`d.OnDeleteMessages(...)`, extraction gains a small
`db.EventKindMessageDelete` case (paralleling the existing
`EventKindMessageEdit`), and `persist` records it as an audited event. The
executor's step 4 above reads these rows (or a lighter-weight "is this
message id still live" check) to decide invalidation. This is the one
piece of this proposal that touches a directory the issue does not name
explicitly (`internal/agent/listener`); without it, "delete invalidates
draft" cannot be implemented at all, so it is treated as in-scope rather
than deferred — see requirements.md's Open Questions.

### 5. `internal/agent/profile` — owner profile provider

`OwnerProfileProvider` struct loads and parses YAML
(`gopkg.in/yaml.v2`, already an indirect dependency in `go.mod`, promoted
to direct) from `AGENT_PROFILE_PATH` once at startup into a struct with
`Identity`, `PublicProfile`, `Skills`, `Preferences`, `Restricted` sections
matching the issue's field list. `PublicProfile(peerTGID int64)
(map[string]any, error)` marshals only the first four sections — the
`Restricted` field is structurally absent from the returned value, not
merely filtered by key name, so a future field added to `Restricted`
cannot leak by omission from a filter list. A unit test walks the struct
via reflection/JSON round-trip asserting no key from `Restricted` ever
appears in `PublicProfile`'s output, so the guarantee holds even as the
schema grows. `cmd/server/main.go` constructs this and calls
`agentSrv.WithProfile(...)` when `AGENT_PROFILE_PATH` is set (gated the
same way other optional wiring is — absent path means the endpoint keeps
501ing, matching today's nil-`Profile` behavior).

### 6. Wiring (`cmd/server/main.go`)

- Construct `control.Router` (needs `*db.Store`, the `Notifier`) and pass
  it instead of `nil` at the existing `listener.New(store, agentQueue, nil,
  m)` call site.
- Construct `profile.OwnerProfileProvider` from `cfg.AgentProfilePath` (new
  config field) and call `agentSrv.WithProfile(...)`.
- Start `executor.Run(ctx, store, pool, cfg.ReplicaID, m, tickInterval)` as
  a new goroutine alongside the other `go sweeper.X(...)` calls, gated on
  `cfg.AgentEnabled` (matching the existing "off by default" convention —
  when the surface is off, nothing autonomously sends either).
- Add `AGENT_PROFILE_PATH` to `internal/config/config.go` and
  `.env.example`.

### 7. Observability additions (`internal/metrics/metrics.go`)

New collectors in the existing "Communication agent (M6)" section:
`AgentActionsTotal` (CounterVec by resulting status, mirroring
`AgentJobsTotal`'s shape), `AgentActionExecutingStuck` (Gauge),
`AgentApprovalLatency` (Histogram, seconds from `approved_at` to
`executed`), `AgentExecutorRestartsTotal` (Counter, incremented once in
`executor.Run`'s startup). `AgentDeadLetterTotal` already exists and is
reused as-is (it already counts `agent_jobs` dead-letters, which is the
queue-level dead-letter signal the issue asks to keep visible).

## Alternatives

1. **Keep `executing` as a true trap state and add an operator "unstick"
   endpoint instead of retry-by-`random_id`.** Rejected: this is the
   design the issue explicitly revises ("REVISED 2026-07-22 for crash
   recovery... replaces the original eternal-trap-state design"). It also
   does not remove the double-send risk, it just shifts the decision to a
   human who has no better information than the system does — MTProto's
   own `random_id` dedup already makes the retry provably safe.
2. **Eager, event-driven executor (approval triggers an immediate send
   attempt via a channel/pubsub) instead of a poll loop.** Rejected for
   this proposal in favor of the poll loop: every other background process
   in this codebase (`sweeper.Sessions`, `AuditLog`, `RefreshTokens`,
   `AgentRetention`, `AgentJobs`) is a plain ticker loop, and introducing a
   new intra-process signaling primitive is disproportionate complexity for
   the latency win, especially since approval latency is now an explicit
   metric rather than an implicit assumption. Can be revisited later purely
   as a tick-interval tuning problem without changing the state machine.
3. **Detect "concurrent owner reply" with a bespoke lock/version check on
   the action row instead of relying on `Conversation.State`.** Rejected:
   the listener already flips `Conversation.State` to `taken_over`
   synchronously with the owner's outgoing message, and `policy.Evaluate`
   already denies on that state. Building a second, parallel signal would
   duplicate existing, already-tested logic and risks the two signals
   disagreeing.
4. **Store the whole restricted-vs-public YAML split as two separate
   files instead of one file with a `restricted` section.** Rejected: the
   issue explicitly asks for one mounted file with sections; two files
   doubles the ops/rotation surface for no safety gain, since the
   in-process filtering already guarantees restricted data never reaches
   `PublicProfile`'s return value.

## Platform impact

- **Migrations**: three additive, nullable columns on `agent_actions`
  (`random_id`, `source_event_id`, `approved_at`) via the existing
  `addColumnIfMissing` idiom — no backfill required (existing terminal
  rows never need a `random_id`; any row already `executing` at deploy
  time, if one somehow exists, is picked up by the same claim query and
  gets a `random_id` minted lazily on the first executor tick after
  upgrade, since `ClaimAgentActionForSend` mints one whenever the column is
  NULL regardless of current status).
- **Backward compatibility**: `internal/agentapi` is untouched; the
  `OwnerProfileProvider`/`CommandRouter` interfaces are consumed exactly as
  already defined, so no call-site changes ripple beyond `main.go`'s
  wiring. Deployments with `AGENT_ENABLED=false` or no
  `AGENT_PROFILE_PATH` see no behavior change (matching every prior
  agent-workstream PR's off-by-default posture).
- **Resource impact**: one new ticker goroutine (executor) plus the
  already-existing per-account listener goroutines; DB load is one
  additional `SKIP LOCKED` claim query per tick (bounded by `limit`, same
  cost profile as the existing `agent_jobs` claim).
- **Risks and mitigations**:
  - *Double-send despite retry-by-`random_id`* — mitigated by generating
    and persisting the `random_id` strictly before the CAS to `executing`
    and strictly before the RPC, and by never generating a second
    `random_id` for a row already `executing`; covered by a dedicated
    crash-and-retry unit test per the issue's own test list.
  - *Stale approval bypassing a newly-true deny condition* — mitigated by
    the mandatory second `policy.Evaluate` call with freshly-loaded
    inputs; covered by a "policy-changed-between-approve-and-send" unit
    test.
  - *Owner's own message racing the agent's send* — mitigated by relying
    on the already-merged, already-tested `taken_over` transition rather
    than new concurrency code; covered by a
    "concurrent-owner-reply-cancels-pending" unit test.
  - *Restricted profile data leaking via a future field* — mitigated by
    structurally excluding the `Restricted` section from the marshaled
    output (not a key-based filter) plus a reflection-based leak test.
  - *New listener dispatcher (delete) regressing existing update
    handling* — mitigated by keeping the new case additive and mirroring
    the existing, already-tested edit-handling shape exactly.
