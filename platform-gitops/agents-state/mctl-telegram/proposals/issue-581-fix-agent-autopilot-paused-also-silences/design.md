# Design: issue-581-fix-agent-autopilot-paused-also-silences

## Current state

### The policy engine

`policy.Evaluate` (`internal/agent/policy/policy.go:285-397`) is a pure
function. It applies hard denials in a fixed order, then accumulates
require-approval reasons. The relevant prefix is:

```go
// policy.go:286   if in.GlobalKill { return deny("global kill switch engaged") }
// policy.go:296   cross-user Profile/Conversation guard (ActionTypeReply only)
// policy.go:300   switch in.Profile.Mode { ... case db.AgentModeOff: return deny("agent mode is off") ... }
// policy.go:307
if in.Profile.AutopilotPaused {
    return deny("autopilot paused for this account")
}
// policy.go:310-316  (the carve-out's contract comment)
// policy.go:317
if in.Action.Type == db.ActionTypeOwnerSummary || in.Action.Type == db.ActionTypeOwnerApproval {
    return Result{Decision: Allow, Reasons: []string{"owner-facing action"}}
}
// policy.go:320   conversation state switch (taken over / closed / paused)
// policy.go:331   blocked-sender check
```

There are exactly five call sites of `Evaluate`:
`internal/agentapi/actions.go:207` (`handleProposeReply`, always
`ActionTypeReply`), `internal/agentapi/actions.go:429` (`handleOwnerFacing`,
owner summary/approval), and `internal/agent/executor/executor.go:283`
(`send`) and `:561` (`recoverOne`), plus the definition itself.

### What happens to an owner-facing action today

`handleOwnerFacing` (`internal/agentapi/actions.go:388-508`) is the single
funnel for both `POST /notify/summary` (`send_owner_summary`) and
`POST /actions/request_owner_approval`. It loads the profile, evaluates
policy, and then:

```go
// actions.go:447-449
status := db.ActionExecuted
if result.Decision != policy.Allow { status = db.ActionDenied }
```

If the persisted row is `denied` it returns at `actions.go:487` — **before**
`InsertOwnerNotification` at `:498`. No `owner_notifications` row is ever
created, so `control.Notifier.DeliverPending` has nothing to deliver and the
owner is never told. The HTTP response carries
`{"decision":"deny","reasons":[...]}` back to the worker, which is the only
place the reason exists outside the `agent_actions` table.

Owner-facing actions are inserted directly as `executed` or `denied`; they
never enter `approved` or `executing`, so `Executor.ProcessApproved`
(`executor.go:230`, which lists `db.ActionApproved` only) and
`Executor.send`/`recoverOne` never see them. **The issue's claim that the
owner-facing denial is terminalised by `UpdateAgentActionStatus(...
ActionDenied)` in `internal/agent/executor/executor.go` is not accurate for
owner-facing actions** — that executor path only terminalises *reply* actions
that were already `approved`. The owner-facing terminalisation happens in
`handleOwnerFacing`. The observable symptom the issue describes is real; the
file is different.

### The owner transport

There is no separate control chat. The owner channel is the account's own
Telegram **Saved Messages** over MTProto:
`internal/telegram/sendself.go` → `control.SelfSender`
(`internal/agent/control/notifier.go:45-56`) → `poolSelfSender`
(`cmd/server/main.go:215`). `Notifier.DeliverPending`
(`notifier.go:132-214`) drains `owner_notifications` every 30s via
`sweeper.AgentNotifier` (`cmd/server/main.go:319`).

Critically, **the notifier package never calls `policy.Evaluate` and has no
`AutopilotPaused` check at all**. Its only gate is the kill switch:

```go
// notifier.go:133-139
if n.GlobalKill != nil && n.GlobalKill() {
    return 0, 0, nil
}
```

So the delivery half of the owner channel already behaves the way this issue
wants: it is silenced only by `AGENT_KILL_SWITCH`. The pause gate lives
exclusively upstream, at insert time, inside `Evaluate`. Fixing the ordering
therefore needs no transport work whatsoever.

### How an account gets paused

`autopilot_paused` is easy to enter and hard to leave:

- `EnsureAgentProfile` (`internal/db/agent_domain.go:147-162`) inserts
  `true` for every new profile — so paused is the *default* state.
- `/mctl pause` (`internal/agent/control/router.go:285-293`) sets it.
- The agent itself can set it, via the `pause_autopilot` MCP tool
  (`internal/agentworker/mcpserver.go:333-347` →
  `client.PauseAutopilot`, `internal/agentworker/client.go:380`).
- The **only** way back is `POST /autopilot/pause {"paused":false}`
  (`internal/agentapi/misc.go:108`) or the admin profile update
  (`internal/agentapi/profilehandler.go:149`). There is no `/mctl` unpause —
  `/mctl continue` only resets *conversation* state
  (`router.go:262-283`), and the pause confirmation text says so explicitly
  ("autopilot itself stays paused until you re-enable it via the agent API").

That asymmetry is what turns a policy-ordering detail into an operational
failure: an account can drift into paused-and-silent by default, by an
owner's `/mctl pause`, or by the model's own decision, and then stay there
indefinitely with no signal.

### The evidence trail

`docs/reports/communication-agent-c1.md:261-275` records the live incident:

> `autopilot_paused=true` is an unconditional hard **deny** checked before
> `mode` is even read ... every drafted reply since the soak opened was
> silently denied with zero owner-visible signal (confirmed live: action
> #42, `policy_reasons="autopilot paused for this account"`).

`docs/runbook.md:144-156` lists the containment controls and already
*documents* the intended behaviour that the code contradicts:

> - `agent_profiles.autopilot_paused=true` denies autonomous replies for that
>   account.

"Autonomous replies" — not owner notifications. The docs and the policy
comment agree with each other and disagree with the code.

## Proposed solution

Two phases. Phase A is the minimal correctness fix and is independently
shippable; Phase B closes the remaining silence for denied *replies*. The
recommendation is to approve both.

### Phase A — move the owner-facing carve-out above the pause gate

In `internal/agent/policy/policy.go`, relocate the owner-facing
short-circuit currently at `:317-319` so it sits immediately after the mode
switch (`:300-306`) and immediately **before** the `AutopilotPaused` check
(`:307-309`). Rewrite the contract comment at `:310-316` to state the new,
now-accurate ordering: owner-facing actions clear the kill switch and the
mode gate, and are exempt from the autopilot-pause gate and from every
per-conversation gate below.

Net effect, as a decision table:

| Gate engaged        | `propose_reply` | `send_owner_summary` / `request_owner_approval` |
|---------------------|-----------------|--------------------------------------------------|
| `AGENT_KILL_SWITCH` | deny            | deny (unchanged)                                 |
| `mode = off`        | deny            | deny (unchanged)                                 |
| `autopilot_paused`  | deny (unchanged)| **allow (changed)**                              |
| conversation gates  | deny            | allow (unchanged)                                |

Nothing else moves. `Evaluate` stays pure and performs no I/O. No field is
added to `policy.Input`, so every existing table case keeps its zero values.

**Why `AGENT_KILL_SWITCH` must stay above the carve-out.** Four independent
reasons, and they compound:

1. *Purpose.* It is env-only and deliberately not a DB row — see
   `internal/config/config.go:192-197`: "so an operator can cut the agent off
   by redeploying config even if the database is unreachable or
   compromised." Its job is to stop *all* agent-originated traffic. Under a
   compromised worker, an "owner summary" is attacker-controlled text
   delivered into the owner's own Saved Messages; that is precisely what an
   emergency stop must be able to prevent.
2. *Redundancy.* Even if `Evaluate` allowed it, `DeliverPending` returns
   early under the kill switch (`notifier.go:133-139`), by design and with a
   comment saying so. The action would produce a `pending` row that reaches
   nobody. Moving the carve-out above the kill switch would buy nothing but
   a queue of undelivered rows.
3. *No confusion to fix.* The failure this issue is about is "the operator
   cannot tell paused from idle." Someone who set `AGENT_KILL_SWITCH=true`
   and redeployed is, by construction, already informed.
4. *Scope.* The issue's own constraints forbid weakening it, and the
   existing tests that pin it (`policy_test.go:295` and
   `TestHandleOwnerFacing_KillSwitchBlocksNotification`,
   `internal/agentapi/server_test.go:1018`) stay green unmodified.

**Why `mode = off` must stay above the carve-out.** `mode` is the account's
*configuration*: observe / guarded / off (`policy.go:300-306`).
`off` means the account has opted out of the communication agent. It is a
durable, owner-chosen state with no resumption story attached, and an
opted-out account should not receive agent-generated Saved Messages at all —
those would read as unsolicited noise in the owner's own chat. There is also
nothing to report: an account in `off` mode should not be producing drafts
whose suppression needs explaining.

`autopilot_paused` is different in kind on three counts, and this is the
argument the issue asked to have made rather than assumed:

- **It is the default.** `EnsureAgentProfile` sets it `true` for every new
  profile (`agent_domain.go:157`). A gate that is on by default and silences
  owner notifications means silence is the *out-of-the-box* behaviour of the
  product. `mode=off` and `AGENT_KILL_SWITCH` are both opt-in states someone
  deliberately entered.
- **The model can set it.** `pause_autopilot`
  (`mcpserver.go:333-347`) lets the agent stand itself down mid-turn. Under
  today's ordering, the `send_owner_summary` explaining *why* it stood down
  is denied by the flag the agent just set. That is the sharpest form of the
  bug: the agent can decide a conversation is beyond it and is then
  structurally unable to say so. Neither `mode` nor the kill switch is
  reachable by the model.
- **It is a hold, not an opt-out.** Its whole point is that the owner
  intends to come back — which requires knowing something happened while
  they were away. `mode=off` carries no such expectation.

So: pause moves; kill switch and mode do not. All three relative positions
get pinned by tests rather than left incidental.

### Phase B — a deterministic pause notice for denied replies

Phase A makes the owner-facing *path* work while paused, but a
`propose_reply` denied for pause still produces no owner signal unless the
model separately chooses to call `send_owner_summary`. The soak report's
complaint was exactly about denied drafts. Close that server-side, so the
signal does not depend on model behaviour.

1. Add a machine-readable gate code to `policy.Result` (not `Input`, so no
   table case changes):

   ```go
   type Gate string
   const (
       GateNone            Gate = ""
       GateKillSwitch      Gate = "kill_switch"
       GateModeOff         Gate = "mode_off"
       GateAutopilotPaused Gate = "autopilot_paused"
   )
   // Result gains: Gate Gate
   ```

   Set only by the three account-wide denials; `GateNone` everywhere else.
   `Evaluate` stays pure. Callers never string-match a human-readable
   reason.

2. In `handleProposeReply` (`internal/agentapi/actions.go:207-240`), in the
   `case policy.Deny` branch, when `result.Gate == policy.GateAutopilotPaused`
   also call `Store.InsertOwnerNotification` with
   `Kind: db.NotificationAlert`, `ActionID:` the denied action id, and a
   short body naming the conversation and the reason — **not** the draft
   text. `db.NotificationAlert` (`internal/db/agent_actions.go:1143`) is
   already declared and currently has no producer in non-test code; this is
   the kind it was declared for.

3. Idempotency is free: `InsertOwnerNotification` has a unique partial index
   on `action_id` and returns the existing row's id on conflict
   (`agent_actions.go:1228-1290`), so a redelivered job that resolves its
   action through the `(job_id, action_type)` key cannot queue a second
   notice.

4. A notification-enqueue failure here is best-effort (log and continue),
   **unlike** the approval-notification path at `actions.go:284-296` which
   must fail the request because the notification is the only carrier of the
   approval code. A pause notice carries no code and no irreplaceable state;
   failing the whole `propose_reply` over it would be a worse outcome than a
   missed notice.

Delivery then rides the existing notifier unchanged: `DeliverPending` has no
pause gate, so a paused account's alert goes to Saved Messages on the next
30s sweep, and remains correctly silenced by the kill switch.

### Phase C — documentation

Update `docs/runbook.md`'s "Communication Agent operations" section
(`##` at `:142`; the containment-controls preamble is `:144-156`, before the
first `###` at `:158`):

- Fix the pre-existing "three independent containment controls" lead-in at
  `:144`, which is followed by four bullets and by "all four controls
  together" at `:155`.
- Amend the `autopilot_paused` bullet at `:150` and the config-table row at
  `:209` ("Per-account autonomous action pause.") to state the new
  semantics.
- Add a short paragraph after `:156` stating what an operator should expect
  from a paused account: recruiter-facing replies stop and are recorded in
  `agent_actions` with `policy_reasons="autopilot paused for this account"`;
  the owner still receives Saved Messages (per-draft pause alerts, plus any
  `send_owner_summary`/`request_owner_approval` the agent raises); total
  silence means `AGENT_KILL_SWITCH`, `mode=off`, or a disabled listener, not
  a pause. Cross-reference the C1 report incident so the next soak does not
  re-diagnose it.

### Test-ordering conflict the operator must accept

`TestEvaluate_OwnerFacingStillDeniedByAccountWideGates`
(`internal/agent/policy/policy_test.go:290-309`) has an explicit
`{"autopilot paused", ...}` case at `:297` asserting the behaviour this
proposal changes. That one case must be **moved** into a new
"owner-facing allowed while paused" table. It is the only existing case that
must change; the `{"autopilot paused", ...}` case in `TestEvaluate_DenyRules`
at `:41` uses `ActionTypeReply` and stays green unmodified, as does
everything else in the file. This is a deliberate, reviewed edit — not a
test weakened to fit an implementation — and it is called out here because
the issue's acceptance criteria as written cannot all hold at once.

## Alternatives

**Option 2 in isolation — keep the deny, make it observable.** Leave the
ordering alone and emit an owner notification whenever an owner-facing action
is denied for pause. Dropped as the primary because it is strictly worse than
Phase A while being more code: it preserves a contradiction between
`policy.go:310-316`'s stated contract and the behaviour, it needs a
notification-emitting side channel in `handleOwnerFacing` that duplicates
what a correct ordering gets for free, and it produces the absurd result of
notifying the owner that the agent was prevented from notifying the owner.
Its *useful half* — deterministic, model-independent signalling — is kept and
narrowed to the reply-denial case as Phase B, where there genuinely is no
owner-facing action to allow.

**Option 3 — downgrade replies to require-approval while paused.** Dropped.
It changes what pausing means for the recruiter-facing path, which the issue
explicitly wants preserved (`AC 1`: an autonomous reply is still refused). It
would also convert every paused draft into a `pending_approval` row with a
live approval code, so an owner typing `/mctl approve` could send a reply
from an account they had deliberately paused — the exact bypass
`pause_autopilot`'s anti-prompt-injection comment
(`mcpserver.go:324-333`) is written to prevent. Blast radius is the widest of
the three for the least benefit.

**Move the carve-out above all three gates.** Dropped for the reasons argued
under Phase A: it would weaken `AGENT_KILL_SWITCH` (out of scope by the
issue's own constraint, and pointless given `notifier.go:133-139` already
blocks delivery) and would push Saved Messages into accounts that opted out
via `mode=off`.

**Gate the notifier instead of the policy engine.** Add an
`AutopilotPaused` check to `DeliverPending` and allow owner-facing actions
everywhere in `Evaluate`. Dropped: it would require the notifier to load a
profile per row (it currently touches the store only for claim/format/mark),
splitting the account-gate authority across two packages. `policy.Evaluate`
is documented as "the server-side authority on what the communication agent
may do" (`policy.go:1-5`); the gates belong there.

## Platform impact

**Migrations.** None. No schema change, no new column, no new table.
`db.NotificationAlert` and the `owner_notifications` unique partial index on
`action_id` already exist.

**Backward compatibility.** `policy.Result` gains a field; it is constructed
by value in `Evaluate` and consumed by field name at all four call sites, so
adding `Gate` is source-compatible. `policy.Input` is unchanged, so every
existing table-driven case keeps its zero values. No API contract changes:
`handleOwnerFacing`'s response shape is identical, it simply now returns
`decision: "allow"` with a non-zero `notification_id` in a case where it
previously returned `decision: "deny"`. The worker's `OwnerFacingResult`
(`internal/agentworker/client.go`) needs no change.

**Resource impact.** Phase A: none. Phase B: one extra
`owner_notifications` row per pause-denied draft, plus one Saved Messages
send per row on the 30s sweep. Volume is bounded by inbound recruiter
messages the agent chose to answer, and every row is already
`truncateForTelegram`-bounded (`notifier.go:28-38`) and encrypted at rest via
`SealForUser` (`agent_actions.go:1252-1258`).

**Risks and mitigations.**

- *Risk: notification volume during a sustained soak.* Mitigation: the
  notice is one short line per denied draft, deduped per action id. If it
  proves noisy, a per-conversation-per-pause-window throttle is a
  follow-up — see `requirements.md` open question 3. Under-notifying is the
  failure being fixed, so erring toward more signal is the correct default.
- *Risk: pausing feels less "off" to owners who read pause as total
  silence.* Mitigation: this is exactly what the runbook change in Phase C
  exists to state, and the `/mctl pause` confirmation text
  (`router.go:292`) can carry one added clause noting that notifications
  continue.
- *Risk: privacy.* The pause notice body must name the conversation and the
  reason only, never the draft text, a phone number, or session material —
  `.claude/CLAUDE.md` safety rules and `internal/audit/redact.go`. No new
  log fields are introduced; the enqueue-failure log line carries only
  `action_id`/`user_id`, matching the surrounding `logHandlerErr` calls.
- *Risk: the changed test case is read as a weakened assertion.* Mitigation:
  the moved case is replaced by a *stronger* table that pins all three gates
  against both owner-facing action types, and the commit message plus the
  test comment must name issue #581 and the C1 report, following the
  package's established convention of citing the finding each test guards.
- *Risk: the fix passes tests but does not change behaviour.* Mitigation:
  the mutation check in `tasks.md` T7 — revert the one-line reorder and
  confirm the new cases go red — is a required step, not an optional one.
