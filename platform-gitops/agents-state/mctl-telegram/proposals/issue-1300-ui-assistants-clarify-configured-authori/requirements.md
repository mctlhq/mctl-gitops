# Clarify configured authority and assistant state in the assistant management UI

Status: proposed. Owner approval is required before any implementation.

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
reply policy (`internal/agent/policy/policy.go`) does not auto-send those
intents. The page therefore shows saved configuration as if it were effective
autonomous behaviour. The spike calls this "the smallest honest improvement"
(§5.4, §9.1).

The change is presentation only. It relabels and groups data the page already
loads (`assistantinstall.Settings` and the installed assistant name) into
"configured to send without approval", "needs your approval" and "never sent",
each marked as a saved setting with its conditions. It derives a display label
(off, unrecognized, paused, not listening, observing, guarded) from the stored
mode, paused and listening flags. It also says plainly that the page shows
saved configuration and cannot verify effective authority, runtime or listener
health, or the platform kill switch. No API, policy, permission, handler or
schema changes.

## Terms used below

Three kinds of information are kept apart. Copy and tests must not blur them.

- **Known configured state**: values stored in `assistantinstall.Settings`
  (mode, paused, listening, auto/never intents, limits). The page knows these.
  They are settings, not runtime health.
- **Unavailable data**: the data could not be loaded (`LoadErr`) or `Settings`
  is nil. The page shows an unavailable message and implies no authority.
- **Unobservable effective authority**: what the system would actually do for a
  given action. It depends on inputs the page does not read (fork promotion,
  kill switch, listener or worker state, queued jobs, per-action inputs). The
  page says "unknown" or "not verified here" and never fills the gap with a
  guess.

The display label precedence below is **presentation precedence only**. It
decides which single label is shown first. It is not a new policy contract and
does not replace `policy.Evaluate`.

## User stories

- AS an account owner I WANT the assistant section to show what my saved
  settings say about sending on its own, under conditions, SO THAT I do not
  mistake saved configuration for autonomous behaviour while the assistant is
  observing, paused or off.
- AS an account owner I WANT my configured auto-send, approval-required and
  never-sent intents shown under explicit, conditional labels SO THAT I can
  review my configuration without mistaking it for a guarantee.
- AS an account owner I WANT the page to say what it cannot verify (effective
  permission, whether a worker or listener is running, the kill switch, fork
  promotion) SO THAT missing evidence is not shown as healthy.
- AS a maintainer I WANT deterministic rendering tests, including mixed-state
  cases and a restore-the-bug mutation check, SO THAT the honesty gap cannot
  return unnoticed.

## Acceptance criteria (EARS)

Display label (one primary label, highest precedence first: off, unrecognized,
paused, not listening, observing, guarded):

- WHEN an installed assistant's stored mode is `off` THE SYSTEM SHALL render
  the label "Off" with text saying that, per saved settings, replies are not
  sent.
- ELSE IF the stored mode is not one of `observe`, `guarded` or `off` THE
  SYSTEM SHALL render the label "Unrecognized mode" with text saying reply
  policy refuses replies for an unrecognized mode. This mirrors
  `DenyModeUnrecognized`.
- ELSE IF `Settings.Paused` is true THE SYSTEM SHALL render the label
  "Paused" with text saying that, per saved settings, replies are held back and
  not sent.
- ELSE IF `Settings.Listening` is false THE SYSTEM SHALL render the label "Not
  listening" with text saying that listening is switched off in saved settings,
  so new messages are not configured to be picked up. The text SHALL say this
  describes configured intake and is not proof that no already-queued action
  can send.
- ELSE IF the stored mode is `observe` THE SYSTEM SHALL render the label
  "Observing" with text saying every reply waits for the owner's approval.
- ELSE (mode `guarded`, unpaused, listening) THE SYSTEM SHALL render the label
  "Guarded".
- WHEN several conditions hold at once (for example `observe` + paused + not
  listening, or an unrecognized mode + paused) THE SYSTEM SHALL show only the
  highest-precedence label as primary, and the saved Paused and Listening rows
  SHALL still show every stored flag.
- THE SYSTEM SHALL always render the label as visible text, never as colour
  alone.
- THE SYSTEM SHALL NOT present the label as runtime health. Saved settings are
  not runtime health.

Configured authority (known configured state, shown with conditions):

- THE SYSTEM SHALL NOT render any config-derived row, value or label (including
  the helper field that feeds the "without approval" row) in wording that
  implies a verified effective permission or a send guarantee. Rows SHALL be
  labelled as saved settings and SHALL state their conditions, and a separate
  "Not verified here" note SHALL say the effective result is not verified.
- WHEN the display label is anything other than Guarded THE SYSTEM SHALL render
  the "Configured to send without approval (saved setting)" row as "None under
  saved settings" followed by the reason (mode off, mode unrecognized, paused,
  listening off, observe mode). It SHALL NOT render any configured auto-send
  intent in that row. This wording is a statement about saved settings, not a
  claim that nothing can ever be sent.
- WHILE the label is Guarded on a non-fork assistant with a non-empty
  `AutoIntents` THE SYSTEM SHALL list those intents in the "Configured to send
  without approval (saved setting)" row. The row SHALL carry conditional wording
  saying the saved setting applies only in guarded mode, unpaused and
  listening, and only when no hold condition listed under "Needs your approval"
  applies, and SHALL say the effective result is not verified here. It SHALL NOT
  use the word "allowed".
- WHILE the label is Guarded on a non-fork assistant with an empty
  `AutoIntents` THE SYSTEM SHALL render "None under saved settings" in that
  row.
- WHILE the label is Guarded and the installed assistant is a private fork
  (`db.IsForkAssistant`) THE SYSTEM SHALL render the row value as "unknown".
  The text SHALL say that auto-send also depends on fork promotion, which this
  page does not show. This is an unobservable-authority case and SHALL NOT be
  rendered as "none" or as a list. The conditional promotion unknown SHALL be
  preserved.
- THE SYSTEM SHALL render the configured auto-send list (`AutoIntents`, or
  "none") in its own row labelled "Auto-send list (saved setting)", together
  with the condition under which it is used (guarded mode, unpaused,
  listening).
- WHEN the stored mode is `observe` or `guarded` and the assistant is not
  paused THE SYSTEM SHALL render a "Needs your approval" row. The row SHALL say
  that, per saved settings, a reply not covered by the auto-send row needs
  approval when a hold condition applies. It SHALL list hold conditions as
  illustrative, policy-derived condition labels, introduced with wording such as
  "Conditions that can hold a reply (illustrative, not a current decision)". The
  list SHALL NOT claim that every listed hold is active now, nor that it is
  exhaustive. See "Hold condition labels" below.
- WHEN the stored mode is `off`, unrecognized, or the assistant is paused THE
  SYSTEM SHALL render the "Needs your approval" row as saying that, per saved
  settings, replies are held back and not sent, and that this page does not show
  whether anything is queued. It SHALL NOT list hold conditions and SHALL NOT
  state or imply that an approval queue is available.
- THE SYSTEM SHALL NOT infer whether the approval queue is available or
  reachable from listener configuration. Saved `Listening` says nothing about
  approvals, and the page makes no claim about approval while not listening.
- THE SYSTEM SHALL render `NeverIntents` (or "none") under a "Never sent
  (saved setting)" row saying that approval cannot release these. The row SHALL
  also carry a fixed, static note that platform rules (kill switch, a changed
  install revision, blocked senders, excluded audience, links and
  credential-like content) can also stop a reply.
- THE SYSTEM SHALL render a fixed "Not verified here" note. The note SHALL say
  the section shows saved configuration and cannot confirm effective
  permission, that a listener or worker is running, fork promotion, or whether
  the platform kill switch is on.
- THE SYSTEM SHALL scope the observe, paused and off statements to replies, the
  action that reply policy governs. It SHALL NOT claim that these states stop
  every kind of owner-facing action (alerts, notices, approvals).
- THE SYSTEM SHALL keep the existing `Paused` and `Listening` rows, with ids
  `assistant-paused` and `assistant-listening` and yes/no values, labelled as
  saved settings. They SHALL NOT be presented as live runtime status.

Hold condition labels:

- THE SYSTEM SHALL take hold-condition wording from `policy.OwnerHoldReasons`,
  using the same words as the Telegram approval notices, for each approval
  category that exists in the supplied policy source. The categories to review
  against source are: observe mode (observe only), turn budget, intent not on
  the allowlist, rate limit, working hours, unreadable working-hours schedule,
  and protected-field handling. The proposal does not name a constant for a
  category unless the supplied source names it.
- IF a category has no `policy.OwnerHoldReasons` wording in source THEN THE
  SYSTEM SHALL omit it from the page rather than invent text, and the
  implementer SHALL ask for a decision.
- THE SYSTEM SHALL pass only approval categories to the label list. Denial
  categories (paused, install changed, kill switch, never intent, mode off) are
  never listed as hold conditions.

Unavailable and empty data:

- IF the install cannot be read (`LoadErr`) THEN THE SYSTEM SHALL render the
  existing `assistant-unknown` message and no authority block.
- IF an install exists but `Settings` is nil THEN THE SYSTEM SHALL render
  "Configured authority is unavailable" and no display label, and SHALL NOT
  imply any authority.
- WHEN no assistant is installed THE SYSTEM SHALL render the existing
  `assistant-none` text and no authority block.
- THE SYSTEM SHALL NOT use a blanket "none" for cases where the answer is
  unavailable or unobservable. "None under saved settings" is used only where
  saved settings determine it; "unavailable" and "unknown" are used otherwise.

Preservation:

- THE SYSTEM SHALL keep every existing form (pause, listening, mode, runtime,
  install): its action, its hidden fields (including `expected_revision`),
  option values and its handler unchanged.
- THE SYSTEM SHALL render the authority block with no form controls and no
  `script` element. The response Content-Security-Policy SHALL stay unchanged,
  and the page SHALL keep working without JavaScript. The page SHALL stay
  readable at mobile width, using existing CSS classes only.
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
- New backend fields, APIs, policy, settings or grants: live listener or worker
  health, kill-switch status, fork promotion state, effective per-intent
  decision preview or simulator, a second policy evaluator, live reads.
- New pages, a builder or Studio, a framework migration, client-side
  JavaScript, or new dependencies.
- Changes to the Telegram `/mctl assistant` text (`internal/agent/control/router.go`).
- Live Telegram sends, runtime activation, releases, deploys or image changes.
  Releases and deploys are separately governed and are not part of this
  proposal or its approval.

## Open questions

- Not listening: `policy.Evaluate` does not check `ListenerEnabled`. A job
  created before listening was turned off may, in principle, still reach
  policy. Saved `listening=false` describes configured intake only. The
  proposal phrases it that way and does not claim that nothing can be sent. A
  reviewer should confirm this wording against
  `internal/agent/listener/supervisor.go`.
- Approval while not listening: the spike notes that `/mctl approve` is read by
  the account listener and that this failure mode was not verified. The
  proposal makes no claim about it.
- Kill switch and fork promotion are not available to the web layer. The
  proposal states them as "not verified here" or "unknown" rather than adding
  a field. Showing them as real values would need a separate decision, because
  it needs a new backend read.
- Hold condition categories: the list above comes from design review notes on
  `policy.go`. The exact `policy.OwnerHoldReasons` wording and the complete
  approval category list (including protected-field handling) are not available
  in this gitops checkout. Before implementation, the orchestrator or owner
  should supply the exact excerpts so the label list can be confirmed.
- Precedence: when several states apply, one primary label is shown (see
  "Display label"), and the raw saved rows still show every flag. If reviewers
  prefer listing every applicable state instead, only the template changes.
