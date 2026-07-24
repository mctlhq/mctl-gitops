# Saved Messages control plane, approval executor, and owner profile (A-PR7)

## Context

The communication agent (M6 workstream) already has a working spine: `internal/agent/listener`
turns live Telegram updates into durable `incoming_events` + `agent_jobs`, `internal/agentapi`
lets an external worker propose replies and request owner approval, `internal/agent/policy`
is the sole authority on what may auto-send, and `internal/db` already carries the
`agent_actions` / `agent_profiles` / `conversations` / `owner_notifications` tables with a
CAS-enforced action lifecycle. What is missing is the owner-facing control surface and the
component that actually turns an approved action into a sent Telegram message:

1. Nothing parses the owner's `/mctl ...` commands. `internal/agent/listener.Listener` already
   defines a `CommandRouter` interface and detects Saved-Messages commands
   (`extract.go:isMCTLCommand`), but `cmd/server/main.go:93` wires `listener.New(store,
   agentQueue, nil, m)` — the router argument is `nil`. Nothing sends the owner a summary or an
   approval request either (`internal/telegram/sendself.go:SendToSelf` exists but has no caller).
2. Nothing executes an `approved` action. `agent_actions.status` can reach `approved` (via
   `handleProposeReply`'s guarded-mode Allow path, or a future owner `/mctl approve`), but no code
   ever moves it past that point. The `executing` status and its doc comment
   (`internal/db/agent_actions.go:29-40`) currently describe it as a **dead trap state** — "nothing
   auto-retries from executing" — which the issue explicitly asks to replace with a self-healing,
   `random_id`-keyed retry.
3. Nothing implements `agentapi.OwnerProfileProvider`. `internal/agentapi/server.go:20-31` defines
   the interface and documents that `Server` runs with `Profile == nil` (returning 501 for
   `GET /recruiters/{peer}`) "until #297 wires a real implementation in."

This proposal designs the three packages that close these gaps — `internal/agent/control`,
`internal/agent/executor`, `internal/agent/profile` — plus the minimal, unavoidable extensions to
already-shipped packages (a `random_id` column, a couple of dedicated CAS store methods, a small
listener wiring change) that those three packages need in order to satisfy the issue's
crash-recovery and edit/delete-invalidation requirements. Getting this right matters because this
is the layer that turns a policy decision into an irreversible action on the owner's real Telegram
account — a bug here either silently drops an owner's approval or double-sends a message the owner
never actually approved twice.

## User stories

- AS the account owner I WANT to type `/mctl status`, `/mctl leads`, `/mctl show <id>`,
  `/mctl continue <id>`, `/mctl pause`, `/mctl takeover <id>`, `/mctl approve <code>`, and
  `/mctl reject <code>` into my own Saved Messages SO THAT I can supervise and control the
  communication agent from the same Telegram client I already use, without a separate app.
- AS the account owner I WANT an approval request in Saved Messages that shows the conversation
  summary, the exact draft reply, and the approve/reject code SO THAT I can make an informed
  yes/no decision without switching context.
- AS the account owner I WANT my kill switch flip, autopilot pause, conversation takeover, or a
  newly-tripped rate limit to still block a previously-approved send SO THAT approving a draft five
  minutes ago cannot bypass a guardrail I engaged since then.
- AS the account owner I WANT the executor to never send the same approved reply twice, even if the
  server crashes mid-send SO THAT a restart cannot double-message a recruiter.
- AS the account owner I WANT a draft invalidated if I edit or delete the message it was drafted
  from SO THAT the agent never sends a reply that answers something that no longer exists in the
  chat.
- AS the account owner I WANT my restricted profile fields (salary floor, visa status, etc.) to
  never appear in anything the agent-facing API returns SO THAT a compromised or misbehaving worker
  process cannot exfiltrate information I explicitly marked private.
- AS an operator I WANT metrics for stuck `executing` actions, approval latency, dead-lettered
  sends, and executor restarts SO THAT I can alert on the executor misbehaving instead of
  discovering it from an owner complaint.

## Acceptance criteria (EARS)

### Command parsing (`internal/agent/control`)
- WHEN `ParseCommand` is given a string that is not a syntactically valid `/mctl <verb> [arg]`
  command THE SYSTEM SHALL return a parse error and no side effect — parsing is a pure function
  with no I/O.
- WHEN `ParseCommand` is given `/mctl status`, `/mctl leads`, `/mctl pause` THE SYSTEM SHALL return
  a command requiring no argument.
- WHEN `ParseCommand` is given `/mctl show <id>`, `/mctl continue <id>`, `/mctl takeover <id>` THE
  SYSTEM SHALL return a command carrying a parsed integer conversation id, and SHALL reject a
  non-numeric or missing id.
- WHEN `ParseCommand` is given `/mctl approve <code>` or `/mctl reject <code>` THE SYSTEM SHALL
  return a command carrying the approval code verbatim (case as typed; matching is case-sensitive,
  matching `GetAgentActionByCode`'s existing contract).
- WHEN `ParseCommand` is given an unrecognized verb THE SYSTEM SHALL return a parse error naming
  the unknown verb, never a partial/best-guess command.

### Notifier
- WHEN the executor or control router needs to reach the owner THE SYSTEM SHALL send exclusively
  via `internal/telegram.SendToSelf` (`InputPeerSelf`, the owner's own MTProto session) — never via
  a bot token, which cannot post into Saved Messages.
- WHEN an action reaches `pending_approval` THE SYSTEM SHALL send an approval request to Saved
  Messages containing: a summary of the conversation/intent, the verbatim draft reply text, and the
  exact `/mctl approve <code>` / `/mctl reject <code>` strings the owner can copy.
- WHEN `/mctl status` is received THE SYSTEM SHALL reply in Saved Messages with the current agent
  mode, autopilot-paused flag, kill-switch state, and counts of conversations by state.

### Executor send flow and crash recovery
- WHEN an action transitions into `approved` THE SYSTEM SHALL generate a Telegram `random_id` and
  persist it on the action row BEFORE issuing the `messages.sendMessage` RPC.
- WHEN the executor issues the send RPC THE SYSTEM SHALL have already CAS'd the action's status to
  `executing` using the SAME database write that persisted the `random_id` (single atomic
  transition), so that no `executing` row is ever missing its `random_id`.
- IF the process restarts (or a tick observes) a row with `status = executing` THEN THE SYSTEM
  SHALL retry `messages.sendMessage` with the SAME persisted `random_id`, relying on Telegram's
  `random_id` deduplication to make the retry safe regardless of whether the original RPC reached
  Telegram before the crash.
- WHILE an action is in `executing` THE SYSTEM SHALL NOT mint a new `random_id` or send with a
  different one under any circumstance.
- WHEN a send (first attempt or retry) succeeds THE SYSTEM SHALL CAS the action from `executing` to
  `executed`, record the returned Telegram message id, append the profile's disclosure text
  (`policy.DisclosureSep` + `DisclosureText`) to the sent body, and increment the conversation's
  autonomous-turn counter.
- IF a send fails with a permanent Telegram error (e.g. peer no longer reachable, user blocked the
  account) THEN THE SYSTEM SHALL stop retrying that action, move it to a terminal failed state with
  the error recorded, and count it in the dead-letter metric — it SHALL NOT be retried indefinitely
  the way a transient error is.

### Re-check before send
- WHEN the executor is about to issue the send RPC (both a fresh `approved -> executing` send and
  an `executing` retry) THE SYSTEM SHALL re-run `policy.Evaluate` against freshly-read profile and
  conversation rows, not the state captured at approval time.
- IF the re-check evaluates to Deny (kill switch engaged, mode off, autopilot paused, conversation
  no longer `active`, sender newly blocked, or any other current-truth deny condition) THEN THE
  SYSTEM SHALL NOT issue the send RPC and SHALL move the action to a terminal denied state with the
  fresh reasons recorded, even though it was previously approved.
- WHILE a conversation is `taken_over` (owner replied in-thread or issued `/mctl takeover`) THE
  SYSTEM SHALL treat any `pending_approval` or `executing` action for that conversation as blocked
  by the next re-check and SHALL NOT let the agent's reply land after the owner's.

### Edit/delete invalidation
- IF the source incoming message that a `pending_approval`, `approved`, or `executing` action's
  draft was derived from has since been edited THEN THE SYSTEM SHALL deny/expire that action with a
  reason identifying the edit, rather than sending the stale draft unchanged.
- IF the source incoming message has since been deleted THEN THE SYSTEM SHALL deny/expire that
  action with a reason identifying the deletion.
- THE SYSTEM SHALL perform this staleness check at the same re-check point as the policy re-check
  (immediately before the send RPC), not only at proposal time.

### Approval TTL
- WHILE an action sits in `pending_approval` for longer than the configured TTL
  (`AGENT_APPROVAL_TTL`, default 24h) THE SYSTEM SHALL expire it via the existing
  `ExpireStaleAgentActions` sweep already wired in `internal/sweeper.AgentJobs` — this proposal
  reuses that mechanism rather than duplicating it inside the executor.

### Owner profile (`internal/agent/profile`)
- WHEN the server starts with `AGENT_PROFILE_PATH` set THE SYSTEM SHALL load and validate the YAML
  profile at that path before serving `GET /recruiters/{peer}`.
- WHEN `PublicProfile(peerTGID)` is called THE SYSTEM SHALL return only the `identity`,
  `public_profile`, `skills`, and `preferences` sections (or the subset of fields within them
  intended for exposure).
- THE SYSTEM SHALL NEVER include any field from the `restricted` section in the value returned by
  `PublicProfile`, regardless of that field's `approval_required` / `never_auto_send` markers —
  those markers describe a future gated-disclosure flow and are not, by themselves, a signal to
  expose the field today.
- IF `AGENT_PROFILE_PATH` is unset or the file is missing/invalid THEN THE SYSTEM SHALL leave
  `Server.Profile` nil (existing 501 behavior) and log the reason, never panic or serve a
  partially-loaded profile.

### Gating and safety
- WHILE `AGENT_ENABLED` is false THE SYSTEM SHALL NOT start the executor tick loop, the control
  router, or mount any profile-backed endpoint — matching every other agent-domain feature's
  gating convention.
- THE SYSTEM SHALL route every send through the existing `allowedActionTransitions` CAS state
  machine (extended, not bypassed, by this proposal) — no ad hoc `UPDATE agent_actions` outside
  `internal/db`.
- THE SYSTEM SHALL NOT log message bodies, draft text, or profile field values;
  `internal/audit/redact.go`'s `sensitiveKeys` set governs this and SHALL be extended for any new
  sensitive attribute keys this proposal introduces.

## Out of scope

- The external agent worker itself (the process that calls Claude, proposes replies via
  `internal/agentapi`) — that is #296 and earlier PRs, already merged into this clone.
- A gated "ask owner to disclose a restricted field" flow that would use the `approval_required` /
  `never_auto_send` markers to drive a live approval — the issue only asks that restricted fields
  are stripped from the agent surface today; wiring the markers into an actual disclosure workflow
  is future work.
- Hot-reloading the owner profile YAML on file change (SIGHUP, fsnotify, etc.) — load-once-at-startup
  is sufficient for this proposal; see Open Questions.
- Multi-owner / multi-account profile management UI — `AGENT_PROFILE_PATH` is a single mounted file
  per deployment, matching how the account is deployed today (one mctl-telegram instance per owner).
- Rewriting `internal/agent/policy.Evaluate` — this proposal calls it more often (at approve-time
  and again at send-time) but does not change its decision logic.
- The PR-9 privacy/retention documentation the issue references in its final paragraph — flagged
  as a downstream dependency below, not authored by this proposal.

## Open questions

- **Delete detection requires a small listener change outside the three named packages.** MTProto's
  delete-message updates for private chats carry bare message IDs with no peer field, so detecting
  "this specific incoming message was deleted" requires a new `OnDeleteMessages` handler in
  `internal/agent/listener` that correlates deleted IDs against `incoming_events.message_id` for the
  account, plus a new `EventKindMessageDelete`. The issue text scopes this proposal to
  `internal/agent/control` / `executor` / `profile`, but the edit/delete-invalidation acceptance
  criterion is not satisfiable without it. Interpretation taken: this listener change is treated as
  a necessary, minimal extension of the already-shipped `internal/agent/listener` package (not a new
  package), and is called out explicitly in tasks.md so the Tier 2 implementer does not miss it.
- **Exact wording/format of `/mctl status` and `/mctl leads` output** is not specified by the issue.
  Interpretation taken: mirror the fields already exposed by `GET /policy` and
  `GET /conversations/{id}/context` (mode, autopilot_paused, kill switch, conversation counts by
  state, and a compact per-lead line) so the control surface stays consistent with the agent-facing
  HTTP surface rather than inventing new vocabulary.
- **Whether `/mctl takeover <id>` should itself deny/cancel any action already `executing`** for
  that conversation, or only conversations that are `pending_approval` at the moment of takeover.
  Interpretation taken: `takeover` sets `conversation.state = taken_over` immediately (the same
  mechanism the listener already uses for an in-thread owner reply), and the executor's mandatory
  send-time re-check is what actually stops an in-flight `executing` action — no separate
  cancellation code path is needed, since the re-check already covers this case generically.
- **Whether the executor should be a goroutine inside `cmd/server` (poll-based, like the existing
  sweepers) or a separate process/binary.** Interpretation taken: a goroutine inside `cmd/server`,
  ticker-driven, mirroring `internal/sweeper` and `listener.RunSupervisor` — this is the only
  process with direct access to the `telegram.ClientPool` needed to call `SendToInputPeer`, and
  every other MTProto-writing feature in this codebase (digest, listener, MCP tools) lives in the
  same process today.
- **Whether permanently-failed sends should reuse the `denied` status or need a new terminal status**
  (e.g. `send_failed`) distinct from a policy denial, for operator clarity. Interpretation taken:
  reuse `denied` with a `policy_reasons` string prefixed to distinguish cause (e.g. "send failed:
  ..." vs a policy reason), to avoid widening the state machine and the status-labeled metrics/
  dashboards built around it. Flagged for Tier 2 / reviewer judgment since a new status is a
  defensible alternative.
- Everything else the issue specifies (command list, approval TTL value, disclosure separator,
  policy re-check timing, `random_id` crash-recovery semantics) is unambiguous in the issue body and
  is not treated as open.
