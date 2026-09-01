# Design: issue-442-mctl-show-continue-takeover-need-a-conve

## Current state

The owner's command surface lives in `internal/agent/control`:

- `command.go`'s `ParseCommand` splits `/mctl <sub> [arg...]` into a
  `Command{Type, Arg}`. For `show`/`continue`/`takeover` the remaining fields
  are joined verbatim into `Arg` with no format validation — validation
  happens downstream in the router.
- `router.go`'s `handleShow`, `handleContinue`, and `handleTakeover` each
  independently do `strconv.ParseInt(arg, 10, 64)` and, on failure, reply
  with a `"Usage: /mctl <sub> <conversation id>"` message. On success they
  call `Store.GetConversation(ctx, userID, convID)` /
  `Store.SetConversationState(ctx, userID, convID, ...)`, both scoped to
  `userID` via a `WHERE id = $1 AND user_id = $2` clause
  (`internal/db/agent_domain.go`'s `getConversation` and
  `SetConversationState`).
- `handleLeads` calls `Store.ListJobLeads(ctx, userID, 20)`
  (`internal/db/agent_actions.go:1102`), which selects from `job_leads`
  ordered by `updated_at DESC LIMIT $2`, and prints
  `"Conv #%d — %s / %s (%s)\n"` using `l.ConversationID`, `l.Company`,
  `l.Role`, `l.Status`. `JobLead` (`agent_actions.go:953`) has no peer-name
  field; the leads query never joins `conversations`.
- `handleShow` prints `conv.PeerDisplayName` (`Conversation.PeerDisplayName`,
  `agent_domain.go`), sourced from `conversations.peer_display_name`, which
  `EnsureConversation` keeps fresh from Telegram metadata on every incoming
  event (`COALESCE`d so a later empty value never erases a known name) — see
  `agent_domain.go:498-520`. The same table already stores `peer_username`
  and `peer_tg_id` for every conversation.
- `Store.GetConversationByPeer(ctx, userID, peerTGID)` already exists
  (`agent_domain.go:530`) and is used today by
  `internal/agent/listener/listener.go:318` to look up a conversation from an
  incoming Telegram event's peer id. There is no equivalent
  `GetConversationByUsername`, and no `ListConversations` (only
  `ListJobLeads`).
- Schema: `conversations` (SQLite: `agent_schema.go:313-325`; Postgres:
  `agent_schema.go:527-539`) has a unique index on `(user_id, peer_tg_id)`
  only (`idx_conversations_user_peer`). There is no index covering
  `(user_id, updated_at)` or `(user_id, peer_username)`. `migrateAgent`
  (`agent_schema.go:23`) runs every statement in `agentSchemaSQLite()` /
  `agentSchemaPG()` on every startup — `CREATE TABLE IF NOT EXISTS` /
  `CREATE INDEX IF NOT EXISTS` are idempotent, so new indexes can be appended
  to these lists and apply to existing deployments automatically, matching
  how `idx_job_leads_conversation` and friends were added.
- The unknown-command help text and error-path usage strings
  (`router.go:47`, `handleShow`/`handleContinue`/`handleTakeover`'s
  `"Usage: ..."` replies) are the only place the command surface is
  documented to the owner — there is no separate help/docs file that lists
  `/mctl` subcommands (checked `SECURITY.md`, `internal/agentapi/actions.go`,
  `internal/agent/listener/listener.go`, `internal/agentworker/mcpserver.go`:
  all reference specific `/mctl` commands in code comments, none maintain a
  full command list that would need updating).

## Proposed solution

Three additive, independent changes, all inside `internal/agent/control` and
`internal/db`, following the file's existing conventions:

### 1. Peer name in `/mctl leads`

In `handleLeads` (`router.go`), for each `JobLead` fetch its conversation's
`PeerDisplayName` and include it in the printed line:

```go
for _, l := range leads {
	name := "—"
	if conv, err := r.Store.GetConversation(ctx, userID, l.ConversationID); err == nil {
		name = orDash(conv.PeerDisplayName)
	}
	fmt.Fprintf(&sb, "Conv #%d — %s — %s / %s (%s)\n", l.ConversationID, name, orDash(l.Company), orDash(l.Role), l.Status)
}
```

This reuses `Store.GetConversation` (already used by `handleShow`) rather
than adding a JOIN to `ListJobLeads`: `job_leads` is capped at 20 rows per
call (`ListJobLeads`'s existing default limit), this is a manual,
low-frequency owner command (not a hot path like the executor's send loop),
and keeping `JobLead`'s shape unchanged avoids touching `UpsertJobLead`,
`GetJobLead`, `GetJobLeadByConversation`, and their tests for a
presentation-only concern. A lookup failure (conversation deleted, or the
`ErrConversationNotFound` case) degrades to the existing dash placeholder
rather than failing the whole command, since a stale lead pointing at a
gone conversation must not break `/mctl leads` for the other 19 lines.

### 2. New `/mctl conversations` command

- `command.go`: add `CmdConversations CommandType = "conversations"` to the
  `CmdStatus, CmdLeads, CmdPause` no-arg group in `ParseCommand`'s switch (no
  argument required, same as `leads`).
- `internal/db/agent_domain.go`: add
  `ListConversations(ctx context.Context, userID int64, limit int) ([]Conversation, error)`,
  modeled directly on `ListJobLeads`: `SELECT ... FROM conversations WHERE
  user_id = $1 ORDER BY updated_at DESC LIMIT $2`, reusing the same
  column set and scan pattern as `getConversation`.
- Schema: append
  `CREATE INDEX IF NOT EXISTS idx_conversations_user_updated ON conversations(user_id, updated_at DESC)`
  to both `agentSchemaSQLite()` and `agentSchemaPG()` (SQLite drops
  `DESC` from the index key silently but the statement is valid there too —
  matches how other indexes in this file are written once and shared across
  both dialects). Without it, `ListConversations` does a full per-user
  table scan on every call; given the schema already indexes on
  `(user_id, peer_tg_id)` for a similarly small table, adding this second
  index is a cheap, standard covering-order optimization even at the small
  per-user row counts this system runs at today.
- `router.go`: add `case CmdConversations: return r.handleConversations(ctx, userID)`
  to `HandleSavedText`'s switch, and a `handleConversations` modeled on
  `handleLeads`:

  ```go
  func (r *Router) handleConversations(ctx context.Context, userID int64) error {
  	convs, err := r.Store.ListConversations(ctx, userID, 20)
  	if err != nil {
  		return fmt.Errorf("list conversations: %w", err)
  	}
  	if len(convs) == 0 {
  		return r.Notifier.Reply(ctx, userID, "No conversations yet.")
  	}
  	var sb strings.Builder
  	sb.WriteString("Recent conversations:\n")
  	for _, c := range convs {
  		fmt.Fprintf(&sb, "Conv #%d — %s (%s)\n", c.ID, orDash(c.PeerDisplayName), c.State)
  	}
  	sb.WriteString("\n/mctl show <conversation id> for details")
  	return r.Notifier.Reply(ctx, userID, sb.String())
  }
  ```

  This surfaces every conversation regardless of lead state, in particular
  `taken_over` ones with no `job_leads` row — the exact gap the issue
  reports.
- Update the unknown-command help text in `HandleSavedText` to list
  `/mctl conversations`.

### 3. Peer reference as an alternative to the numeric id

Add a shared resolver in `router.go` and use it in `handleShow`,
`handleContinue`, `handleTakeover` in place of each one's standalone
`strconv.ParseInt`:

```go
func (r *Router) resolveConversationID(ctx context.Context, userID int64, arg string) (int64, error) {
	if id, err := strconv.ParseInt(arg, 10, 64); err == nil {
		return id, nil
	}
	switch {
	case strings.HasPrefix(arg, "user:"):
		peerTGID, err := strconv.ParseInt(strings.TrimPrefix(arg, "user:"), 10, 64)
		if err != nil {
			return 0, db.ErrConversationNotFound
		}
		conv, err := r.Store.GetConversationByPeer(ctx, userID, peerTGID)
		if err != nil {
			return 0, err
		}
		return conv.ID, nil
	case strings.HasPrefix(arg, "@"):
		conv, err := r.Store.GetConversationByUsername(ctx, userID, strings.TrimPrefix(arg, "@"))
		if err != nil {
			return 0, err
		}
		return conv.ID, nil
	default:
		return 0, errNotAReference
	}
}
```

(`errNotAReference` is a small unexported sentinel distinguishing "not a
recognized reference form" from `db.ErrConversationNotFound`, so callers can
still show the existing usage message for garbage input vs. the existing
not-found message for a well-formed but unmatched reference.)

Each of `handleShow`/`handleContinue`/`handleTakeover` replaces its
`strconv.ParseInt(arg, ...)` call with `r.resolveConversationID(ctx, userID, arg)`,
keeping every downstream line (the `db.ErrConversationNotFound` handling, the
reply text) unchanged — only the id-acquisition step changes, so the
"Conversation %d not found" and success messages still print the resolved
numeric id, giving the owner the id to reuse directly next time.

`internal/db/agent_domain.go` gains `GetConversationByUsername`, mirroring
`GetConversationByPeer`:

```go
func (s *Store) GetConversationByUsername(ctx context.Context, userID int64, username string) (*Conversation, error) {
	return s.getConversation(ctx, `user_id = $1 AND LOWER(peer_username) = LOWER($2)`, userID, username)
}
```

Bare usernames only, no `@` — the router strips it before calling. No new
index is added for this lookup: `peer_username` lookups are scoped to one
owner's conversations (already a small set) and happen only on the rare
manual-recovery path this issue is about, not a hot path, so the added
schema surface of a third index is not justified the way the
`updated_at` one is for `/mctl conversations`, which is a directly
recency-listing query.

No live Telegram/MTProto call is made anywhere in this resolution path —
`peer_tg_id` and `peer_username` are read straight from the already-persisted
`conversations` row, consistent with the "only ever targets a conversation
that already exists" scoping in Acceptance Criteria.

## Alternatives

1. **Join `conversations` into `ListJobLeads`'s SQL and add a
   `PeerDisplayName` field to `JobLead`.** Dropped: `JobLead` is a shared
   domain type used by `UpsertJobLead`, `GetJobLead`,
   `GetJobLeadByConversation`, and their existing tests
   (`internal/db/agent_actions_test.go`, not modified by this proposal) —
   widening its meaning to include conversation-presentation data for the
   benefit of one Telegram-facing formatting call is a larger, less-isolated
   change than doing the extra `GetConversation` call per line in
   `handleLeads`, for a command capped at 20 rows and called manually.
2. **Resolve `@username` via a live `contacts.ResolveUsername` RPC
   (`internal/telegram.ResolvePeer`, `internal/telegram/peers.go:14`).**
   Dropped: `continue`/`takeover`/`show` only ever make sense against a
   conversation this system already has a row for (you cannot take over a
   thread you have never seen), so the locally stored `peer_username` is
   always sufficient; a live RPC would add network latency, flood-wait risk,
   and a `*telegram.Client` dependency into the synchronous Saved-Messages
   command path (`Router` currently depends only on `*db.Store` and
   `Approver`, both non-network-blocking in the flood-wait sense) for zero
   additional reach.
3. **Replace the leads-only view entirely with `/mctl conversations` and
   drop `/mctl leads`.** Dropped: `job_leads`-specific fields (`company`,
   `role`, `status`) are genuinely useful and not present on `Conversation`;
   the issue's own suggested fixes are additive ("any of these would close
   the gap"), and removing `/mctl leads` is an unrelated, larger behavior
   change with no requirement driving it.

## Platform impact

- **Migrations**: one additive index,
  `idx_conversations_user_updated ON conversations(user_id, updated_at DESC)`,
  appended to both `agentSchemaSQLite()` and `agentSchemaPG()` in
  `internal/db/agent_schema.go`. Applied automatically on next server start
  via `migrateAgent`'s existing idempotent-statement loop — no separate
  migration file or manual step, consistent with how every other index in
  this schema was added. No column additions, no `addColumnIfMissing` calls
  needed (the two new columns this design reads — `peer_display_name`,
  `peer_username` — already exist).
- **Backward compatibility**: fully additive. Existing numeric
  `/mctl show|continue|takeover <id>` usage is unchanged (the fast path in
  `resolveConversationID` is still the first `strconv.ParseInt` attempt,
  identical to today's behavior and error text for non-numeric,
  non-reference garbage). `/mctl leads`' output gains one extra field per
  line but keeps its existing fields and ordering — any owner-side scripting
  against the old exact string would need to tolerate the new field, but
  this is a human-facing Telegram reply, not an API contract. `/mctl
  conversations` is a brand-new subcommand name with no prior meaning.
- **Resource impact**: `handleLeads` goes from 1 query to up to 21
  (`ListJobLeads` + one `GetConversation` per row, capped at 20) — trivial at
  this system's scale (a single owner's Saved Messages command, not a
  request-per-second path). `handleConversations` is 1 new query, index-
  backed. `resolveConversationID`'s new paths add at most 1 extra query
  (`GetConversationByPeer` or `GetConversationByUsername`) only when the
  argument is non-numeric, which is strictly the new, previously-impossible
  case.
- **Risks + mitigations**:
  - *Username collisions/staleness*: `peer_username` is refreshed
    opportunistically (`EnsureConversation`'s `COALESCE`, never cleared once
    known) — if a peer changes their Telegram username, `@oldhandle` keeps
    resolving to them until a fresh incoming event updates the stored value,
    and the new handle will not resolve until then. Documented as an open
    question/acceptable staleness, not fixed by this proposal (same
    staleness already exists for `PeerDisplayName` shown in `/mctl show`
    today).
  - *Two different conversations owned by the same user could theoretically
    share a peer_username* if Telegram ever recycled a handle between two
    peers the owner talked to at different times without a refresh in
    between; `GetConversationByUsername`'s `getConversation` helper returns
    a single row via `QueryRowContext`, so this would surface as "whichever
    row's `peer_username` value is stale" rather than an error. Low risk in
    practice (recycled Telegram usernames are rare) and no worse than not
    having the feature at all (today there is no way to reach that
    conversation by name whatsoever).
  - *`errNotAReference` sentinel shadowing real usage errors*: kept
    unexported and internal to `router.go`, distinct from
    `db.ErrConversationNotFound`, so the three call sites can still
    distinguish "reply with usage text" (bad input) from "reply with not
    found" (well-formed reference, no match) exactly as they do today for
    the numeric-only case.
