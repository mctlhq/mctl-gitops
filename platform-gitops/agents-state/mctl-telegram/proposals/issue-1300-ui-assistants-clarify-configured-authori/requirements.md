# Clarify configured authority and assistant state in the assistant management UI

## Context

Issue #1300 follows research #1280 (merged spike PR #1292,
`docs/spikes/assistant-builder-ui-reference.md`). An account owner manages an
installed assistant in the server-rendered assistant section of the manage
page (`/telegram/connect/manage#assistant`, `internal/web/manage_assistant.go`).
Owners reach it from the `/assistants` catalog through the "Browse the
assistant catalog" link, and the catalog card links back to it. Today that
section prints the configured auto-send list as "Replies on its own: <intents>"
(`manage_assistant.go:445`) in every state. In `observe` mode, while paused,
with mode `off`, or in `guarded` mode on an unpromoted private fork, the
server's policy engine (`internal/agent/policy/policy.go`) never auto-sends
those intents. The page therefore shows saved configuration as if it were
effective autonomous behaviour. The spike calls this "the smallest honest
improvement" (§5.4, §9.1).

The change is presentation only. It relabels and groups data the page already
loads (`assistantinstall.Settings` and the installed assistant name) into
"configured to send without approval", "needs your approval" and "never sent".
It derives a state label (off, paused, not listening, observing, guarded) from
the stored mode, paused and listening flags. It also says plainly that the page
shows saved configuration and cannot verify runtime or listener health or the
platform kill switch. No API, policy, permission, handler or schema changes.

## User stories

- AS an account owner I WANT the assistant section to say whether my assistant
  can currently send anything on its own SO THAT I do not believe it is
  replying autonomously while it is observing, paused or off.
- AS an account owner I WANT my configured auto-send, approval-required and
  never-sent intents shown under explicit, conditional labels SO THAT I can
  review my configuration without mistaking it for a guarantee.
- AS an account owner I WANT the page to say what it cannot verify (whether a
  worker or listener is running, the kill switch) SO THAT missing evidence is
  not shown as healthy.
- AS a maintainer I WANT deterministic rendering tests that fail if the old
  "Replies on its own" presentation comes back SO THAT the honesty gap cannot
  return unnoticed.

## Acceptance criteria (EARS)

State label (one primary label, highest precedence first: off, paused, not
listening, observing, guarded):

- WHEN an installed assistant's stored mode is `off` THE SYSTEM SHALL render
  the state label "Off" with text saying the assistant sends nothing.
- WHEN the stored mode is not `off` AND `Settings.Paused` is true THE SYSTEM
  SHALL render the state label "Paused" with text saying replies are held back
  and not sent.
- WHEN the stored mode is not `off`, the assistant is not paused, AND
  `Settings.Listening` is false THE SYSTEM SHALL render the state label "Not
  listening" with text saying new messages are not picked up for the assistant.
- WHEN the stored mode is `observe` and neither of the above applies THE
  SYSTEM SHALL render the state label "Observing" with text saying every reply
  waits for the owner's approval.
- WHEN the stored mode is `guarded`, unpaused and listening THE SYSTEM SHALL
  render the state label "Guarded".
- IF the stored mode is not one of `observe`, `guarded` or `off` THEN THE
  SYSTEM SHALL render the state label "Unrecognized mode" with text saying
  policy refuses every reply. This mirrors `DenyModeUnrecognized`.
- THE SYSTEM SHALL always render the state as visible text, never as colour
  alone.

Configured authority:

- WHILE the effective state is anything other than Guarded on a non-fork
  assistant THE SYSTEM SHALL render the "Sends without your approval" row as
  "none" followed by the reason (mode off, paused, listening off, observe mode,
  unrecognized mode). It SHALL NOT render any configured auto-send intent in
  that row.
- WHILE the state is Guarded on a non-fork assistant with a non-empty
  `AutoIntents` THE SYSTEM SHALL list those intents in the "Sends without your
  approval" row. The row SHALL carry conditional wording saying this applies
  only when no hold listed under "Needs your approval" applies, and SHALL NOT
  use the word "allowed".
- WHILE the state is Guarded and the installed assistant is a private fork
  (`db.IsForkAssistant`) THE SYSTEM SHALL render the "Sends without your
  approval" value as "unknown". The text SHALL say that auto-send also depends
  on fork promotion, which this page does not show.
- THE SYSTEM SHALL render the configured auto-send list (`AutoIntents`, or
  "none") in its own row labelled "Auto-send list (saved setting)", together
  with the condition under which it is used (guarded mode, unpaused, listening).
- WHILE the state is Observing or Guarded THE SYSTEM SHALL render a "Needs your
  approval" row. The row SHALL say every reply not covered above needs approval,
  and SHALL list the hold reasons using the wording of
  `policy.OwnerHoldReasons` for `ReasonObserveMode` (observe only),
  `ReasonTurnBudget`, `ReasonIntentNotAllowed`, `ReasonRateLimit`,
  `ReasonWorkingHours` and `ReasonScheduleUnreadable`.
- WHILE the state is Off, Paused or Unrecognized mode THE SYSTEM SHALL render
  the "Needs your approval" row as saying replies are held back and not queued
  for approval. It SHALL NOT list hold reasons.
- THE SYSTEM SHALL render `NeverIntents` (or "none") under a "Never sent" row
  saying that approval cannot release these. The row SHALL also carry a fixed,
  static note that platform rules (kill switch, a changed install revision,
  blocked senders, excluded audience, links and credential-like content) can
  also stop a reply.
- THE SYSTEM SHALL render a fixed "Not verified here" note. The note SHALL say
  the section shows saved configuration and cannot confirm that a listener or
  worker is running, or whether the platform kill switch is on.
- THE SYSTEM SHALL keep the existing `Paused` and `Listening` rows, with ids
  `assistant-paused` and `assistant-listening` and yes/no values, labelled as
  saved settings. They SHALL NOT be presented as live runtime status.

Unavailable and empty data:

- IF the install cannot be read (`LoadErr`) THEN THE SYSTEM SHALL render the
  existing `assistant-unknown` message and no authority block.
- IF an install exists but `Settings` is nil THEN THE SYSTEM SHALL render
  "Configured authority is unavailable" and no state label, and SHALL NOT
  imply any authority.
- WHEN no assistant is installed THE SYSTEM SHALL render the existing
  `assistant-none` text and no authority block.

Preservation:

- THE SYSTEM SHALL keep every existing form (pause, listening, mode, runtime,
  install): its action, its hidden fields (including `expected_revision`) and
  its handler unchanged.
- THE SYSTEM SHALL render the authority block with no form controls and no
  `script` element. The response Content-Security-Policy SHALL stay unchanged,
  and the page SHALL keep working without JavaScript.
- THE SYSTEM SHALL HTML-escape every intent name and every other dynamic value
  in the new block through `html/template` contextual escaping.
- THE SYSTEM SHALL continue to omit install values, owner notes and
  instructions (existing `assertNoAssistantLeak` guarantee).
- WHEN the public catalog page `/assistants` renders a card's tier digest THE
  SYSTEM SHALL prefix it with "Default tiers:", so that catalog defaults are not
  read as the owner's configured authority.

## Out of scope

- Any change to `policy.Evaluate`, `assistantinstall` services, MCP tools,
  REST/agent APIs, schemas, store/migrations, permissions (`account:manage`),
  activation, approval, revision fencing or any POST handler.
- New backend fields or APIs: live listener or worker health, kill-switch
  status, fork promotion state, effective per-intent decision preview or
  simulator.
- New pages, a builder or Studio, a framework migration, client-side
  JavaScript, or new dependencies.
- Changes to the Telegram `/mctl assistant` text (`internal/agent/control/router.go`).
- Live Telegram sends, runtime activation, release or deployment. The release
  happens through the normal release-please flow after merge and is not part of
  this proposal.

## Open questions

- Not listening: `policy.Evaluate` does not check `ListenerEnabled`. A job
  created before listening was turned off may, in principle, still reach
  policy. The proposal phrases the state as "new messages are not picked up"
  and shows "none for new messages" rather than claiming that nothing can be
  sent. A reviewer should confirm this wording against
  `internal/agent/listener/supervisor.go`.
- Approval while not listening: the spike notes that `/mctl approve` is read by
  the account listener and that this failure mode was not verified. The
  proposal makes no claim about it.
- Kill switch and fork promotion are not available to the web layer. The
  proposal states them as "not verified here" or "unknown" rather than adding
  a field. Showing them as real values would need a separate decision, because
  it needs a new backend read.
- Precedence: when several states apply (for example observe + paused + not
  listening), one primary label is shown in the order off > paused > not
  listening > observing > guarded, and the raw saved rows still show every
  flag. If reviewers prefer listing every applicable state instead, only the
  template changes.
