# Make conversation ids discoverable for /mctl show|continue|takeover

## Context

`/mctl show <id>`, `/mctl continue <id>` and `/mctl takeover <id>` all take the
internal `conversations.id` (parsed as a plain integer in
`internal/agent/control/router.go`'s `handleShow`/`handleContinue`/
`handleTakeover`), but no owner-facing command reliably surfaces that number.
`/mctl leads` (`router.go handleLeads`) is the only command that prints ids,
and it does so by listing `job_leads` rows (`Store.ListJobLeads`, backed by
`internal/db/agent_actions.go`'s `job_leads` table), not conversations — a
conversation with no lead row (e.g. one that never turned into a job lead, or
one the owner took over before the agent extracted anything) never appears
anywhere. Even when a lead line does appear, it identifies the conversation by
`company`/`role`, which are frequently blank (`Conv #5 — — / — (discovery)`),
while the one thing that reliably identifies a Telegram peer — the display
name the agent already stores in `conversations.peer_display_name` and prints
in `/mctl show`'s own output (`PeerDisplayName`, `router.go:120-121`) — is
missing from the leads listing entirely.

This matters most exactly when the owner needs it most: when the agent has
gone quiet on a thread (e.g. after an owner reply flips the conversation to
`taken_over`, per `internal/db/agent_domain.go`'s `ConversationTakenOver`
constant and `SECURITY.md`'s description of that state), the only documented
recovery path is `/mctl continue <conversation id>` — but there is no reliable
way to learn that id for a thread with no lead row. The recovery loop is
circular: to un-stick a conversation you need its id, and today the only
place ids are printed depends on agent-authored lead data that a stuck
conversation may never have.

## User stories

- AS the account owner I WANT `/mctl leads` to show the peer's name next to
  each conversation id SO THAT I can identify a conversation even when
  `company`/`role` are blank.
- AS the account owner I WANT a command that lists my recent conversations by
  recency, independent of whether a job lead exists, SO THAT I can find and
  recover a `taken_over` or otherwise stuck thread that never produced a lead.
- AS the account owner I WANT to target `/mctl show`, `/mctl continue` and
  `/mctl takeover` using something I can see in the Telegram UI (a username or
  the peer's Telegram user id) as well as the internal conversation id SO THAT
  I am not required to first run a lookup command to get the numeric id.

## Acceptance criteria (EARS)

- WHEN the owner runs `/mctl leads` THE SYSTEM SHALL include each lead's
  conversation's peer display name in the printed line (falling back to the
  existing dash placeholder when the peer has no stored display name).
- WHEN the owner runs `/mctl conversations` THE SYSTEM SHALL reply with the
  owner's most recent conversations ordered by `updated_at` descending,
  each line showing the conversation id, peer display name, and state.
- WHEN the owner runs `/mctl conversations` and has no conversations THE
  SYSTEM SHALL reply with a message stating there are none, matching the
  existing "No leads yet." / "No agent profile configured..." style used by
  `handleLeads`/`handleStatus`.
- WHEN the owner runs `/mctl show`, `/mctl continue`, or `/mctl takeover` with
  an argument that parses as an integer THE SYSTEM SHALL treat it as a
  conversation id, exactly as today (no behavior change for existing numeric
  usage).
- WHEN the owner runs `/mctl show`, `/mctl continue`, or `/mctl takeover` with
  an argument of the form `user:<telegram id>` THE SYSTEM SHALL resolve it to
  the conversation whose `peer_tg_id` matches, scoped to the owner's own
  conversations, and operate on that conversation.
- WHEN the owner runs `/mctl show`, `/mctl continue`, or `/mctl takeover` with
  an argument of the form `@<username>` (or a bare username containing no
  digits-only content) THE SYSTEM SHALL resolve it to the conversation whose
  stored `peer_username` matches case-insensitively, scoped to the owner's own
  conversations, and operate on that conversation.
- IF a `user:<id>` or `@<username>` reference does not match any of the
  owner's conversations THEN THE SYSTEM SHALL reply with a not-found message
  analogous to today's `"Conversation %d not found."`, without changing
  arguments into a different command or crashing the router.
- IF an argument is neither a valid integer, nor `user:<id>`, nor a
  `@username`/bare-username form THEN THE SYSTEM SHALL reply with a usage
  message, matching today's `"Usage: /mctl show <conversation id>"` shape
  (extended to mention the new forms).
- WHILE resolving a peer reference THE SYSTEM SHALL rely only on data already
  persisted in the `conversations` table (`peer_tg_id`, `peer_username`) and
  SHALL NOT make a live Telegram/MTProto RPC call to resolve the reference.

## Out of scope

- Any live Telegram API username resolution (`contacts.ResolveUsername` /
  `internal/telegram.ResolvePeer`) for peers the owner has never previously
  messaged through this system — `@username`/`user:<id>` only ever resolve
  against conversations already present in the local `conversations` table,
  which is sufficient for `continue`/`takeover` since both commands only ever
  make sense on a conversation that already exists.
- Pagination, filtering, or search for `/mctl conversations` beyond a fixed
  recency-ordered limit (mirrors `/mctl leads`' existing `limit 20` behavior).
- Changing `/mctl leads`' selection criteria (it still lists `job_leads` rows
  only) — this proposal only adds the peer name to its existing lines.
- Any change to `taken_over`/policy semantics (e.g. the "owner notification
  suppressed" issue referenced in the source issue's context — that is a
  separate `policy.Evaluate` ordering issue filed alongside this one).
- Renumbering or exposing conversation ids differently (e.g. switching to
  UUIDs) — the internal integer id remains the canonical identifier; this
  proposal only adds alternate ways to reach it.

## Open questions

- Should `/mctl conversations` respect a fixed limit (e.g. 20, matching
  `/mctl leads`) or should it be owner-configurable via an argument (e.g.
  `/mctl conversations 50`)? Resolved here with the most reasonable
  interpretation: fixed limit of 20, no argument, matching `handleLeads`'
  existing `ListJobLeads(ctx, userID, 20)` call — consistent with the rest of
  the command surface and cheapest to implement and test.
- Should a bare (no `@`, no `user:` prefix) alphabetic argument to
  `show`/`continue`/`takeover` be treated as a username automatically, or
  should `@` be required? Resolved here with the most reasonable
  interpretation: `@username` and `user:<id>` are the two explicit forms
  (matching the issue's own suggested syntax); a bare non-numeric argument
  that is not one of those two forms falls through to "not found" via the
  usage-error path rather than being silently guessed at, since Telegram
  usernames may contain digits and an implicit heuristic risks surprising
  behavior.
- Should `/mctl leads`' peer-name addition also print `peer_username` (e.g.
  `@handle`) when `peer_display_name` is empty but a username is known?
  Resolved here with the most reasonable interpretation: no — reuse the
  existing `orDash` fallback for consistency with `/mctl show`, keeping the
  line format change minimal; the username is still usable as a `continue`/
  `takeover` target even when not printed in `/mctl leads`.
