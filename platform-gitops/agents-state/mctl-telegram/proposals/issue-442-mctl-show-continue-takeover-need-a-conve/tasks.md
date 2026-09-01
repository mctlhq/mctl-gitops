# Tasks: issue-442-mctl-show-continue-takeover-need-a-conve

- [ ] 1. Add `idx_conversations_user_updated ON conversations(user_id, updated_at DESC)`
      to both `agentSchemaSQLite()` and `agentSchemaPG()` in
      `internal/db/agent_schema.go` — DoD: statement appended to both
      dialect statement lists in the existing `CREATE INDEX IF NOT EXISTS`
      style; a fresh `migrateAgent` run against a scratch SQLite DB and
      against the Postgres test harness both succeed.

- [ ] 2. Add `Store.ListConversations(ctx, userID, limit) ([]Conversation, error)`
      to `internal/db/agent_domain.go`, modeled on `ListJobLeads`
      (`internal/db/agent_actions.go:1102`): `SELECT` the same columns as
      `getConversation`, `WHERE user_id = $1 ORDER BY updated_at DESC LIMIT $2`,
      default limit 20 when `limit <= 0` — DoD: unit test with 3+ seeded
      conversations across two users confirms per-user scoping and
      `updated_at DESC` ordering.

- [ ] 3. Add `Store.GetConversationByUsername(ctx, userID, username) (*Conversation, error)`
      to `internal/db/agent_domain.go`, reusing the existing `getConversation`
      helper with `WHERE user_id = $1 AND LOWER(peer_username) = LOWER($2)`
      (depends on 1, for consistent PR sequencing; no functional dependency)
      — DoD: unit test confirms case-insensitive match, per-user scoping, and
      `ErrConversationNotFound` when no row matches.

- [ ] 4. Add `CmdConversations` to `internal/agent/control/command.go`'s
      `CommandType` consts and to the no-arg group in `ParseCommand`'s switch
      (alongside `CmdStatus`, `CmdLeads`, `CmdPause`) — DoD: `ParseCommand("/mctl conversations")`
      returns `Command{Type: CmdConversations}`; add a case to the existing
      `TestParseCommand_Table` table in `command_test.go`.

- [ ] 5. Update `handleLeads` in `internal/agent/control/router.go` to fetch
      each lead's conversation via `Store.GetConversation` and include
      `orDash(conv.PeerDisplayName)` in the printed line, degrading to `"—"`
      on lookup failure (depends on none) — DoD: existing `handleLeads` test
      updated/extended to assert the peer name appears in the reply text,
      and that a lead pointing at a since-deleted conversation still renders
      the rest of the line instead of erroring.

- [ ] 6. Add `handleConversations` to `router.go` and wire
      `case CmdConversations: return r.handleConversations(ctx, userID)`
      into `HandleSavedText`'s switch (depends on 2, 4) — DoD: reply format
      matches `handleLeads`' style (`"Conv #%d — %s (%s)\n"`), empty case
      replies `"No conversations yet."`, and a router-level test (mirroring
      existing `handleLeads`/`handleShow` tests in `router_test.go`) exercises
      both the populated and empty cases.

- [ ] 7. Add `resolveConversationID` to `router.go` and switch `handleShow`,
      `handleContinue`, `handleTakeover` to call it instead of their inline
      `strconv.ParseInt` (depends on 3) — DoD: all three handlers keep
      identical behavior and reply text for numeric args and for garbage
      args (usage message); new tests cover `user:<peer_tg_id>` and
      `@username` resolving to the right conversation for all three
      commands, and both forms replying with the existing not-found message
      when unmatched.

- [ ] 8. Update the unknown-command help text in `HandleSavedText`
      (`router.go`'s `"Unknown command. Try:\n..."` string) to list
      `/mctl conversations`, and update the three `"Usage: /mctl <sub>
      <conversation id>"` strings in `handleShow`/`handleContinue`/
      `handleTakeover` to mention the `user:<id>` / `@username` forms
      (depends on 6, 7) — DoD: strings reviewed for consistency with the
      rest of the file's phrasing; any test asserting exact usage-string
      text is updated to match.

- [ ] 9. Run `go fmt ./...`, `go vet ./...`, and `golangci-lint run` per
      `CLAUDE.md` conventions, and the full `internal/agent/control` and
      `internal/db` test suites (depends on 1-8) — DoD: clean lint, all
      tests pass, no `TODO`/debug output left behind.

## Tests

- [ ] T1. `command_test.go`: `ParseCommand("/mctl conversations")` and
      `/MCTL Conversations` (case-insensitivity) both yield
      `Command{Type: CmdConversations}`.
- [ ] T2. `agent_domain_test.go` (or equivalent): `ListConversations` returns
      only the calling user's conversations, ordered `updated_at DESC`,
      respecting the limit.
- [ ] T3. `agent_domain_test.go`: `GetConversationByUsername` matches
      case-insensitively, is scoped per-user, and returns
      `ErrConversationNotFound` for no match and for a username belonging to
      a different user.
- [ ] T4. `router_test.go`: `handleLeads` output includes the peer display
      name for a lead whose conversation has one set, and falls back to `—`
      when it does not or when the conversation lookup fails.
- [ ] T5. `router_test.go`: `handleConversations` lists conversations
      including a `taken_over` one with no `job_leads` row — the specific
      gap from the source issue — and replies `"No conversations yet."` when
      the user has none.
- [ ] T6. `router_test.go`: `handleShow`/`handleContinue`/`handleTakeover`
      each resolve `user:<peer_tg_id>` and `@username` to the correct
      conversation id, still resolve a plain integer exactly as before, and
      still reply with the pre-existing usage/not-found messages for
      malformed or unmatched input.
- [ ] T7. End-to-end smoke (manual or integration, matching how existing
      `/mctl` commands are exercised): after `/mctl takeover <id>`, running
      `/mctl conversations` shows that conversation as `taken_over`, and
      `/mctl continue <id>` (or the equivalent `@username`/`user:<id>` form)
      resumes it — closing the exact circular-recovery loop described in the
      issue.

## Rollback

All changes are additive (new command, new store methods, new index, one
extra field in an existing reply string) with no destructive schema change
and no removal of existing behavior. To roll back:

1. Revert the PR(s) implementing tasks 1-8. `CREATE INDEX IF NOT EXISTS
   idx_conversations_user_updated` is safe to leave in place even after a
   code revert (an unused index costs write overhead but breaks nothing) —
   if a full rollback of the index itself is wanted, drop it manually via
   `DROP INDEX IF EXISTS idx_conversations_user_updated` in a follow-up
   migration statement; nothing in the schema depends on its presence.
2. No data migration or backfill was performed, so no data-side rollback is
   needed — `peer_display_name`/`peer_username` were already populated by
   existing `EnsureConversation` calls before this proposal.
3. Because `/mctl conversations` and the `user:`/`@` reference forms are new
   surface area with no prior callers, reverting them cannot break any
   existing owner workflow; only `/mctl leads`' line format (task 5) changes
   existing output, and reverting that one commit restores the exact prior
   string.
