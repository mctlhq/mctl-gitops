# Bind Telegram threads to canonical WorkItem and resume flow

## Context

Today `mctl-telegram` is the sole owner of every piece of investigation state
it touches. The only "thread" abstraction in the codebase is the
communication agent's `conversations` table (`internal/db/agent_domain.go`),
and the only command surface is the owner's private Saved Messages self-chat,
parsed by `internal/agent/control.Router` (`/mctl status|leads|show|continue|
pause|takeover|approve|reject`). Nothing in this repo talks to another mctl
service over HTTP for anything resembling work/task state; the closest
existing pattern is `internal/agentworker.Client`, a bearer-token HTTP client
this process's own worker uses to call back into `mctl-telegram`'s own
`/api/agent/v1` — not a client of an external platform API.

Issue #443 (part of roadmap `mctlhq/.github#21`) asks `mctl-telegram` to stop
being an owner of investigation state and become a surface adapter: a
Telegram interaction should create or open a canonical `WorkItem` (owned by
`mctl-api`, see `mctlhq/mctl-api#227`) and start/continue an investigator
execution (owned by `mctl-agents`, see `mctlhq/mctl-agents#267`), while
`mctl-telegram` persists only a minimal correlation between the Telegram
surface (chat/thread/message) and the canonical work reference. The pilot is
the investigator workflow itself — the same class of agent run that produces
proposals like this one — with acceptance demonstrated by starting work from
Telegram and resuming/inspecting it from a second surface (CLI/MCP or web)
without replaying Telegram history.

This matters because the communication agent already proved that
Telegram-side ad hoc state (approval codes, conversation rows, job leads)
does not generalize to other work types and does not travel to other
surfaces. Binding to a canonical WorkItem is the mechanism that lets a piece
of work started by tapping a phone be continued from a laptop.

## User stories

- AS the account owner I WANT to start an investigator run by typing a
  command in my Telegram Saved Messages SO THAT I do not have to open a
  terminal or a web console to kick off work.
- AS the account owner I WANT a stable, shareable work/execution reference
  returned in the Telegram reply SO THAT I can hand it to a teammate or open
  it from another surface later.
- AS the account owner I WANT repeating the same Telegram command to reopen
  my existing work instead of creating a duplicate SO THAT I don't end up
  with fragmented, parallel investigations for the same topic.
- AS the account owner I WANT to see pending-approval or result state for my
  work item surfaced in Telegram SO THAT I don't have to switch surfaces just
  to check status, without the bot inventing its own approval semantics.
- AS a platform operator I WANT Telegram's authorization to stay bound to the
  existing Telegram identity/auth boundary SO THAT reachability over
  Telegram never implies platform authorization it hasn't been granted.
- AS an existing communication-agent user I WANT my current `/mctl` commands
  to keep working unchanged SO THAT this rollout does not regress leads,
  approvals, or takeover flows I already depend on.

## Acceptance criteria (EARS)

- WHEN the owner sends a recognized "start/open work" command in their
  primary Saved Messages dialog THE SYSTEM SHALL create or open a canonical
  WorkItem via the platform contract and reply with a stable work/execution
  reference.
- WHEN a WorkItem is created or opened from Telegram THE SYSTEM SHALL persist
  only a minimal correlation record (Telegram chat id, saved-peer/thread id,
  triggering message id, WorkItem id, execution id) — never the full message
  transcript as canonical task state.
- WHEN starting an investigator execution from Telegram THE SYSTEM SHALL pass
  actor identity (the Telegram-derived subject already used for MCP auth,
  e.g. `tg:<telegram_id>`), surface (`telegram`), and work-item metadata into
  the platform contract call.
- IF the owner repeats the same start command for a Telegram thread that
  already has an open, non-terminal WorkItem THEN THE SYSTEM SHALL resolve
  to the existing WorkItem/execution instead of creating a new one.
- WHEN a duplicate Telegram delivery of the same triggering message is
  processed (retry, reconnect, at-least-once redelivery) THE SYSTEM SHALL NOT
  create a second WorkItem or a second execution for it.
- WHEN the platform reports pending-approval or result state for a bound
  WorkItem THE SYSTEM SHALL render that state to the owner in Telegram
  without evaluating or storing its own approval decision for it.
- IF a second supported surface (CLI/MCP or web) opens the same WorkItem id
  THEN THE SYSTEM SHALL NOT require any Telegram-side data to resume or
  inspect that work — the correlation record is surface metadata only, not a
  dependency for the canonical resume path.
- WHILE the platform-side WorkItem/execution contract (`mctl-api#227`,
  `mctl-agents#267`) is unavailable or not configured THE SYSTEM SHALL leave
  all existing `/mctl` communication-agent commands (status, leads, show,
  continue, pause, takeover, approve, reject) fully functional and SHALL
  fail the new work-context command with a clear, non-crashing message
  rather than a panic or silent no-op.
- IF an inbound Telegram message does not pass the existing owner-authored,
  primary-Saved-Messages gate (`internal/agent/listener.classifySavedCommand`)
  THEN THE SYSTEM SHALL NOT treat it as a work-context command, matching the
  existing trust boundary for all `/mctl` commands today.
- WHEN mctl-telegram calls the platform WorkItem/execution API THE SYSTEM
  SHALL treat a platform-side 401/403 as an authorization failure to surface
  to the owner, and SHALL NOT infer platform authorization from the fact
  that the Telegram message itself was successfully received and parsed.

## Out of scope

- Full chat synchronization or transcript replication with any other
  surface.
- Making `mctl-telegram` the WorkItem system of record, or duplicating
  `mctl-api`'s WorkItem schema locally beyond the minimal correlation row.
- Implementing the WorkItem/execution HTTP contract itself — that is
  `mctl-api#227` and `mctl-agents#267`; this proposal defines and consumes a
  narrow Go client interface against that contract and documents the
  assumptions it makes pending those APIs landing.
- Forum-topic-level threading for group chats. `mctl-telegram`'s only
  existing command surface is the owner's private Saved Messages dialog
  (self-chat); this proposal binds at that granularity (chat + Telegram
  "saved peer" sub-thread, see Design) and does not add group/channel
  command handling.
- Replacing or refactoring the existing communication-agent
  `conversations`/`agent_actions`/approval-code machinery. That system keeps
  working exactly as-is; work-context binding is additive.
- A second-surface UI. The proposal only guarantees the canonical API makes
  resume/inspect possible from elsewhere; building or changing a CLI/MCP/web
  client outside this repo is out of scope.

## Open questions

- The exact HTTP contract for `mctl-api#227` (WorkItem create/open/get
  endpoints, request/response shapes, idempotency-key semantics) and
  `mctl-agents#267` (how an investigator execution is started/resumed and
  how `ContextSnapshot` versions are exposed) are owned by other repos and
  were not available to read from this clone. This proposal defines the
  narrowest Go client interface (`workcontext.PlatformClient`) it needs and
  isolates all HTTP specifics behind it; the concrete implementation must be
  finalized once those issues land, likely as a follow-up PR in this repo.
- Whether "Telegram thread" for binding purposes should be
  (chat_tgid) alone or (chat_tgid, saved_peer_id) — Telegram's Saved
  Messages sub-threads (`GetSavedPeerID` in
  `internal/agent/listener/extract.go`) are the only sub-chat threading
  concept this codebase currently reads. This proposal binds at
  (user_id, chat_tgid, saved_peer_id) and treats a Saved Messages sub-thread
  as the "thread" the issue refers to, since group/forum topics are not
  read anywhere in the current MTProto handling. Revisit if `mctl-api#227`
  defines a different expected granularity.
- Whether the "start investigator work" Telegram command takes a free-text
  topic, a GitHub issue URL, or both. This proposal accepts either (a raw
  argument string forwarded verbatim as the WorkItem's opening description)
  and lets the platform side interpret it, since interpretation is
  explicitly a platform/agent concern, not a bot concern.
- Whether non-owner/group-chat entry points should ever bind WorkItems in a
  later iteration. Out of scope here; the existing owner-only Saved Messages
  gate is reused unchanged.
