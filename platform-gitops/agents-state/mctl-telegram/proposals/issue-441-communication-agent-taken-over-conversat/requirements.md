# Owner-facing notifications must survive non-active conversation state

## Context

`policy.Evaluate` (`internal/agent/policy/policy.go`) is the single
server-side gate every proposed communication-agent action passes through
before it can affect Telegram or the owner. Today it evaluates
`in.Conversation.State` (line 310) before it evaluates `in.Action.Type`
(line 325). Because `db.ConversationTakenOver`, `db.ConversationClosed`, and
`db.ConversationPaused` all `deny()` unconditionally at that switch, an
owner-facing action (`send_owner_summary` / `request_owner_approval`) is
denied before `Evaluate` ever reaches the branch that is supposed to always
allow it (line 327-328: `case db.ActionTypeOwnerSummary,
db.ActionTypeOwnerApproval: return Result{Decision: Allow, ...}`).

The conversation-state gate exists to enforce "the agent must not reply to
the recruiter on my behalf right now" (`db.ConversationTakenOver`'s own
comment in `internal/db/agent_domain.go:38`: "owner replied in-thread; agent
must stay silent"). It does not mean "stop telling me things arrived." Those
are two different instructions, and today only the first one is honored:
once a conversation is taken over, paused, or closed, the owner stops
receiving summaries and approval requests about it too, with no error, no
retry, and no visible signal that anything was suppressed (the job that
tried to notify them still reports `outcome=completed`, per
`internal/agentworker/worker.go:127-130`, because a denied `agent_actions`
row satisfies `POST /jobs/{id}/complete`'s "exact persisted result id"
requirement just as well as an executed one).

This was observed on real traffic on 2026-09-01: a recruiter's job offer
arrived in a conversation the owner had taken over the previous day
(`internal/agent/listener/listener.go:323`), the worker ran and reported
success, and nothing was ever delivered to the owner — no reply (correct)
and no draft-for-approval or FYI in Saved Messages (incorrect). The owner
only found out by reading the dialog by hand.

The fix is a reordering inside `Evaluate`: owner-facing action types must
clear the account-wide gates (global kill switch, `Mode == off`,
`AutopilotPaused`) but must short-circuit to `Allow` before the
per-conversation state switch, exactly as `internal/agentapi/actions.go`'s
`handleOwnerFacing` already assumes for the `ConversationID == 0` case (its
comment at lines 409-417 documents that `Evaluate` denies unrecognized
states, including the zero-value conversation's empty `State`, which is why
it currently has to synthesize `db.Conversation{State: db.ConversationActive}`
as a workaround). The workaround only covers callers with no conversation
row; a real, conversation-scoped notification — the common case, e.g. "the
recruiter you're talking to just sent an offer" — loads the actual row and
gets denied whenever that conversation is not active.

## User stories

- AS the account owner I WANT to still receive `send_owner_summary` and
  `request_owner_approval` notifications for a conversation I took over,
  paused, or closed SO THAT I never lose visibility into something that
  arrived just because I'm handling that thread myself or stepped away
  from it.
- AS the account owner I WANT the emergency kill switch, agent-off mode,
  and autopilot-pause to still silence owner-facing notifications SO THAT
  I retain one reliable way to go fully quiet across every account, not
  just per-thread.
- AS an operator debugging a dropped notification I WANT the policy
  decision that actually ran to be visible and correctly attributed SO
  THAT "denied because taken over" and "denied because kill switch" are
  distinguishable in the audit trail.

## Acceptance criteria (EARS)

- WHEN `Evaluate` receives an `Action.Type` of `db.ActionTypeOwnerSummary`
  or `db.ActionTypeOwnerApproval` and none of `GlobalKill`,
  `Profile.Mode == db.AgentModeOff`, an unrecognized `Profile.Mode`, or
  `Profile.AutopilotPaused` apply, THE SYSTEM SHALL return
  `Decision: Allow` regardless of `Conversation.State` (including
  `taken_over`, `paused`, `closed`, the zero-value empty string, or any
  other unrecognized value).
- WHILE `Conversation.State` is anything other than `db.ConversationActive`
  THE SYSTEM SHALL continue to deny `db.ActionTypeReply` actions exactly as
  today — this proposal changes ordering only for owner-facing action
  types, never the reply path.
- IF `GlobalKill` is true, OR `Profile.Mode` is `db.AgentModeOff` or
  unrecognized, OR `Profile.AutopilotPaused` is true, THEN THE SYSTEM SHALL
  deny owner-facing actions exactly as it denies every other action type
  today — these account-wide gates are not weakened by this change.
- WHEN `internal/agentapi/actions.go`'s `handleOwnerFacing` builds the
  `policy.Input` for a request with `ConversationID == 0`, THE SYSTEM SHALL
  no longer need to substitute a synthetic `State: db.ConversationActive`
  conversation to get an `Allow` decision, because the owner-facing
  short-circuit no longer depends on `Conversation.State` at all.
- WHEN a new `policy_test.go` case pins `taken_over` /
  `db.ConversationClosed` / `db.ConversationPaused` combined with
  `db.ActionTypeOwnerSummary` or `db.ActionTypeOwnerApproval`, THE SYSTEM
  SHALL evaluate to `Allow`.
- WHEN a new `policy_test.go` case pins `db.ConversationTakenOver` combined
  with `db.ActionTypeReply`, THE SYSTEM SHALL continue to evaluate to
  `Deny` (regression pin for the intentionally unchanged path).
- WHEN a new `policy_test.go` case pins `GlobalKill`, `Profile.Mode ==
  db.AgentModeOff`, or `Profile.AutopilotPaused` combined with an
  owner-facing action type, THE SYSTEM SHALL continue to evaluate to
  `Deny` (regression pin so the reorder cannot silently loosen the
  account-wide gates).

## Out of scope

- Changing anything about `GlobalKill`, `Mode == off`, or
  `AutopilotPaused` — these remain hard denials for every action type,
  owner-facing included, as documented in `actions.go:437-443`.
- Changing the reply path (`db.ActionTypeReply`) or its cross-user
  Profile/Conversation guard (`policy.go:296-299`) in any way.
- Fixing the job-outcome/observability gap described in the issue's "Why
  it was invisible" section (a denied-only job reporting
  `outcome=completed` in `internal/agentworker/worker.go:127-130`). That is
  a real, separate problem in the worker's completion/logging contract,
  not in `policy.Evaluate`'s decision logic, and deserves its own proposal
  so it can weigh trade-offs (e.g. changing what "completed" means for a
  job, versus adding a distinguishing log field) without being rushed
  through as a side effect of this fix.
- The `/mctl continue` workaround (`internal/agent/control/router.go:130-147`)
  and whether it should also be reachable programmatically — not
  mentioned as broken in the issue, and changing who can flip conversation
  state is a different, higher-trust-boundary question than this proposal.

## Open questions

- The issue's scope section calls out only the `Conversation.State` switch
  (`policy.go:310`) as the per-thread gate to fix, and only names
  `GlobalKill` / `Mode == off` / `AutopilotPaused` as the gates that must
  keep denying. It does not mention `isBlocked` (`policy.go:321-323`,
  keyed on `Profile.BlockedSenders` vs `Conversation.PeerTGID`), which
  today also runs before the owner-facing short-circuit. Moving the
  short-circuit "above the switch in.Conversation.State" as the issue's
  suggested fix literally describes necessarily also moves it above
  `isBlocked`, since `isBlocked` currently runs after that switch. Blocking
  a sender is a per-thread instruction ("don't let this person reach me"),
  not a global mute, so the same reasoning the issue applies to
  conversation state arguably applies here too: being told a blocked
  sender tried to contact you is still useful information. This proposal
  takes the literal reading of the suggested fix (owner-facing bypasses
  `isBlocked` as a direct consequence of the reorder) and adds an explicit
  regression test for it so the behavior is pinned and reviewable rather
  than an unnoticed side effect. If a reviewer disagrees, reordering
  `isBlocked` to run before the owner-facing short-circuit is a small,
  isolated follow-up change to the same function.
