# Tasks: issue-354-saved-messages-mctl-commands-can-be-sile

- [ ] 1. Reorder `ExtractMessage` in `internal/agent/listener/extract.go` so any message with
      `PeerID == selfTGID` is routed to `classifySavedCommand` unconditionally, before the
      `msg.Out` branch, removing the now-dead self-peer special case inside `if msg.Out`. —
      DoD: `ExtractMessage` no longer reads `msg.Out` anywhere before deciding whether a
      self-peer message is a saved command; `go build ./...` passes; the doc comment on
      `ExtractMessage` and on `classifySavedCommand` (which currently says "the live push
      path's caller ... has already gated on Out == true before reaching here") is updated to
      reflect that the caller no longer gates on `Out` at all.
- [ ] 2. Add a `kind string` parameter to `eventIDForMessage` in `extract.go` and update all
      three call sites (`EventKindOwnerOutgoing` branch, generic inbound/edit branch,
      `classifySavedCommand`) to pass their respective `db.EventKind*` constant, folding it into
      the returned string (e.g. `"evt:v1:" + kind + ":" + accountTGID + ":" + chatID + ":" +
      messageID[...]`) (depends on 1, same file). — DoD: two `IncomingEvent`s with identical
      `(accountTGID, chatID, messageID, editDate)` but different `Kind` never produce the same
      `event_id`; `go build ./...` passes.
- [ ] 3. Add the `slog.Debug` diagnostic log call at `ExtractMessage`'s entry (or immediately
      before it in `onMessage`, `internal/agent/listener/listener.go`), logging message id,
      is-edit, `msg.Out`, and resolved sender id only — no message body, no phone number, no
      session material (depends on 1). — DoD: grep of `internal/audit/redact.go`'s
      `sensitiveKeys` confirms none of the logged keys collide with anything requiring
      redaction (they don't carry free text); a manual review confirms `msg.Message` is never
      passed to the log call.
- [ ] 4. Update every existing test in `internal/agent/listener/extract_test.go` and
      `internal/agent/listener/history_test.go` that hardcodes the old `event_id` format
      (`evt:v1:100:555:42`, the `"evt:v1:100:555:42:e2000:"` prefix check, and
      `history_test.go`'s direct `eventIDForMessage(acct.tgID, acct.tgID, 101, 0, "...")` call
      in `TestPollSavedHistory_RoutesCommandWithOutFalse`) to the new kind-qualified format
      (depends on 2). — DoD: `go test ./internal/agent/listener/...` passes.
- [ ] 5. Add a new regression test mirroring `TestExtractMessage_SavedCommandAndOwnerTakeover`
      but with `Out: false` on the Saved Messages command message, asserting
      `Kind == db.EventKindSavedCommand` and `SavedCommandText` is populated on the first call
      to `ExtractMessage` (no poller involved) — this is the exact scenario from the issue's
      live evidence (depends on 1). — DoD: the new test fails on the pre-fix code (verify by
      temporarily reverting task 1's change locally) and passes after it.
- [ ] 6. Add a new regression test alongside `TestPollSavedHistory_PushAndHistoryRouteOnce`
      that races `onMessage` (simulating live push with `Out: false`) against `pollSavedHistory`
      for the same Saved Messages command message id, asserting the router is called exactly
      once (depends on 1, 2, 4). — DoD: the test passes deterministically across repeated `go
      test -run TestPollSavedHistory -count=20 ./internal/agent/listener/...` runs (guards
      against a flaky race in the new code path).
- [ ] 7. Run the full verification suite required by `CONTRIBUTING.md`: `go fmt ./...`,
      `go vet ./...`, `go test ./...`, and `golangci-lint run` (optional but appreciated per
      CONTRIBUTING.md) (depends on 1-6). — DoD: all pass locally with zero diffs from `go fmt`.
- [ ] 8. Update `docs/reports/communication-agent-c1.md` with a new dated entry recording the
      fix (PR number once opened, merge SHA once merged) closing out the "not yet fixed" framing
      of the 2026-08-01 entry, per this repo's existing convention of durable evidence-log
      entries for the communication-agent (depends on 7). — DoD: entry added under a new dated
      heading, consistent in style with the existing 2026-07-26/2026-07-31/2026-08-01 entries;
      no message bodies, phone numbers, or credentials included.

## Tests

- [ ] T1. `TestExtractMessage_SavedCommandOutFalse` (new, task 5): a Saved Messages `/mctl`
      command with `Out: false` is classified as `EventKindSavedCommand` with
      `SavedCommandText` set, directly by `ExtractMessage` (live-push path), without touching
      `pollSavedHistory`.
- [ ] T2. `TestExtractMessage_SavedCommandAndOwnerTakeover` (existing) continues to pass
      unmodified in outcome (only `event_id` literal assertions, if any, need updating per
      task 4) — confirms `EventKindOwnerOutgoing` is still produced only for a non-self peer.
- [ ] T3. `TestExtractMessage_RejectsIndirectSavedCommands` (existing) continues to pass
      unmodified in outcome — confirms forwarded/other-saved-peer/other-author messages are
      still rejected when routed unconditionally through `classifySavedCommand`.
- [ ] T4. `TestPollSavedHistory_PushAndHistoryRouteOnce` (existing) continues to pass — confirms
      the concurrent live-push/poll race still routes the router exactly once now that both
      paths agree on `Kind` for every Saved Messages message.
- [ ] T5. New push/poll race test with `Out: false` on the push side (task 6) — the scenario
      that reproduced the issue live twice in one session.
- [ ] T6. `TestPollSavedHistory_IgnoresNonCommandsAndAdvancesCursor` and
      `TestPollSavedHistory_RouterErrorStopsCursorAndRetries` (existing) continue to pass
      unmodified — confirm the cursor-advance and router-error-retry behavior in
      `pollSavedHistory` is unaffected by the `extract.go` changes.
- [ ] T7. A unit test on `eventIDForMessage` directly (new or extending existing coverage)
      asserting that the same `(accountTGID, chatID, messageID)` with `Kind =
      EventKindPrivateMessage` vs `Kind = EventKindSavedCommand` produces two distinct strings
      — the direct regression test for the safety-net fix (task 2), independent of the
      live-push routing fix.
- [ ] T8. `go vet ./...` and `golangci-lint run` clean on the changed files.

## Rollback

The change is confined to `internal/agent/listener/extract.go` (plus the accompanying test
files) and touches no schema, no migration, and no external API/config surface — rollback is a
plain revert of the merge commit (or `git revert <sha>` per this repo's squash-merge convention
in `.claude/CLAUDE.md`) followed by a normal redeploy through the existing release-please /
`mctl-gitops` pipeline. Because no `incoming_events`/`agent_jobs` rows are migrated or backfilled
by this change, reverting is safe at any point: pre-fix and post-fix code both operate correctly
against the same table shape, and any `event_id` values written under the new kind-qualified
format simply remain valid, inert rows if the code is rolled back (they do not collide with or
block anything the old code path computes, since the old code path never generates or looks up
a kind-qualified id). No feature flag is needed given the small, self-contained blast radius;
if a staged rollout is preferred, gate deployment behind the existing preview-environment
process already described in `docs/reports/communication-agent-c1.md` (verify via a live
Saved Messages `/mctl status` round-trip in preview before promoting) rather than adding new
flag-gating code to a fix this narrow.
