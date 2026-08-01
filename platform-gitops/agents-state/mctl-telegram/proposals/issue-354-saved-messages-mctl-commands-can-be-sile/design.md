# Design: issue-354-saved-messages-mctl-commands-can-be-sile

## Current state

`internal/agent/listener/extract.go` maps raw `gotd` updates onto `db.IncomingEvent`s. The
relevant paths, all read from the clone:

- `ExtractMessage(accountUserID, selfTGID int64, msg *tg.Message, ents tg.Entities, isEdit bool)`
  is called from `internal/agent/listener/listener.go`'s `onMessage`, which is wired to
  `tg.NewUpdateDispatcher`'s `OnNewMessage`/`OnEditMessage` handlers inside
  `dispatcherFor` -- this is the **live push** path.
- `ExtractMessage` first checks `if msg.Out`. Only inside that branch, if
  `peerUser.UserID == selfTGID` (the message's dialog is the owner's own Saved Messages), does
  it call `classifySavedCommand`. If `msg.Out` is `false`, execution falls through to the
  generic block below (`text == ""` check, then `peerUser, ok := msg.PeerID.(*tg.PeerUser)`,
  etc.), which treats the message as an ordinary inbound DM and returns
  `db.EventKindPrivateMessage` (or `EventKindMessageEdit` for an edit) with
  `ChatTGID = peerUser.UserID`. For a Saved Messages message this is `selfTGID` -- identical to
  what `classifySavedCommand` would have used.
- `classifySavedCommand(accountUserID, selfTGID int64, msg *tg.Message, text string, isEdit bool)`
  does **not** look at `msg.Out` at all. It authenticates the message via `msg.GetFwdFrom()`,
  `msg.GetSavedPeerID()`, and `msg.GetFromID()` -- checks that hold regardless of what `Out`
  says. Its own doc comment states the invariant precisely: "nothing but the owner can ever
  author a message that lands in their own primary Saved Messages dialog." It filters to
  `/mctl`-prefixed text (`isMCTLCommand`) and returns `db.EventKindSavedCommand`.
- `ExtractSavedHistoryMessage(accountUserID, selfTGID int64, msg *tg.Message)` -- used only by
  `pollSavedHistory` in `internal/agent/listener/history.go` (5-second ticker, gated on
  `l.Store.GetSavedCommandCursor`) -- checks `peerUser.UserID != selfTGID` and otherwise
  delegates straight to `classifySavedCommand`, deliberately never consulting `msg.Out` per its
  own doc comment referencing the 2026-07-26 observation that `messages.getHistory` against
  `InputPeerSelf` does not reliably set it either.
- `eventIDForMessage(accountTGID, chatID, messageID int64, editDate int, body string) string`
  builds `"evt:v1:" + accountTGID + ":" + chatID + ":" + messageID[+ ":e" + editDate + ":" +
  hash6(body)]`. It is called from three places in `extract.go`: the `msg.Out` inbound-owner
  branch (`EventKindOwnerOutgoing`), the generic inbound branch
  (`EventKindPrivateMessage`/`EventKindMessageEdit`), and `classifySavedCommand`
  (`EventKindSavedCommand`). **None of the three calls include `Kind` in the key.** For a Saved
  Messages message, the generic-inbound call and the `classifySavedCommand` call pass the exact
  same `(selfTGID, selfTGID, messageID, editDate, body)` tuple, so they produce the exact same
  `event_id`.
- `internal/db/agent_schema.go` creates `incoming_events` with a **global** unique index:
  `CREATE UNIQUE INDEX IF NOT EXISTS idx_incoming_events_event_id ON incoming_events(event_id)`
  (present in both the SQLite and Postgres schema blocks, ~lines 292-305 and ~506-519). The
  index has no `kind` component.
- `internal/agent/listener/listener.go`'s `persist` function's `EventKindSavedCommand` case
  does: `GetIncomingEvent` dedup check (return nil/no-op if a row with this `event_id` already
  exists) -> `l.Router.HandleSavedText(...)` -> `insertAuditEvent`. When the live push has
  already inserted a `private_message`-kinded row under the identical `event_id`, the dedup
  check short-circuits before `HandleSavedText` is ever called -- this is the exact mechanism
  the issue describes as "permanently, silently lost," and it is reproduced by
  `docs/reports/communication-agent-c1.md`'s 2026-08-01 entry (`incoming_events` ids 758, 767).
- `control.Router.HandleSavedText` (`internal/agent/control/router.go`) is the only entry point
  for `/mctl status|leads|show|continue|pause|takeover|approve|reject`; nothing else invokes it.

## Proposed solution

Two changes, both confined to `internal/agent/listener` (no schema migration, no new table, no
new column):

### 1. Stop gating Saved Messages classification on `msg.Out` (primary fix)

Reorder `ExtractMessage` so the self-peer check runs first, unconditionally, before the
`msg.Out` branch:

```go
func ExtractMessage(accountUserID, selfTGID int64, msg *tg.Message, ents tg.Entities, isEdit bool) (Extracted, bool) {
	if msg == nil {
		return Extracted{}, false
	}
	text := strings.TrimSpace(msg.Message)

	// Saved Messages (PeerID == selfTGID) can only ever contain messages the
	// owner authored, forwarded, or saved into it -- Telegram enforces this
	// server-side, independent of msg.Out. classifySavedCommand re-verifies
	// authorship itself (forwarded/saved-peer/from-id checks), so route here
	// unconditionally instead of trusting Out: Out was observed live
	// (2026-08-01, issue #354) reading false for a genuine owner-authored
	// live-push message in exactly this dialog, which silently misfiled the
	// command as an ordinary inbound private message.
	if peerUser, ok := msg.PeerID.(*tg.PeerUser); ok && peerUser.UserID == selfTGID {
		return classifySavedCommand(accountUserID, selfTGID, msg, text, isEdit)
	}

	if msg.Out {
		peerUser, ok := msg.PeerID.(*tg.PeerUser)
		if !ok {
			return Extracted{}, false
		}
		// (self-peer case removed -- handled above)
		ev := db.IncomingEvent{ /* EventKindOwnerOutgoing, unchanged */ }
		return Extracted{Event: ev}, true
	}
	// ... generic inbound branch, unchanged below this point ...
}
```

This makes the live push agree with `pollSavedHistory` on classification logic for every Saved
Messages message: both now call `classifySavedCommand`, and neither depends on `Out`. The
reported failure (a genuine `/mctl approve` misfiled as `EventKindPrivateMessage`) can no
longer happen on the live-push path at all -- the fix is at the point of first classification,
not a faster recovery from misclassification. `pollSavedHistory`'s existing behavior and its
concurrency-dedup guarantee (`TestPollSavedHistory_PushAndHistoryRouteOnce`: push and poll race
on the same genuine command, router called exactly once) is preserved, because both paths now
always compute the same `Kind` (and therefore, after change 2 below, the same `event_id`) for a
given Saved Messages message.

A secondary, low-risk benefit: today, an *ordinary* (non-command) Saved Messages note sent with
`Out == false` incorrectly falls through to the generic branch and gets persisted as a bogus
`EventKindPrivateMessage` with `ChatTGID == SenderTGID == selfTGID` -- creating a spurious
"conversation with yourself" and queuing an agent job against it. This fix removes that latent
side effect too, since `classifySavedCommand` drops non-`/mctl` Saved Messages content
regardless of `Out`, matching today's `Out == true` behavior exactly.

### 2. Make `event_id` generation kind-aware (safety net)

Add a `kind` parameter to `eventIDForMessage` and thread the caller's `db.EventKind*` constant
through at all three call sites:

```go
func eventIDForMessage(kind string, accountTGID, chatID, messageID int64, editDate int, body string) string {
	base := "evt:v1:" + kind + ":" + strconv.FormatInt(accountTGID, 10) + ":" +
		strconv.FormatInt(chatID, 10) + ":" + strconv.FormatInt(messageID, 10)
	if editDate > 0 {
		sum := sha256.Sum256([]byte(body))
		base += ":e" + strconv.Itoa(editDate) + ":" + fmt.Sprintf("%x", sum[:6])
	}
	return base
}
```

This is deliberately applied uniformly across all four kinds, not just
`EventKindSavedCommand`/`EventKindPrivateMessage`. Reading the `msg.Out` branch shows
`EventKindOwnerOutgoing` computes `ChatTGID = peerUser.UserID` -- the *other* party of an
ordinary 1:1 dialog -- which is exactly the same value the generic inbound branch computes for
messages *from* that same party. If `Out` is ever wrong for a normal DM (not just Saved
Messages; this proposal does not rule that out, see requirements.md's out-of-scope section),
an owner reply could collide event-id-wise with an inbound message in the same slot, with the
same "permanently blocked by dedup" failure mode. A uniform fix closes the whole class for the
cost of one shared helper signature change, rather than a narrower fix scoped only to today's
reported symptom.

This is a pure safety net for change 1: given change 1, `ExtractMessage` never produces a
`private_message`/`message_edit` kind for a Saved Messages message in the first place, so the
originally reported collision cannot occur post-fix. The `event_id` change protects against
*future* or *not-yet-understood* misclassifications (e.g., if `classifySavedCommand`'s own
authorship checks are ever loosened, or a new call site is added) reaching the same
"permanently and silently lost" failure mode the issue describes, by ensuring
`pollSavedHistory`'s reconciliation is never blocked by an unrelated-kind row occupying the same
key.

No `incoming_events`/`agent_jobs` schema change is required: `event_id` is already a free-form
`TEXT` column with a single unique index on itself (`agent_schema.go`); widening the string it
contains needs no migration. Existing rows written under the old `evt:v1:<acct>:<chat>:<msg>`
format remain valid and continue to dedup correctly against themselves; only newly-generated ids
gain the kind segment. There is no reprocessing or backfill of historical rows.

### 3. Low-cardinality diagnostic logging

Add one `slog.Debug` call at the top of `ExtractMessage` (or in `onMessage` just before calling
it) logging `message_id`, `is_edit`, `out` (bool), and the resolved sender id from `msg.FromID`/
`msg.PeerID` -- never `msg.Message` (body text) or anything from `internal/audit/redact.go`'s
`sensitiveKeys` set. This directly answers the issue's ask ("Add temporary trace logging...
around ExtractMessage's entry") and gives the on-call engineer(s) something to grep if `Out`
unreliability recurs for an ordinary DM (the scenario change 2 defends against structurally but
that this proposal does not otherwise investigate). Debug-level keeps it off by default in
production (existing `slog` JSON handler config in `cmd/server/main.go` controls the level), so
it carries no ongoing log-volume cost unless explicitly enabled for investigation.

## Alternatives

1. **Only fix `event_id` (safety net only, no live-push routing change).** This is the issue's
   minimum ask ("a cheap safety net regardless of whether the Out root cause is ever fully
   understood") and is strictly simpler. Rejected as the sole fix because it still lets the
   *first* live-push delivery misfile the command and leaves the owner waiting up to 5 seconds
   (`savedHistoryInterval`) for `pollSavedHistory` to self-heal, and it still leaves a spurious
   `EventKindPrivateMessage`/self-conversation/agent-job row behind as a side effect of the
   original misclassification (see change 1's "secondary benefit" above). Since the live-push
   routing fix is simple, requires no new invariant beyond one already documented in
   `classifySavedCommand`'s own comment, and is strictly more correct, doing only the safety net
   was rejected in favor of doing both.
2. **Root-cause and fix the gotd/Telegram `Out` unreliability itself.** This is the issue's other
   named fix direction. Rejected as the primary fix for this proposal: the issue's own "Root
   cause -- not yet found" section lists three unconfirmed candidate explanations (compact update
   reconstruction, multi-session sync timing, `getDifference` gap-recovery sharing code with the
   live stream), any of which could require a gotd upstream investigation or patch with unknown
   timeline. `classifySavedCommand`'s existing authorship checks make trusting `Out` for Saved
   Messages unnecessary in the first place, so this proposal routes around the problem instead
   of solving it. Root-causing remains valuable for the *general* DM case (see requirements.md's
   out-of-scope section) and is left as a follow-up informed by the new diagnostic logging.
3. **Add a `(event_id, kind)` composite unique index / new column instead of folding `kind` into
   the `event_id` string.** Rejected: it requires an actual schema migration
   (`internal/db/agent_schema.go` plus whatever migration-runner convention the repo uses),
   touches more call sites (`InsertIncomingEvent`, `InsertEventEnqueueJobAndTouch`,
   `GetIncomingEvent`, and the `agent_jobs` table's own `event_id`-keyed `ON CONFLICT`), and buys
   nothing the string-based discriminator doesn't already provide, since every current caller of
   `GetIncomingEvent`/`InsertIncomingEvent` already has `Kind` in hand when it needs the id. The
   string-based fix is a single-file, single-function-signature change.

## Platform impact

- **Migrations:** none. `event_id` stays a `TEXT` column; the unique index is unchanged.
- **Backward compatibility:** old-format `event_id` rows already in any environment's
  `incoming_events`/`agent_jobs` tables are untouched and continue to dedup correctly against
  themselves (nothing re-derives or re-matches an old id against the new format). No consumer
  parses the internal structure of `event_id` beyond the `evt:v1:...:e<ts>:<hash>` edit-suffix
  check already asserted by `TestExtractMessage_EditGetsDistinctEventID`
  (`strings.HasPrefix(got.Event.EventID, "evt:v1:100:555:42:e2000:")`), which the implementer
  must update to match the new kind-qualified prefix.
- **Resource impact:** negligible. One extra short string segment per `event_id`; one new
  `slog.Debug` call per live update (no-op at non-debug log levels).
- **Risks + mitigations:**
  - *Risk:* reordering the self-peer check in `ExtractMessage` changes behavior for a message
    with `PeerID == selfTGID` and `Out == true` that used to reach the `EventKindOwnerOutgoing`
    path. Reading the current code shows this was never reachable: the existing `if msg.Out`
    branch already special-cased `peerUser.UserID == selfTGID` to call `classifySavedCommand`
    before falling to the generic owner-outgoing `ev := db.IncomingEvent{...}` construction, so
    self-peer messages never produced `EventKindOwnerOutgoing` before this change either.
    Mitigation: the existing test `TestExtractMessage_SavedCommandAndOwnerTakeover` already
    asserts `EventKindOwnerOutgoing` only for `PeerID: recruit` (a non-self peer), so this is
    covered by (and must keep passing under) the existing suite.
  - *Risk:* changing `eventIDForMessage`'s signature is a breaking change to every direct caller,
    including test files that construct expected ids by hand (`extract_test.go`,
    `history_test.go`'s `TestPollSavedHistory_RoutesCommandWithOutFalse`). Mitigation: this is a
    small, self-contained package (`internal/agent/listener`); tasks.md enumerates every call
    site to update, and `go build ./...` will fail loudly on any signature mismatch left behind.
  - *Risk:* a message could theoretically have `PeerID == selfTGID` without being a real Saved
    Messages item in some edge case not yet observed. Mitigation: `classifySavedCommand`'s own
    checks (`GetFwdFrom`, `GetSavedPeerID`, `GetFromID`) are unchanged and still reject anything
    that is not a direct, non-forwarded, self-authored message before it can be persisted or
    routed -- routing self-peer messages there unconditionally does not weaken those checks, it
    only removes the redundant, unreliable `Out` pre-filter in front of them.
