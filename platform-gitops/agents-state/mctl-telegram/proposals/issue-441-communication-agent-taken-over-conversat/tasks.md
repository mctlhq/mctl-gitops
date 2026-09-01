# Tasks: issue-441-communication-agent-taken-over-conversat

- [ ] 1. Reorder `Evaluate` in `internal/agent/policy/policy.go`: move the
      `db.ActionTypeOwnerSummary` / `db.ActionTypeOwnerApproval`
      short-circuit from inside the `Action.Type` switch (current lines
      325-331) to immediately after the `Profile.AutopilotPaused` check
      (current line 309) and before the `Conversation.State` switch
      (current line 310). Leave the later `Action.Type` switch handling
      only `db.ActionTypeReply` (fall-through) and the unrecognized-type
      `default: deny(...)`. Add a comment explaining why owner-facing
      types skip `Conversation.State` and `isBlocked` but not the gates
      above them. — DoD: `policy.go` compiles, `go vet` clean, the new
      short-circuit sits between the `AutopilotPaused` check and the
      `Conversation.State` switch, and the `Action.Type` switch no longer
      mentions `db.ActionTypeOwnerSummary` / `db.ActionTypeOwnerApproval`.

- [ ] 2. Simplify `handleOwnerFacing` in `internal/agentapi/actions.go`
      (depends on 1): replace the `conv := db.Conversation{State:
      db.ConversationActive}` default (current line 418) with a plain
      zero-value `var conv db.Conversation`, since the owner-facing
      short-circuit in `Evaluate` no longer reads `Conversation.State`.
      Rewrite the explanatory comment at lines 409-417 to describe the new
      invariant ("owner-facing actions bypass conversation state
      entirely; no synthetic conversation needed") and update the comment
      at lines 439-444 to note that a `Deny` here can now only come from
      the kill switch / mode / autopilot-pause gates. — DoD: the
      `ConversationID == 0` special case is gone, `handleOwnerFacing`
      still compiles and both call sites (`handleNotifySummary`,
      `handleRequestOwnerApproval`) are unaffected in signature/behavior
      for the mode/kill-switch/autopilot-paused deny paths.

- [ ] 3. Update and extend `internal/agent/policy/policy_test.go` (depends
      on 1):
      - Change `TestEvaluate_OwnerActionsAndPeerZero`'s case at lines
        250-255 to use a non-active `Conversation.State` (e.g.
        `db.ConversationTakenOver`) instead of `db.ConversationActive`,
        and update its comment to state that owner-facing actions now
        bypass conversation state by design, not by accident of a
        zero-value dodge.
      - Add: `taken_over` / `closed` / `paused` x
        `db.ActionTypeOwnerSummary` -> `Allow`.
      - Add: `taken_over` / `closed` / `paused` x
        `db.ActionTypeOwnerApproval` -> `Allow`.
      - Add: sender in `Profile.BlockedSenders` matching
        `Conversation.PeerTGID` x owner-facing action type -> `Allow`
        (pins the `isBlocked` bypass called out in `design.md`).
      - Add: `GlobalKill == true` x owner-facing action type -> `Deny`.
      - Add: `Profile.Mode == db.AgentModeOff` x owner-facing action type
        -> `Deny`.
      - Add: `Profile.AutopilotPaused == true` x owner-facing action type
        -> `Deny`.
      — DoD: `go test ./internal/agent/policy/...` passes, including all
      new cases; removing the reorder from task 1 (temporarily, to
      sanity-check) makes at least the new `Allow` cases fail, confirming
      they actually exercise the fix.

- [ ] 4. Update or add tests in `internal/agentapi` for `handleOwnerFacing`
      covering a conversation-scoped (`ConversationID != 0`) owner
      notification against a `taken_over` conversation, asserting the HTTP
      response reflects `Decision: Allow` and an `agent_actions` row is
      persisted with `Status: db.ActionExecuted` rather than
      `db.ActionDenied` (depends on 1, 2). — DoD: a new or updated test in
      this package reproduces the exact scenario from the issue (real
      `ConversationID`, `State: db.ConversationTakenOver`, action type
      `send_owner_summary`) and asserts it is no longer silently denied.

## Tests

- [ ] T1. `go test ./internal/agent/policy/...` — all existing and new
      cases from task 3 pass.
- [ ] T2. `go test ./internal/agentapi/...` — task 4's new/updated test
      passes, and the full existing suite (including any test asserting
      the old `ConversationID == 0` synthetic-conversation comment/shape)
      still passes after task 2's simplification.
- [ ] T3. `go test ./...` — full suite green, confirming no other package
      depended on the old ordering or on `handleOwnerFacing`'s prior
      `ConversationID == 0` special case.
- [ ] T4. Manual/staging sanity check on the preview environment
      referenced in the issue (`labs/agent-worker-preview`): flip a test
      conversation to `taken_over` via the listener path, trigger a
      `send_owner_summary` job, and confirm a Saved Messages notification
      now arrives instead of being silently dropped.

## Rollback

This is a single, self-contained reordering inside `policy.Evaluate` plus a
matching simplification in `handleOwnerFacing` — no schema or data
migration is involved. To roll back:

1. Revert the commit(s) implementing tasks 1-2 (git revert of the PR that
   lands this change). This restores the prior gate ordering and the
   `ConversationID == 0` synthetic-conversation workaround exactly as they
   were.
2. No data cleanup is required: the only persisted-state effect of this
   change is that some future owner-facing `agent_actions` rows get
   `Status: db.ActionExecuted` instead of `Status: db.ActionDenied`.
   Reverting stops new rows from doing that; existing rows on either side
   remain valid historical audit records and need no correction.
3. Because `Evaluate` performs no I/O and the change touches no
   persisted schema, rollback is a plain code deploy — no coordinated
   restart order, no feature flag, and no backward-incompatible API
   change to unwind.
