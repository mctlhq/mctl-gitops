# Autopilot pause must silence the agent toward the peer, not toward the owner

## Context

`policy.Evaluate` (`internal/agent/policy/policy.go:285`) applies its hard
denials in a fixed order. The `AutopilotPaused` gate at
`internal/agent/policy/policy.go:307-309` runs *before* the owner-facing
carve-out at `:317-319`, so while an account is paused the policy engine
denies not only the autonomous reply to the recruiter but also the
`send_owner_summary` / `request_owner_approval` actions whose entire purpose
is to tell the human what happened. `internal/agentapi/actions.go`
`handleOwnerFacing` turns that deny into an `ActionDenied` row and returns
without calling `InsertOwnerNotification`, so no `owner_notifications` row is
ever queued and `internal/agent/control.Notifier.DeliverPending` has nothing
to deliver. From the outside a paused account is indistinguishable from an
idle one — the behaviour `docs/reports/communication-agent-c1.md` recorded
during the sustained soak and left un-root-caused.

Three details make this worse than a cosmetic gap. First,
`Store.EnsureAgentProfile` (`internal/db/agent_domain.go:147-162`) inserts
`autopilot_paused = true` for every new profile, so "paused" is the *normal
steady state* of a freshly onboarded account: the default experience of the
product is silence. Second, the agent can pause *itself* through the
`pause_autopilot` MCP tool (`internal/agentworker/mcpserver.go:333-347`);
under today's ordering the very next `send_owner_summary` explaining why it
stood down is denied, so the agent can stand down without ever being able to
say so. Third, the carve-out's own comment
(`internal/agent/policy/policy.go:310-316`) already states the intended
contract — account-wide gates "exist to keep the agent quiet toward the
recruiter, not to keep the owner uninformed" — and the current ordering
contradicts exactly that half of it.

## User stories

- AS an account owner I WANT to keep receiving Saved Messages notifications
  while autopilot is paused SO THAT I can tell a paused account apart from an
  idle one without querying `agent_actions` by hand.
- AS an account owner I WANT autopilot pause to keep stopping every
  autonomous reply to a recruiter SO THAT pausing still means what it has
  always meant and my safety control is not weakened.
- AS the communication agent I WANT to be able to explain why I paused myself
  immediately after calling `pause_autopilot` SO THAT the owner learns the
  reason instead of only observing that the agent went quiet.
- AS a platform operator I WANT `AGENT_KILL_SWITCH` to keep silencing every
  agent-originated message, owner-facing included, SO THAT the outermost
  containment control keeps its all-or-nothing meaning.
- AS an operator reading `docs/runbook.md` I WANT the four containment
  controls to state what a paused account looks like from the outside SO
  THAT I do not re-diagnose this silence during the next soak.

## Acceptance criteria (EARS)

Policy ordering (Phase A):

- WHILE `Profile.AutopilotPaused` is true AND `Action.Type` is
  `db.ActionTypeReply` THE SYSTEM SHALL return `Deny` with the reason
  `autopilot paused for this account`.
- WHILE `Profile.AutopilotPaused` is true AND `Action.Type` is
  `db.ActionTypeOwnerSummary` or `db.ActionTypeOwnerApproval` THE SYSTEM
  SHALL return `Allow`.
- WHILE `GlobalKill` is true THE SYSTEM SHALL return `Deny` for every action
  type, owner-facing types included, regardless of `AutopilotPaused`.
- WHILE `Profile.Mode` is `db.AgentModeOff` THE SYSTEM SHALL return `Deny`
  for every action type, owner-facing types included, regardless of
  `AutopilotPaused`.
- WHEN both `GlobalKill` and `AutopilotPaused` are set for an owner-facing
  action THE SYSTEM SHALL return `Deny` with the kill-switch reason, so the
  outermost gate remains the one reported.
- THE SYSTEM SHALL keep `policy.Evaluate` a pure function performing no I/O.

Owner-facing delivery (Phase A):

- WHEN `POST /notify/summary` or `POST /actions/request_owner_approval` is
  called for an account with `autopilot_paused = true` and neither the kill
  switch nor `mode=off` is engaged THE SYSTEM SHALL insert the action with
  status `executed` and queue an `owner_notifications` row, returning a
  non-zero `notification_id`.
- WHILE an account is paused THE SYSTEM SHALL keep delivering pending
  `owner_notifications` rows through `control.Notifier.DeliverPending` —
  that sweep gates on the kill switch only
  (`internal/agent/control/notifier.go:133-139`) and SHALL NOT acquire a
  pause gate.

Deterministic pause notice (Phase B):

- WHEN `propose_reply` is denied solely because the account is paused THE
  SYSTEM SHALL queue an `owner_notifications` row of kind
  `db.NotificationSummary` linked to the denied action id, so the owner is
  told without depending on the model choosing to call `send_owner_summary`.
- IF the same denied action is replayed through a job redelivery THEN THE
  SYSTEM SHALL NOT queue a second notification, relying on
  `InsertOwnerNotification`'s unique partial index on `action_id`
  (`internal/db/agent_actions.go:1228-1290`).
- WHILE the kill switch or `mode=off` denies a reply THE SYSTEM SHALL NOT
  queue a pause notice — only the pause gate produces one.
- THE SYSTEM SHALL NOT include message bodies, phone numbers or session
  material in any log line added by this change, per
  `internal/audit/redact.go` and `.claude/CLAUDE.md`.

Configuration invariants:

- THE SYSTEM SHALL keep `EnsureAgentProfile` defaulting `autopilot_paused` to
  `true` for a new profile (`internal/db/agent_domain.go:157`).
- THE SYSTEM SHALL NOT change who may set `autopilot_paused` or how
  (`/mctl pause`, `POST /autopilot/pause`, `pause_autopilot` remain as-is).

Documentation:

- WHEN an operator reads the "Communication Agent operations" section of
  `docs/runbook.md` THE SYSTEM SHALL present, alongside the four containment
  controls, an explicit statement of what a paused account looks like from
  the outside: replies stop, owner notifications continue, and the kill
  switch is the control that produces total silence.

## Out of scope

- Per-hour/per-day send ceilings, cost ceilings, and anomaly-tripped kill
  switches (the C2 safety gate).
- Changing how `autopilot_paused` is set or who may set it.
- Re-designing the C1 approval flow.
- Weakening or re-ordering `AGENT_KILL_SWITCH`. This proposal argues it
  should keep denying owner-facing actions and does not change it.
- Moving the owner-facing carve-out above the `mode=off` gate. This proposal
  argues against it (see `design.md`).
- Making `Executor.ProcessApproved`'s per-action deny (currently only
  `slog.Warn` at `internal/agent/executor/executor.go:237`) owner-visible.
  Related, real, and deliberately left for a follow-up.

## Open questions

1. **An existing policy test case encodes the bug and must change.** The
   issue asks that existing cases pass unmodified, but
   `TestEvaluate_OwnerFacingStillDeniedByAccountWideGates`
   (`internal/agent/policy/policy_test.go:290-309`) contains an explicit
   `{"autopilot paused", ...}` case at `:297` asserting that owner-facing
   actions ARE denied while paused. Under Option 1 that case must be *moved*
   from the "still denied" table into a new "allowed while paused" table.
   Every other existing case, including the `{"autopilot paused", ...}` case
   in `TestEvaluate_DenyRules` at `:41` (which uses `ActionTypeReply`),
   passes unmodified. **The operator should confirm this single deliberate
   test edit at approval time**; it is the one place where the acceptance
   criteria as written cannot all hold simultaneously.
2. **Phase A alone, or Phase A + Phase B?** Phase A (reorder) makes the
   owner-facing *path* work while paused, but a reply that is denied for
   pause still produces no owner signal unless the model separately calls
   `send_owner_summary`. Phase B closes that deterministically at the cost of
   a small non-pure-policy change in `internal/agentapi/actions.go`. The
   recommendation is both; Phase A is independently shippable if the
   operator prefers the minimal diff.
3. **Should the Phase B pause notice be throttled?** As designed it is one
   notification per denied draft (idempotent per action id), so volume is
   bounded by inbound recruiter messages the agent chose to answer. A
   per-conversation-per-pause-window throttle would need a new store query.
   Recommendation: ship without a throttle, since under-notifying is the
   failure mode being fixed and Saved Messages is not a scarce channel.
4. **"An executor-level test" does not map cleanly onto the code.** The issue
   states the denial is terminalised by `UpdateAgentActionStatus(...
   ActionDenied)` in `internal/agent/executor/executor.go`; for *owner-facing*
   actions that is not where it happens. `handleOwnerFacing` inserts them
   directly as `executed` or `denied`
   (`internal/agentapi/actions.go`), and the executor only ever processes
   rows in `approved`/`executing`, which owner-facing actions never enter.
   This proposal therefore satisfies the intent with an `internal/agentapi`
   integration test (the layer that actually queues the notification), a
   `control.Notifier` test (delivery while paused), and an executor test that
   a paused account's *reply* is still denied at send time.
