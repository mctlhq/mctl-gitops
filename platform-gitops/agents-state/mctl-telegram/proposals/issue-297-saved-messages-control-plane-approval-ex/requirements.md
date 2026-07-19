# Saved Messages control plane, approval executor, and owner profile

## Context
The communication agent (MCTL Communication Agent workstream, plan
`tranquil-sleeping-map`) drafts replies to recruiter conversations on the
owner's behalf but must never send anything without a human in the loop
unless explicitly allowlisted. Prior work (#286/#288/#289/#290) built the
storage layer for this: `agent_profiles`, `conversations`,
`conversation_messages`, `agent_actions`, `owner_notifications`, and
`incoming_events` (see `internal/db/agent_domain.go`,
`internal/db/agent_actions.go`, `internal/db/agent_events.go`,
`internal/db/agent_schema.go`), plus a pinned-connection listener runtime
hook (`internal/telegram/agentruntime.go`, `internal/telegram/clientpool.go`)
and a Saved-Messages-only send primitive (`internal/telegram/sendself.go:
SendToSelf`). Issue #296 adds the agent's HTTP/MCP API surface that shares
the action/notification flow with this issue.

This issue is the piece that makes the owner able to see and steer what the
agent is doing without a web UI: typing commands into their own Telegram
"Saved Messages" chat. It also supplies the executor that turns an
`approved` `agent_actions` row into an actual Telegram send (and only that),
and the profile provider that hands the agent a bounded, non-sensitive view
of who the owner is and how they want to be represented. Without this, an
approved draft has no path to delivery, and the owner has no low-friction
control surface (pause / take over / approve / reject) that works from their
phone.

## User stories
- AS the Telegram account owner I WANT to type `/mctl` commands into my own
  Saved Messages chat SO THAT I can check on, pause, and steer the
  communication agent without any other app or UI.
- AS the Telegram account owner I WANT approval requests delivered to Saved
  Messages with a summary, the draft reply, and a short approve/reject code
  SO THAT I can review and decide from my phone in a few seconds.
- AS the Telegram account owner I WANT an approved reply to be sent exactly
  once, to the exact conversation I approved, even across a crash or restart
  SO THAT I never end up with a duplicate or misdirected message to a
  recruiter.
- AS the platform operator I WANT the agent's send path to re-check the kill
  switch, profile mode, and conversation state at execution time (not only
  at proposal time) SO THAT a global stop or a mid-flight pause takes effect
  even for actions that were already approved.
- AS the account owner I WANT to control what the agent knows about me via a
  single YAML file SO THAT I can edit my public profile, skills, and
  preferences without redeploying, while restricted personal fields never
  leave my control.

## Acceptance criteria (EARS)
- WHEN the owner sends a Saved Messages text starting with `/mctl` THE
  SYSTEM SHALL parse it with `ParseCommand` into one of: `status`, `leads`,
  `show <id>`, `continue <id>`, `pause`, `takeover <id>`, `approve <code>`,
  `reject <code>`, or a parse error, as a pure function with no I/O.
- WHEN `ParseCommand` receives unrecognised input or malformed arguments
  (missing/non-numeric id, missing code) THE SYSTEM SHALL return a
  structured parse error and SHALL NOT panic.
- WHEN the agent proposes a reply that requires approval THE SYSTEM SHALL
  send an approval request to Saved Messages containing: a summary of the
  conversation/intent, the full draft reply text, and both
  `/mctl approve <code>` and `/mctl reject <code>` instructions, via
  `internal/telegram.SendToSelf`.
- WHEN a periodic sweep runs THE SYSTEM SHALL call
  `Store.ExpireStaleAgentActions` with a 24h TTL and move
  `pending_approval` rows older than the TTL to `expired`.
- WHEN the owner sends `/mctl approve <code>` THE SYSTEM SHALL look up the
  action by `(user_id, code)`, and IF found and in `pending_approval` THEN
  THE SYSTEM SHALL CAS it to `approved` via `UpdateAgentActionStatus`; IF the
  code does not resolve to a `pending_approval` action for that owner THEN
  THE SYSTEM SHALL reply in Saved Messages that the code is invalid or
  already resolved, without mutating any row.
- WHEN the executor picks up an `approved` action THE SYSTEM SHALL, in
  order: (1) re-check the global kill switch (`AGENT_KILL_SWITCH`), (2)
  re-check the owner's profile mode and `autopilot_paused` flag, (3)
  re-check the target conversation's state, (4) CAS the action from
  `approved` to `executing`, (5) send via the conversation's stored peer
  only (never a peer derived from the action payload or model output), (6)
  on send success CAS `executing` to `executed` via `SetAgentActionExecuted`
  with the resulting Telegram message id.
- IF any of the kill-switch, profile-mode, or conversation-state re-checks
  fails at execution time THEN THE SYSTEM SHALL NOT transition the action
  out of `approved` and SHALL record the reason (policy_reasons / audit log)
  without sending anything.
- WHILE an action is in `executing` THE SYSTEM SHALL NOT auto-retry it from
  that state under any circumstance (crash, timeout, panic recovery) — a row
  stuck in `executing` SHALL be left for manual/operator inspection only.
- WHEN the executor sends an approved reply THE SYSTEM SHALL append the
  profile's disclosure line, separated by `policy.DisclosureSep`, before the
  text leaves the process.
- WHEN a status transition on `agent_actions` is requested THE SYSTEM SHALL
  route it exclusively through `Store.UpdateAgentActionStatus` /
  `SetAgentActionExecuted` / `ExpireStaleAgentActions` so every transition is
  checked against `allowedActionTransitions` — no package in this proposal
  SHALL write `agent_actions.status` via raw SQL.
- WHEN `OwnerProfileProvider` loads the file at `AGENT_PROFILE_PATH` THE
  SYSTEM SHALL parse identity / public_profile / skills / preferences /
  restricted sections from YAML.
- WHEN any agent-surface code (control-plane responses, executor context
  passed to the reply generator, MCP tool output) reads the profile THE
  SYSTEM SHALL NOT include fields from the `restricted` section, regardless
  of caller.
- IF a restricted field is marked `approval_required` or `never_auto_send`
  THEN THE SYSTEM SHALL treat any generated content that would disclose it
  as requiring the standard approval flow (never eligible for guarded-mode
  auto-send), enforced structurally by never surfacing the value in the
  first place.
- WHEN `AGENT_ENABLED` is false or unset THE SYSTEM SHALL NOT parse Saved
  Messages commands, NOT run the executor loop, and NOT load the profile
  file — all three packages are inert.
- WHEN any of the three packages logs THE SYSTEM SHALL NOT include message
  bodies, draft text, approval codes, or restricted profile fields as raw
  log attributes (relying on / extending `internal/audit/redact.go`'s
  `sensitiveKeys`).
- WHEN a Saved Messages send (owner summary, approval request, or executed
  reply) completes or fails THE SYSTEM SHALL be recorded for audit purposes
  (existing audit/notification tables), independent of the MCP-tool audit
  path.

## Out of scope
- The listener/dispatcher that turns raw Telegram updates into
  `incoming_events` rows and detects `EventKindSavedCommand` (already
  scaffolded via `AgentRuntime` in `internal/telegram/agentruntime.go`) —
  this proposal assumes that dispatch exists and calls into
  `internal/agent/control.ParseCommand` / the notifier, but does not build
  the update-handler wiring itself.
- The policy engine that decides `allow` / `require_approval` / `deny` for a
  freshly proposed action, and the reply-drafting/LLM logic that produces
  action payloads (part of the agent API surface, #296, and the reply
  generation work referenced by the wider workstream).
- The `/mctl status`/`leads`/`show` response *content* beyond what the
  parser and notifier need to format a Saved Messages reply — the richer
  MCP-facing read APIs belong to #296.
- Any web/HTTP UI for approvals; Saved Messages is the only control surface
  in this proposal.
- Rate limiting / flood-wait handling for the executor's send call beyond
  reusing the existing `internal/telegram` primitives — no new retry policy
  is introduced (see `AgentActions` state machine: `executing` never
  auto-retries).
- Editing or hot-reloading the owner profile file at runtime beyond a simple
  re-read (no watcher/webhook is specified).

## Open questions
- Exact Go type/package that exposes `AGENT_KILL_SWITCH` and
  `AGENT_ENABLED` (a `config.Config` field like `AgentRetentionDays`, or a
  dedicated `internal/agent/policy` accessor introduced by #296) is not yet
  in the codebase. This proposal assumes `internal/config.Config` gains
  `AgentEnabled bool` / `AgentKillSwitch bool` fields following the existing
  `envBool` convention, and that #296 either introduces or reuses that same
  field — proceeding with that interpretation; the implementer should
  reconcile with whatever #296 actually lands.
- `policy.DisclosureSep` is named in the issue but no `internal/agent/policy`
  package exists yet in this clone. This proposal assumes #296 introduces
  `internal/agent/policy` with at least `DisclosureSep string` (a plain
  constant, e.g. `"\n\n---\n"`) and that this issue's executor imports it
  rather than redefining it. If #296 lands without it, the executor package
  should define it locally and it can be hoisted into `policy` later.
- The exact wire format of `/mctl status` and `/mctl leads` output (which
  fields, how many leads) is not specified by the issue. This proposal
  defines a minimal, useful summary (counts + most recent items) and leaves
  richer formatting to be tuned post-merge.
- Approval code generation (length, alphabet, collision handling against the
  partial unique index `idx_agent_actions_code`) is not specified. This
  proposal uses a short (6-char) unambiguous base32-style code generated at
  the point an action transitions to `pending_approval`, with a regenerate-
  on-collision retry, matching the "short code the owner types" description
  in `internal/db/agent_actions.go`.
- Multi-conversation disambiguation: if the owner has more than one
  conversation pending approval and only sends `/mctl approve <code>`, the
  code alone is sufficient (codes are unique per user among non-terminal
  actions), so no additional disambiguation is required — recorded here so
  the design does not need a "which conversation" prompt.
- None beyond the above; where the issue is silent this proposal proceeds
  with the most conservative (approval-required, no-auto-send) reading.
