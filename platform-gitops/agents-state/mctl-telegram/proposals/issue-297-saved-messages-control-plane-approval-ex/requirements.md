# Saved Messages Control Plane, Approval Executor, and Owner Profile (A-PR7)

## Context

Issue #297 is the third leg of the MCTL Communication Agent workstream
(plan: tranquil-sleeping-map), gated the same way every prior agent PR has
been — behind `AGENT_ENABLED` and, for sends, `AGENT_KILL_SWITCH`. The
listener (`internal/agent/listener`), policy engine
(`internal/agent/policy`), job queue (`internal/agent/queue`), and agent
HTTP surface (`internal/agentapi`) already exist and already anticipate this
work: `listener.Listener.Router` is a `CommandRouter` interface wired to
`nil` today (`cmd/server/main.go:93`), `agentapi.Server.Profile` is an
`OwnerProfileProvider` interface that 501s until wired
(`internal/agentapi/server.go:25-39`), and the `agent_actions` state machine
already documents `executing` as "deliberately a trap state on crash"
(`internal/db/agent_actions.go:36-40`) — the exact design this issue
revises.

This proposal turns those stubs into three real packages —
`internal/agent/control` (Saved Messages command parser + notifier),
`internal/agent/executor` (approved-action executor with crash-safe
dedup-by-`random_id` recovery), and `internal/agent/profile` (owner profile
provider) — so the owner can supervise and steer the agent entirely from
their own Saved Messages chat, with every autonomous send guaranteed
exactly-once even across a process crash mid-send.

## User stories

- AS the account owner I WANT to type `/mctl` commands into my own Saved
  Messages SO THAT I can check status, review leads, and control the agent
  without any other app or dashboard.
- AS the account owner I WANT approval requests that show the draft reply
  and a short code SO THAT I can approve or reject an autonomous send with
  one short reply.
- AS the account owner I WANT my own reply in a chat (or an explicit
  takeover) to immediately silence the agent in that conversation SO THAT
  the agent's draft never lands on top of or after what I already said.
- AS the platform operator I WANT an approved send to be delivered exactly
  once even if the process crashes mid-send SO THAT a recruiter never gets
  a duplicate message and the owner never has to manually unstick a row.
- AS the platform operator I WANT policy re-evaluated immediately before the
  RPC fires, not only at approval time, SO THAT a stale approval can never
  bypass a kill-switch flip, a new autopilot pause, or a rate limit that
  became true in the gap between approval and send.
- AS the account owner I WANT a restricted profile section that is never
  returned to the agent SO THAT sensitive answers (compensation floor,
  private notes) stay private even though the agent can describe my public
  background.

## Acceptance criteria (EARS)

### Command parsing (`internal/agent/control`)

- WHEN `ParseCommand` is given `/mctl status`, `/mctl leads`,
  `/mctl show <id>`, `/mctl continue <id>`, `/mctl pause`,
  `/mctl takeover <id>`, `/mctl approve <code>`, or `/mctl reject <code>`
  (any casing on `/mctl` and the verb, arbitrary surrounding/interior
  whitespace) THE SYSTEM SHALL return a structured command with the verb
  and argument, performing no I/O.
- IF the text does not start with `/mctl` (case-insensitive) THEN THE SYSTEM
  SHALL return a "not a command" result without error, distinct from a
  recognized-but-malformed command.
- IF the verb is unrecognized, or a verb requiring an argument
  (`show`/`continue`/`takeover`/`approve`/`reject`) is missing one, THEN THE
  SYSTEM SHALL return a parse error that identifies the problem, and never
  panic on malformed input (empty string, only whitespace, extra
  arguments).
- WHILE approval codes are matched case-sensitively (per
  `internal/agentapi/approvalcode.go`'s alphabet) THE SYSTEM SHALL pass
  `approve`/`reject` arguments through unchanged (no case-folding).

### Notifier (`internal/agent/control`)

- WHEN an owner-facing action (`send_owner_summary`,
  `request_owner_approval`) is enqueued as an `owner_notifications` row with
  `status=pending` THE SYSTEM SHALL deliver it to Saved Messages via
  `telegram.SendToSelf` (`InputPeerSelf`) and mark it `sent` with the
  resulting Telegram message id, or `failed`, per the existing
  compare-and-set semantics in `MarkOwnerNotificationSent`/
  `MarkOwnerNotificationFailed`.
- WHEN an approval request is formatted THE SYSTEM SHALL include the
  conversation summary, the full draft reply text, and literal
  `/mctl approve <code>` / `/mctl reject <code>` instruction lines.
- WHEN a `/mctl` command is handled THE SYSTEM SHALL send a short
  confirmation back to Saved Messages (e.g. "paused", "approved, sending
  shortly", "unknown command") so the owner has feedback that the command
  was received, exactly once per the listener's existing dedup (see
  design.md).

### Executor send flow and crash recovery (`internal/agent/executor`)

- WHEN an action is `approved` (owner-approved or guarded-mode
  auto-approved) THE SYSTEM SHALL, before issuing any send RPC, re-evaluate
  `policy.Evaluate` against a freshly loaded `AgentProfile` and
  `Conversation` (not the values captured at proposal or approval time).
- IF the re-evaluation returns anything other than `Allow` THE SYSTEM SHALL
  NOT send, and SHALL transition the action to `denied` recording the
  reasons, even though it was previously `approved`.
- WHEN the re-check passes THE SYSTEM SHALL generate a Telegram
  `random_id`, persist it on the action row, and only then compare-and-set
  the status to `executing` — in that order — before the send RPC is
  issued.
- WHEN the send RPC succeeds THE SYSTEM SHALL compare-and-set the action
  from `executing` to `executed`, record `executed_tg_message_id`,
  increment the conversation's autonomous-turn counter, and append an
  `agent_outgoing` conversation message.
- WHILE a row is found with `status=executing` (whether from a fresh
  approval this tick or a restart after a prior tick was interrupted) THE
  SYSTEM SHALL retry the identical send RPC using the SAME persisted
  `random_id`, relying on MTProto's dedup-by-`random_id` guarantee so the
  retry is safe whether or not the original send actually reached Telegram.
  `executing` SHALL be treated as a transient, self-healing state, never as
  a state requiring manual operator intervention.
- WHEN the outgoing text is assembled THE SYSTEM SHALL append the profile's
  `DisclosureText` using `policy.DisclosureSep` before the length check and
  before the send.
- WHEN a `pending_approval` action's `updated_at` is older than the
  approval TTL (`AGENT_APPROVAL_TTL`, default 24h) THE SYSTEM SHALL expire
  it via `ExpireStaleAgentActions` (already wired into
  `sweeper.AgentJobs`) and THE SYSTEM SHALL additionally notify the owner
  that the draft lapsed.

### Concurrent owner reply and edit/delete invalidation

- WHILE an action is `pending_approval` or `executing` for a conversation,
  IF the owner sends any message in that same Telegram chat (detected today
  by the listener's existing `EventKindOwnerOutgoing` handling, which flips
  `Conversation.State` to `taken_over` — see `listener.go:193-211`) THEN THE
  SYSTEM SHALL have its next policy re-check observe the `taken_over` state
  and deny the pending action rather than sending it.
- IF the owner issues `/mctl takeover <id>` THEN THE SYSTEM SHALL set that
  conversation to `taken_over` immediately (independent of any inbound
  Telegram echo), with the same denial effect on any pending/executing
  action for that conversation.
- IF the incoming message that a `pending_approval` (or earlier-stage)
  action's draft was derived from is edited or deleted before the action
  is sent THEN THE SYSTEM SHALL mark that action `denied` with a reason
  identifying the edit/delete, and SHALL NOT send the original draft
  unchanged. A new incoming event for the edited content re-enters the
  ordinary proposal pipeline as its own job.

### Action state machine and observability

- WHILE the action lifecycle is enforced THE SYSTEM SHALL route every
  status transition through `UpdateAgentActionStatus`'s compare-and-set (or
  a narrowly-scoped dedicated method, matching the existing precedent of
  `SetAgentActionExecuted`/`ExpireStaleAgentActions`), never a bare `UPDATE`.
- WHEN an action has sat in `executing` past a grace window (materially
  longer than one executor tick) THE SYSTEM SHALL count it in an
  `executing_stuck` gauge — expected to stay at ~0 given retry-by-
  `random_id`; any sustained nonzero value is a real incident, not expected
  noise.
- WHEN an action moves `approved -> executed` THE SYSTEM SHALL record the
  approve-to-executed latency in an observable metric.
- WHEN an agent job dead-letters, or the executor process (re)starts, THE
  SYSTEM SHALL increment the existing/dedicated dead-letter and restart
  counters respectively.

### Owner profile (`internal/agent/profile`)

- WHEN `AGENT_PROFILE_PATH` points to a YAML file THE SYSTEM SHALL load
  `identity` / `public_profile` / `skills` / `preferences` / `restricted`
  sections at startup.
- WHILE serving the agent-facing surface (`GET /recruiters/{peer}` via
  `agentapi.OwnerProfileProvider.PublicProfile`) THE SYSTEM SHALL NEVER
  include any field from the `restricted` section, including fields marked
  `approval_required` or `never_auto_send`, regardless of future additions
  to that section.

### Safety and audit

- WHILE any communication-agent code logs, THE SYSTEM SHALL NOT log message
  bodies, drafts, approval codes, or profile restricted content — new
  sensitive field names introduced by this work (e.g. any raw-command or
  raw-draft log key) MUST be added to `internal/audit/redact.go`'s
  `sensitiveKeys`.
- WHEN any send, approval, denial, or expiry occurs THE SYSTEM SHALL audit
  it (matching the existing `s.audit(...)` convention in `agentapi`).

## Out of scope

- Implementing or modifying the `internal/agentapi` HTTP surface itself
  (propose_reply, request_owner_approval, etc.) — that is #296 and is a
  precondition, not part of this work.
- Multi-owner accounts, group-chat approvals, or any peer type other than
  private users (v1 conversations are user-only per `db.Conversation`'s
  doc comment).
- A UI/dashboard for approvals — Saved Messages is the only control
  surface in this proposal.
- The Local Bridge / Channels bridge alternative transport.
- PR9's privacy/retention documentation update (explicitly deferred by the
  issue to "Note for PR 9"), though this proposal's design section records
  what that PR will need to describe.
- Hot-reloading the owner profile YAML on file change (load-at-startup is
  in scope; a reload endpoint/watch is not).
- Rate-limiting or throttling `/mctl` commands themselves (the existing
  per-message dedup via `incoming_events`/`EventKindSavedCommand` is relied
  on as-is).

## Open questions

- The issue lists `show <id>` under the same family as `continue`/
  `takeover <id>`. This proposal interprets `<id>` uniformly as a
  conversation id in all three (not a job id or lead id), since
  conversations are the only entity the owner naturally references by a
  small number from a `status` listing. Proceeding on that interpretation.
- Whether `/mctl continue <id>` should also call `ResetAutonomousTurns` in
  addition to `SetConversationState(active)`. The existing method's doc
  comment ("called when the owner takes over or explicitly continues a
  conversation, granting the agent a fresh budget") directly supports yes;
  proceeding with both calls.
- Message-delete detection requires a new `tg.UpdateDeleteMessages`
  dispatcher hook that does not exist yet in
  `internal/agent/listener/listener.go` (today only `OnNewMessage`/
  `OnEditMessage` are wired). This proposal treats that listener addition
  as an in-scope, load-bearing dependency of the executor's edit/delete
  invalidation requirement even though the issue nominally scopes only
  `internal/agent/control`/`executor`/`profile` — see design.md and
  tasks.md. Proceeding with the minimal addition rather than deferring the
  requirement.
- Exact wording/format of the Saved Messages confirmation replies (e.g.
  "paused" vs. a fuller sentence) is left to implementation; the
  requirement is that some confirmation is always sent, not its exact copy.
- Whether guarded-mode auto-approved actions (`policy.Allow` at propose
  time, status inserted directly as `approved`, no owner approval step) go
  through the same executor loop as owner-approved ones. This proposal
  assumes yes — one executor loop handles every `approved`/`executing` row
  regardless of how it got there, since the re-check-before-send
  requirement applies equally to both origins.
- Whether the executor runs as a poll loop (matching the existing
  `sweeper.AgentJobs` ticker style) or is triggered eagerly on approval for
  lower latency. This proposal chooses the poll loop for consistency with
  the rest of the codebase's sweeper pattern; approval latency becomes an
  observable metric precisely because of this choice, per the issue's own
  observability ask.
