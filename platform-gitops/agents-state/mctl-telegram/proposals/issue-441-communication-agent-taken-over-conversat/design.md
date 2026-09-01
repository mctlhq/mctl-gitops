# Design: issue-441-communication-agent-taken-over-conversat

## Current state

`internal/agent/policy/policy.go`'s `Evaluate` (lines 285-389) is the only
authority on whether a proposed communication-agent action may proceed. It
runs the following gates in order, denying at the first one that fires:

1. `GlobalKill` (line 286-288).
2. Cross-user Profile/Conversation guard, scoped to `db.ActionTypeReply`
   only (lines 296-299) — owner-facing types are exempt by an explicit
   `in.Action.Type == db.ActionTypeReply &&` prefix.
3. `Profile.Mode` switch: deny on `db.AgentModeOff` or unrecognized mode
   (lines 300-306).
4. `Profile.AutopilotPaused` (lines 307-309).
5. `Conversation.State` switch (lines 310-320): allow-through only on
   `db.ConversationActive`; deny on `db.ConversationTakenOver`,
   `db.ConversationClosed`, `db.ConversationPaused`, and any unrecognized
   value (including the empty string a zero-value `db.Conversation`
   carries).
6. `isBlocked` on `Profile.BlockedSenders` vs `Conversation.PeerTGID`
   (lines 321-323).
7. `Action.Type` switch (lines 325-331): `db.ActionTypeReply` falls
   through to the reply-specific checks below (peer match, disclosure
   text, length, URL/credential scanning, rate limit, allowlist);
   `db.ActionTypeOwnerSummary` / `db.ActionTypeOwnerApproval` return
   `Allow` immediately; anything else is denied as unrecognized.

Because step 5 runs before step 7, an owner-facing action can never reach
its own always-allow branch once the conversation is not active. The three
denying conversation states are reached routinely: `taken_over` is set
automatically by `internal/agent/listener/listener.go:323` whenever the
owner replies in the thread by hand, `closed`/`paused` are set through
`internal/agent/control/router.go`'s `/mctl` command handlers.

`internal/agentapi/actions.go`'s `handleOwnerFacing` (lines 389-462, shared
by `handleNotifySummary` and `handleRequestOwnerApproval`) already works
around one slice of this: when `req.ConversationID == 0` (a
conversation-less notification, e.g. a general daily digest) it builds
`policy.Input` with a synthetic `db.Conversation{State:
db.ConversationActive}` instead of a zero-value one, specifically so step 5
does not deny on the empty-string default case. Its own comment
(lines 409-417) spells out that this is a deliberate dodge of step 5, and
`policy_test.go`'s `TestEvaluate_OwnerActionsAndPeerZero` (lines 250-255)
sets `State: db.ConversationActive` explicitly to reach the same code path
in a test — i.e. the "owner-facing bypasses conversation state" property is
asserted only for the synthetic zero-conversation case, never for a real,
loaded conversation row. When `req.ConversationID != 0`, `handleOwnerFacing`
loads the real row via `s.Store.GetConversation` (line 420) and uses its
actual `State` — which is exactly the case that silently denies once that
conversation is `taken_over`, `closed`, or `paused`.

The result observed in the issue: `agent-worker-preview` ran a job for an
inbound recruiter message in a `taken_over` conversation, the model called
`send_owner_summary`, `handleNotifySummary` -> `handleOwnerFacing` ->
`policy.Evaluate` denied at step 5 with reason `"conversation taken over by
owner"`, the denial was persisted as an `agent_actions` row with
`Status: db.ActionDenied` (`actions.go:445-454`), and the model then called
`complete_agent_job` with that action's ID as `result_action_id`. Because
`POST /jobs/{id}/complete` (`internal/agentapi/events.go:205+`) only
requires an *exact persisted result id* — a denied row qualifies exactly as
well as an executed one — the job completed with `status=completed`, and
`internal/agentworker/worker.go:127-130` logged
`outcome=completed`. Nothing distinguishes a delivered notification from a
silently denied one in that log line or in the job's terminal status.

## Proposed solution

Reorder `Evaluate` so the owner-facing short-circuit runs immediately after
the account-wide gates (`GlobalKill`, `Mode`, `AutopilotPaused`) and before
the per-conversation gates (`Conversation.State`, `isBlocked`):

```go
if in.Profile.AutopilotPaused {
    return deny("autopilot paused for this account")
}
// Owner-facing actions notify the human, not the recruiter: they encode
// "tell me what happened," not "reply on my behalf." They must still clear
// every account-wide gate above (kill switch, mode, autopilot pause) but
// must never be silenced by a per-conversation instruction below (taken
// over / closed / paused, or that peer being blocked) — those gates exist
// to keep the agent quiet toward the recruiter, not to keep the owner
// uninformed.
if in.Action.Type == db.ActionTypeOwnerSummary || in.Action.Type == db.ActionTypeOwnerApproval {
    return Result{Decision: Allow, Reasons: []string{"owner-facing action"}}
}
switch in.Conversation.State {
...
```

and drop the now-redundant `case db.ActionTypeOwnerSummary,
db.ActionTypeOwnerApproval:` arm from the later `Action.Type` switch,
leaving it to only distinguish `db.ActionTypeReply` (falls through to the
existing reply checks) from anything unrecognized (denied, unchanged).

This is a pure reordering — no new state, no new fields on `Input` or
`Result`, no schema change. It changes exactly one thing: which action
types are subject to the `Conversation.State` and `isBlocked` gates. Reply
actions are unaffected because the switch statements they still pass
through are untouched; only their relative position for owner-facing types
moves.

`internal/agentapi/actions.go`'s `handleOwnerFacing` no longer needs its
`ConversationID == 0` special case, because `Evaluate` now allows
owner-facing actions regardless of `Conversation.State` — the zero-value
`db.Conversation{}`'s empty `State` no longer matters for this action type.
Simplify:

```go
var conv db.Conversation
if req.ConversationID != 0 {
    c, err := s.Store.GetConversation(ctx, id.UserID, req.ConversationID)
    ...
    conv = *c
}
```

and update the comment block (lines 409-417) to explain the new invariant
instead of the old workaround, and update the comment at lines 439-444 to
note that a `Deny` result here can now only mean the kill switch, mode, or
autopilot-pause gate fired (never conversation state or blocklist).

`policy_test.go` changes:

- Update `TestEvaluate_OwnerActionsAndPeerZero` (lines 232-256): the
  `State: db.ConversationActive` on the case at lines 250-255 stops being
  load-bearing; change it to a non-active state (e.g. `taken_over`) so the
  test actually exercises the property it claims to, and update its
  comment accordingly.
- Add cases (either as new `t.Run` subtests or appended to the existing
  table-driven tests) covering:
  - `taken_over` / `closed` / `paused` + `db.ActionTypeOwnerSummary` ->
    `Allow`.
  - `taken_over` / `closed` / `paused` + `db.ActionTypeOwnerApproval` ->
    `Allow`.
  - Blocked sender (`Profile.BlockedSenders` containing
    `Conversation.PeerTGID`) + owner-facing action -> `Allow` (pins the
    `isBlocked` side effect called out in the Open Questions section of
    `requirements.md`).
  - `taken_over` + `db.ActionTypeReply` -> `Deny` (already covered by the
    existing `TestEvaluate_DenyRules` "taken over" case using
    `baseInput()`, which defaults `Action.Type` to
    `db.ActionTypeReply` — kept as an explicit regression pin, not
    removed).
  - `GlobalKill` / `Mode == db.AgentModeOff` / `AutopilotPaused` +
    owner-facing action -> `Deny` (new; the existing `TestEvaluate_DenyRules`
    table only exercises these gates with `baseInput()`'s default
    `Action.Type == db.ActionTypeReply`, so they do not currently pin that
    owner-facing types are equally denied by the account-wide gates).

No other files reference the ordering of these two switches (checked via
`Grep` for `ConversationTakenOver`, `ActionTypeOwnerSummary`,
`ActionTypeOwnerApproval` across the repo — the only production call sites
are `policy.go` itself and `actions.go`'s two owner-facing handlers).

## Alternatives

1. **Special-case only `taken_over`, keep `closed`/`paused` denying
   owner-facing actions.** Rejected: the issue's evidence
   (`policy_test.go:TestEvaluate_OwnerActionsAndPeerZero`'s existing
   `State: ConversationActive` dodge, and the "Scope" section's framing of
   the whole `Conversation.State` switch as the problem, not just one of
   its branches) treats all three denying states the same way — a paused
   or closed conversation is exactly as much "don't reply for me" and
   exactly as little "don't tell me" as a taken-over one. Splitting them
   would need a justification the issue does not provide and would leave
   the same silent-drop bug for two of the three states.

2. **Keep the switch order, add a conversation-state override field to
   `Input` (e.g. `IgnoreConversationState bool`) that `handleOwnerFacing`
   sets.** Rejected: adds a new knob to `Input` that every other caller of
   `Evaluate` (and every future one) has to understand and could
   misuse to bypass the gate for a `db.ActionTypeReply`, defeating the
   safety property `Evaluate`'s own package doc comment describes ("Model
   output and system prompts are never treated as a security boundary").
   The reorder achieves the same result while keeping the invariant
   structural (tied to `Action.Type`, not to a caller-supplied flag) and
   is a smaller diff.

3. **Fix it entirely in `handleOwnerFacing` by overriding `conv.State` to
   `db.ConversationActive` whenever `req.ConversationID != 0` too, mirroring
   the existing `ConversationID == 0` workaround.** Rejected: this is the
   "add a second special case" version of the bug that created the first
   special case. It still lets `Conversation.State` decide the fate of an
   action type whose contract says it should never depend on that field,
   it silently loses the real conversation's state on `agent_actions.
   PolicyReasons`-adjacent introspection paths that might read `conv` for
   other purposes later, and `policy_test.go`'s existing coverage would
   stay unable to express "owner-facing ignores conversation state" as a
   `policy` package-level property — it would remain an `agentapi`-level
   workaround, exactly the shape of code that let this bug hide for as
   long as it did.

## Platform impact

- **Migrations:** none. No schema, no new columns, no new `Input`/`Result`
  fields.
- **Backward compatibility:** the on-the-wire contract of
  `POST /notify/summary` and `POST /actions/request_owner_approval` is
  unchanged (same request/response shapes in `actions.go`); only the
  policy decision for a subset of previously-denied requests changes from
  `Deny` to `Allow`. Existing persisted `agent_actions` rows with
  `Status: db.ActionDenied` and reason `"conversation taken over by
  owner"` / `"conversation closed"` / `"conversation paused"` for
  owner-facing action types are historical audit records and are not
  rewritten — this is a forward-only behavior change, as is standard for
  this codebase's append-only action audit trail.
- **Resource impact:** negligible. The reordered check is O(1) and runs no
  additional I/O (`Evaluate` performs no I/O per its own doc comment,
  line 45).
- **Risks:**
  - *Behavior change risk:* previously-silent (to the owner) taken-over /
    paused / closed conversations will now generate visible summary/approval
    notifications. This is the intended fix, but it is a visible behavior
    change for any account currently relying (even accidentally) on the
    old silence. Mitigated by this being exactly the reported bug and by
    the issue's explicit request for this outcome.
  - *Scope-creep risk on `isBlocked`:* as detailed in
    `requirements.md`'s Open Questions, the literal reorder also lets
    owner-facing actions bypass the sender-blocklist gate, which the issue
    text does not explicitly discuss. Mitigated by calling it out
    explicitly here and in a dedicated regression test, so a reviewer can
    object and request the narrower `isBlocked`-preserving variant (moving
    only past `Conversation.State`, keeping `isBlocked` before the
    short-circuit) as a one-line follow-up if that turns out to be the
    intended scope.
  - *Regression risk on the reply path:* mitigated by not touching any
    reply-path logic and by the existing `TestEvaluate_DenyRules` table
    (which uses `baseInput()`'s `db.ActionTypeReply`) continuing to pass
    unmodified — it is a regression pin already in the tree.
