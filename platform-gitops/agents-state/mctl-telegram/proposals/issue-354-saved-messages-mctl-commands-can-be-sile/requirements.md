# Stop trusting msg.Out for Saved Messages command classification, and make event_id kind-aware

## Context

`internal/agent/listener/extract.go`'s live-push classifier (`ExtractMessage`) currently
decides whether a Saved Messages message is an owner-authored `/mctl` control command by
checking `msg.Out == true` before delegating to `classifySavedCommand`. Live evidence from
2026-08-01 (issue #354, corroborated in `docs/reports/communication-agent-c1.md`'s
"2026-08-01" entry) shows Telegram's live push (`UpdateNewMessage`/`UpdateEditMessage` via
`gotd`'s `updates.Manager`) can deliver `Out == false` for a message the owner genuinely sent
to their own Saved Messages dialog. When that happens, the message falls through to the
generic inbound-message branch of `ExtractMessage` and is persisted as an ordinary
`EventKindPrivateMessage` instead of `EventKindSavedCommand`, so `control.Router.HandleSavedText`
is never invoked -- the command silently no-ops.

The 5-second `pollSavedHistory` fallback (`internal/agent/listener/history.go`) exists
specifically because `messages.getHistory` against `InputPeerSelf` is documented (in
`ExtractSavedHistoryMessage`'s doc comment) to be similarly `Out`-unreliable, so it classifies
via `classifySavedCommand` directly without gating on `Out`. It should self-heal a live-push
misclassification on its next tick -- but it cannot, because `eventIDForMessage` computes the
same dedup key (`event_id`) for a Saved Messages message regardless of which kind it was
classified as. The already-inserted, wrongly-kinded `private_message` row makes the fallback's
own `GetIncomingEvent` dedup check treat the command as already-processed, so the command is
lost permanently, not just delayed -- with no retry, no alert, and no owner-visible signal.

This matters because `/mctl approve|reject|pause|takeover|...` is the owner's only control
surface over the communication agent. A control command that can be silently and permanently
dropped undermines the whole approval-gated safety model the agent depends on (see
`docs/plans/communication-agent.md` and the C1 acceptance criteria in
`docs/reports/communication-agent-c1.md`).

## User stories

- AS the account owner I WANT every `/mctl` command I send in Saved Messages to reach
  `control.Router.HandleSavedText` on the first delivery SO THAT approvals, pauses, and
  takeovers are never silently dropped regardless of what Telegram reports in `msg.Out`.
- AS the account owner I WANT the 5-second Saved Messages poller to be able to recover any
  future misclassification of a Saved Messages message under the wrong event kind SO THAT a
  bug in live-push classification degrades to "recovered within one poll interval," never to
  "permanently and silently lost."
- AS an on-call engineer I WANT low-cardinality diagnostic context around `ExtractMessage`'s
  entry SO THAT a recurrence of Telegram/gotd `Out` unreliability (in Saved Messages or in an
  ordinary DM) can be investigated without needing another live incident to reproduce evidence
  from scratch.

## Acceptance criteria (EARS)

- WHEN a live-push update (`UpdateNewMessage` or `UpdateEditMessage`) delivers a `*tg.Message`
  whose `PeerID` is the owner's own Telegram ID (`selfTGID`), THE SYSTEM SHALL classify it via
  `classifySavedCommand` regardless of the value of `msg.Out`.
- WHEN a message classified via `classifySavedCommand` is a genuine `/mctl` command directly
  authored by the owner in their primary Saved Messages dialog, THE SYSTEM SHALL persist it as
  `EventKindSavedCommand` and invoke `control.Router.HandleSavedText` on the first live-push
  delivery, without depending on `pollSavedHistory` to reclassify it.
- WHILE a message's `PeerID` equals `selfTGID`, THE SYSTEM SHALL apply the same
  forwarded/saved-peer/from-id authorship checks `classifySavedCommand` already performs today,
  so indirect (forwarded, saved-from-elsewhere, or third-party-authored) Saved Messages content
  is still rejected exactly as it is today.
- WHEN a message with `PeerID == selfTGID` is not a `/mctl` command (an ordinary personal note,
  media, etc.), THE SYSTEM SHALL NOT persist it as `EventKindPrivateMessage`,
  `EventKindMessageEdit`, or `EventKindOwnerOutgoing` -- it remains untracked, matching today's
  behavior for `Out == true` Saved Messages notes.
- THE SYSTEM SHALL compute `event_id` such that two `IncomingEvent` rows for the same
  `(accountTGID, chatID, messageID[, editDate])` tuple but different `Kind` values never
  collide, so a future misclassification-then-reclassification of the same underlying message
  (via `pollSavedHistory` or any other reconciling path) is never blocked by the dedup guard in
  `listener.go`'s `persist` (`GetIncomingEvent` check before `Router.HandleSavedText` /
  `insertAuditEvent`).
- IF `pollSavedHistory` reclassifies a message that a prior live-push delivery already
  persisted under a different `Kind`, THEN THE SYSTEM SHALL still route it through
  `control.Router.HandleSavedText` exactly once (the existing per-`event_id` unique-index
  dedup, and the existing concurrent push/poll race test
  `TestPollSavedHistory_PushAndHistoryRouteOnce`, must continue to guarantee "exactly once,"
  not "zero times" and not "more than once").
- WHEN `ExtractMessage` is entered for a live update, THE SYSTEM SHALL emit a structured,
  low-cardinality debug-level log line containing the Telegram message id, the update kind
  (new vs. edit), `msg.Out`, and the resolved sender id -- never message body text, phone
  numbers, or session material (per `internal/audit/redact.go`'s existing constraints) -- to
  support diagnosing any future `Out`-unreliability recurrence.
- THE SYSTEM SHALL require no database schema migration and no change to the
  `incoming_events` / `agent_jobs` unique-index shape (`agent_schema.go`) to implement the
  `event_id` kind-discriminator fix.

## Out of scope

- Root-causing *why* gotd/Telegram's live push (`UpdateNewMessage`/`UpdateShortMessage`
  reconstruction, multi-session sync, `updates.Manager` gap recovery) sets `Out == false` for a
  genuine owner-authored message. This proposal removes mctl-telegram's *dependence* on `Out`
  for Saved Messages classification rather than fixing Telegram/gotd's behavior; the diagnostic
  logging acceptance criterion above is deliberately lightweight and does not require a gotd
  upgrade, patch, or vendored fix.
- Fixing `Out`-unreliability for ordinary (non-Saved-Messages) 1:1 dialogs. The owner-takeover
  path (`ExtractMessage`'s `if msg.Out` branch for a peer other than `selfTGID`, producing
  `EventKindOwnerOutgoing`) still relies on `msg.Out` and is structurally exposed to the same
  kind of misclassification risk (see design.md's "General applicability" note) -- this is
  flagged as a follow-up, not fixed here.
- Any owner-facing alert/notification when a reconciliation happens (e.g., a Telegram message
  telling the owner "your command was delayed by one poll tick"). The kind-aware `event_id` fix
  makes this a non-event in the reported scenario (the live-push fix classifies correctly on
  the first pass); a notification would only fire for hypothetical *other* future
  misclassifications this proposal cannot enumerate today.
- Backfilling or repairing the two already-mis-kinded historical rows referenced in the issue
  (`incoming_events` ids 758 and 767) -- those were already worked around live and are not
  present in any environment this proposal's tests run against.
- Changing `updates.Manager` gap-recovery (`getDifference`) behavior or the `pollSavedHistory`
  5-second interval.

## Open questions

- Whether the `event_id` format change (adding a kind discriminator) should apply uniformly to
  all four `EventKind*` values or only to the Saved Messages case. Chosen interpretation: apply
  it uniformly. Reading `extract.go` shows `chatID` is computed identically
  (`peerUser.UserID`) for `EventKindOwnerOutgoing` and `EventKindPrivateMessage`/
  `EventKindMessageEdit` in an ordinary 1:1 dialog too -- so the same collision class exists
  there if `Out` is ever wrong for a normal DM, not just for Saved Messages. A uniform,
  kind-qualified `event_id` closes that whole bug class for the cost of one shared helper
  change, versus a narrower fix that would need to be rediscovered later. Proceeding with the
  uniform fix; flagged here since the issue itself only asked for the Saved Messages case.
- Whether the temporary trace logging the issue asks for should be truly temporary (removed
  after some observation window) or a permanent low-level debug log. Chosen interpretation:
  make it a permanent `slog.Debug`-level log (near-zero cost when debug logging is off, no
  tracked removal task needed, and it remains useful if `Out`-unreliability resurfaces for
  ordinary DMs per the out-of-scope note above).
- Whether `TestPollSavedHistory_PushAndHistoryRouteOnce`'s concurrency guarantee (router called
  exactly once when live push and history poll race on the same genuine command) needs a new
  explicit regression test for the `Out == false` case specifically. Chosen interpretation: yes
  -- add one, since it is the exact race the issue's live incident hit twice in one session (see
  tasks.md T-series).
