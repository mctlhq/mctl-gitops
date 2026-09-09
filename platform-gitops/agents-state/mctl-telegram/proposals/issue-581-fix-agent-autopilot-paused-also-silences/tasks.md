# Tasks: issue-581-fix-agent-autopilot-paused-also-silences

Phase A (tasks 1-3, T1-T5, T7) is the minimal correctness fix and is
independently shippable. Phase B (tasks 4-6, T6) adds the deterministic
pause notice. Phase C (task 7) is documentation. See `design.md` for the
option analysis the operator approves at proposal time.

## Phase A - policy ordering

- [ ] 1. In `internal/agent/policy/policy.go`, move the owner-facing
      short-circuit (`:317-319`) to sit immediately after the `Profile.Mode`
      switch (`:300-306`) and immediately before the `AutopilotPaused` check
      (`:307-309`). No other statement moves. — DoD: `go build ./...` passes;
      `Evaluate` still performs no I/O and takes no new `Input` field;
      `git diff` on the file is a block move plus a comment rewrite and
      nothing else.
- [ ] 2. Rewrite the contract comment at `policy.go:310-316` so it describes
      the new ordering accurately: owner-facing actions must clear the kill
      switch and the mode gate, are exempt from the autopilot-pause gate, and
      are exempt from every per-conversation gate below. Argue the pause vs.
      kill-switch/mode distinction in one or two sentences (see `design.md`,
      "Why `mode = off` must stay above the carve-out"). (depends on 1) —
      DoD: the comment no longer says owner-facing actions must clear
      "autopilot pause"; a reader can derive the decision table in
      `design.md` from the comment alone.
- [ ] 3. Update the now-stale comment in
      `internal/agentapi/actions.go:439-446`, which asserts that a `Deny` at
      `handleOwnerFacing` "can now only come from one of those account-wide
      gates (kill switch, mode==off, autopilot paused)". Drop
      autopilot pause from that list. (depends on 1) — DoD: no comment in
      `internal/agentapi` claims autopilot pause denies owner-facing actions.

## Phase B - deterministic pause notice for denied replies

- [ ] 4. Add a `Gate` string type to `internal/agent/policy/policy.go` with
      constants `GateNone` (""), `GateKillSwitch`, `GateModeOff`,
      `GateAutopilotPaused`, and a `Gate Gate` field on `Result`. Populate it
      only in the three account-wide deny branches; leave it zero everywhere
      else. `deny()` keeps its current signature; add a small
      `denyGate(gate, reasons...)` helper rather than changing every caller.
      (depends on 1) — DoD: `policy.Input` is unchanged; every existing
      table case in `policy_test.go` compiles and passes with no edit;
      `Evaluate` remains pure.
- [ ] 5. In `internal/agentapi/actions.go` `handleProposeReply`, in the
      `case policy.Deny` branch, when `result.Gate ==
      policy.GateAutopilotPaused`, call `Store.InsertOwnerNotification` with
      `Kind: db.NotificationAlert`, `ActionID:` the denied action id, and a
      short body naming the conversation and the reason. The body must NOT
      contain the draft text, a phone number, or session material. (depends
      on 4) — DoD: a pause-denied `propose_reply` returns 200 with
      `decision: "deny"` and leaves exactly one pending `owner_notifications`
      row of kind `alert` linked to that action id.
- [ ] 6. Make the enqueue in task 5 best-effort: on error, `logHandlerErr`
      with `action_id`/`user_id` only and continue, unlike the approval-code
      notification at `actions.go:284-296` which must fail the request.
      Document why in a comment. (depends on 5) — DoD: an injected
      `InsertOwnerNotification` failure still returns 200 with the deny
      decision; no message body reaches any log line.

## Phase C - documentation

- [ ] 7. Update `docs/runbook.md`, "Communication Agent operations"
      (`##` at `:142`): (a) fix the "three independent containment controls"
      lead-in at `:144` that is followed by four bullets and by "all four
      controls together" at `:155`; (b) amend the `autopilot_paused` bullet
      at `:150` and the config-table row at `:209` to state that pause stops
      recruiter-facing replies but not owner notifications; (c) add a
      paragraph after `:156`, before the `###` at `:158`, stating what an
      operator should expect from a paused account — replies denied and
      recorded in `agent_actions` with
      `policy_reasons="autopilot paused for this account"`, owner Saved
      Messages continuing, and total silence meaning `AGENT_KILL_SWITCH`,
      `mode=off`, or a disabled listener rather than a pause. Cross-reference
      `docs/reports/communication-agent-c1.md:261-275`. (depends on 1) —
      DoD: an operator reading only the runbook can distinguish paused from
      idle without opening the database.
- [ ] 8. Optional, operator's call: add one clause to the `/mctl pause`
      confirmation text at `internal/agent/control/router.go:292` noting that
      notifications continue while paused. (depends on 1) — DoD:
      `TestRouter_Pause_SetsAutopilotPaused`
      (`internal/agent/control/router_test.go:202`) still passes; if it
      asserts on the reply text, update that assertion in the same commit.

## Tests

All policy tests call `Evaluate` directly, never through a wrapper, per the
issue's instruction. Every new test carries a comment naming issue #581 and
`docs/reports/communication-agent-c1.md`, following this package's existing
convention of citing the finding each test guards.

- [ ] T1. Move the `{"autopilot paused", ...}` case out of
      `TestEvaluate_OwnerFacingStillDeniedByAccountWideGates`
      (`internal/agent/policy/policy_test.go:297`). This is the ONE
      deliberate edit to an existing case — see `requirements.md` open
      question 1. The remaining `global kill` and `mode off` cases stay
      exactly as they are. — DoD: the test's name still matches what it
      asserts; a comment records that the pause case moved to T2 and why.
- [ ] T2. New table-driven `TestEvaluate_OwnerFacingAllowedWhilePaused` in
      `policy_test.go`: for each of `db.ActionTypeOwnerSummary` and
      `db.ActionTypeOwnerApproval`, with `Profile.AutopilotPaused = true` and
      no other gate set, assert `Allow`. — DoD: fails on `main`, passes after
      task 1.
- [ ] T3. New table-driven `TestEvaluate_AccountWideGatePrecedence` pinning
      all three gates' relative semantics for all three action types
      (`ActionTypeReply`, `ActionTypeOwnerSummary`, `ActionTypeOwnerApproval`)
      across the combinations: kill only, mode-off only, paused only, kill +
      paused, mode-off + paused. Assert the expected `Decision` and, for the
      combined cases, that the reported reason is the outermost gate's
      (kill switch beats pause; mode-off beats pause). — DoD: the matrix in
      `design.md`'s "Phase A" section is reproducible from this test alone;
      the three gates' ordering is pinned rather than incidental.
- [ ] T4. `internal/agentapi/server_test.go`: new
      `TestHandleOwnerFacing_PausedAccountStillNotifiesOwner`, modelled on
      `TestHandleOwnerFacing_KillSwitchBlocksNotification` (`:1018`). Seed a
      profile via `h.seedProfile(db.AgentModeObserve)` then
      `h.store.SetAgentAutopilotPaused(ctx, h.userID, true)`; POST
      `/notify/summary`; assert 200, `decision == "allow"`, non-zero
      `notification_id`, and `action.Status == db.ActionExecuted`. Repeat for
      `/actions/request_owner_approval`. — DoD: this is the test that proves
      the owner-facing action is not silently dropped while paused (see
      `requirements.md` open question 4 on why it lives here and not in
      `internal/agent/executor`). Fails on `main`, passes after task 1.
- [ ] T5. `internal/agent/executor/executor_test.go`: new
      `TestExecutor_Approve_AutopilotPausedDeniesAtSendTime`, modelled on
      `TestExecutor_Approve_KillSwitchDeniesAtSendTime` (`:331`) and
      `TestExecutor_Approve_TakeoverDeniesAtSendTime` (`:356`). Seed a
      pending approval via `seedPendingApproval`, call
      `store.SetAgentAutopilotPaused(ctx, uid, true)`, call `exec.Approve`,
      then assert `action.Status == db.ActionDenied`, `len(sender.calls) ==
      0`, and that the error text contains `autopilot paused for this
      account`. — DoD: pins acceptance criterion 1 (an autonomous reply is
      still refused while paused) at the executor layer; passes both before
      and after the change, and is expected to — it is a regression guard on
      the half that must NOT move, not evidence of the fix.
- [ ] T6. `internal/agentapi/server_test.go`: new
      `TestProposeReply_PausedAccountQueuesOwnerAlert` — paused profile,
      seeded conversation, POST `/actions/propose_reply`; assert 200 with
      `decision: "deny"`, exactly one pending `owner_notifications` row of
      kind `db.NotificationAlert` linked to the denied action, and that the
      stored body contains neither the draft text nor a peer phone number.
      Then replay the identical job-tied request and assert the row count is
      still one (the `action_id` unique partial index). Also assert that a
      kill-switch deny and a `mode=off` deny queue NO alert. (depends on
      tasks 4-6) — DoD: fails on `main`, passes after Phase B.
- [ ] T7. **Mutation check — required, not optional.** Revert task 1 alone
      (restore the original statement order in `policy.go`, keep every test)
      and confirm T2, T3's owner-facing-while-paused rows, and T4 all go
      RED. Then revert task 5 alone and confirm T6 goes RED. Restore. — DoD:
      the revert-and-fail run is recorded in the PR description with the
      failing test names, per the issue's "validate the tests, do not just
      add them".
- [ ] T8. Full gate: `go build ./...`, `go vet ./...`, `golangci-lint run`,
      `go test ./...`, `gofmt -l .` clean. — DoD: green, and the only
      pre-existing test file with a modified case is
      `internal/agent/policy/policy_test.go` (the single move in T1).

## Rollback

Every phase is independently revertible and nothing is persisted that a
revert would strand.

- **Phase A** is a pure statement reorder inside a pure function. `git
  revert` of that commit restores the previous ordering exactly. There is no
  schema change, no config flag, and no persisted state whose meaning
  depends on the new ordering. Owner-facing `agent_actions` rows written
  while the fix was live remain valid `executed` rows; already-queued
  `owner_notifications` rows keep delivering through the unchanged notifier.
- **Phase B** reverts by dropping the `handleProposeReply` enqueue (task 5).
  The `policy.Result.Gate` field can be left in place harmlessly if only the
  behaviour needs backing out. Any `owner_notifications` rows of kind
  `alert` already queued deliver normally or age out through
  `MaxPendingAge`/`MarkOwnerNotificationFailed`
  (`internal/agent/control/notifier.go:70-75`); none of them carry an
  approval code, so nothing becomes unactionable.
- **Operational stop-gap while a revert ships.** Setting
  `AGENT_KILL_SWITCH=true` restores the old total-silence behaviour
  immediately for every account, at both the policy layer and
  `DeliverPending` (`notifier.go:133-139`). For a single noisy account,
  `mode=off` via the admin profile update
  (`internal/agentapi/profilehandler.go:149`) has the same effect without a
  redeploy.
- **Docs.** Task 7's runbook edit must be reverted together with Phase A, or
  the runbook will describe behaviour the code no longer has — the exact
  divergence this issue exists to close.
