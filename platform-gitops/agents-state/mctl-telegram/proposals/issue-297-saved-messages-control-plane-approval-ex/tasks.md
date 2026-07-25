# Tasks: issue-297-saved-messages-control-plane-approval-ex

- [ ] 1. Add `AGENT_PROFILE_PATH` to `internal/config/config.go` (+
      `.env.example`), following the existing `envOr`/doc-comment style
      next to `AgentEnabled`/`AgentKillSwitch`. — DoD: `Config.AgentProfilePath`
      populated from env, empty string when unset, config tests updated.

- [ ] 2. Schema: add nullable `agent_actions.random_id`,
      `agent_actions.source_event_id`, `agent_actions.approved_at` via
      `addColumnIfMissing` in `internal/db/agent_schema.go`'s `migrateAgent`
      (depends on 1 only for ordering convenience; no functional
      dependency). — DoD: migration idempotent on both SQLite and Postgres
      paths, `store_migration_test.go`-style test confirms re-running
      `Migrate` twice is a no-op.

- [ ] 3. Extend `internal/db/agent_actions.go`: widen
      `allowedActionTransitions` to add `pending_approval -> denied` and
      `approved -> denied`; add `ClaimAgentActionForSend` (mint-or-reuse
      `random_id`, CAS `approved -> executing`, no-op read on already-
      `executing`); add `InvalidateAgentAction` (CAS
      `{pending_approval, approved, executing} -> denied` with a reason);
      add `ClaimApprovedAgentActions` (SKIP LOCKED claim of
      `approved`/`executing` rows, modeled on `ClaimAgentJobs`); stamp
      `approved_at` wherever a row is inserted/transitioned directly into
      `approved` (guarded auto-approve in propose_reply, and the
      `control` router's approve handler in task 6). (depends on 2) —
      DoD: unit tests for each new method including the crash-retry
      no-op-on-executing case and the multi-source-status CAS in
      `InvalidateAgentAction`.

- [ ] 4. Extend `internal/telegram/sendself.go`: factor the send body out
      of `SendToInputPeer` so a new `SendToInputPeerWithRandomID(ctx, c,
      userID, peer, text, randomID int64)` accepts a caller-supplied
      `random_id`; `SendToInputPeer`/`SendToSelf` become thin wrappers that
      generate their own id and call it. — DoD: existing `send_test.go`/
      `send_media_test.go`-adjacent tests still pass unmodified; new test
      confirms the same `randomID` is placed on the outgoing RPC verbatim.

- [ ] 5. `internal/agent/listener`: add `tg.UpdateDeleteMessages` dispatch
      (`dispatcherFor`), a `db.EventKindMessageDelete` constant + extraction
      case in `extract.go` mirroring the existing edit case, and a
      `persist` branch that records it as an audited event. (depends on
      nothing above, but is a hard dependency of task 8's edit/delete
      invalidation) — DoD: `extract_test.go`-style unit tests for the new
      extraction path; `listener_test.go` covers the new dispatcher branch
      end-to-end against a fake update.

- [ ] 6. `internal/agent/control`: `ParseCommand` (pure, table-driven per
      the issue's exact verb list: `status|leads|show <id>|continue
      <id>|pause|takeover <id>|approve <code>|reject <code>`), `Notifier`
      (Saved Messages summary/approval formatting + send +
      mark-sent/failed), `Router` implementing `listener.CommandRouter`
      (dispatches every verb to the corresponding store method, replies via
      `Notifier`). (depends on 3 for approve/reject transitions) — DoD:
      `ParseCommand` has exhaustive table-driven tests (valid verbs, case
      variants, whitespace variants, missing args, unknown verb, non-`/mctl`
      text); `Router` has tests per verb using a fake store/notifier.

- [ ] 7. `internal/agent/profile`: YAML-backed `OwnerProfileProvider`
      satisfying `agentapi.OwnerProfileProvider`; loads
      `identity/public_profile/skills/preferences/restricted` from
      `AGENT_PROFILE_PATH`; `PublicProfile` structurally excludes
      `restricted`. (depends on 1) — DoD: unit tests cover a fixture YAML
      with all five sections and assert (a) public fields are present, (b)
      every key under `restricted` in the fixture is absent from
      `PublicProfile`'s output via a reflection/round-trip check, not a
      hand-maintained key list.

- [ ] 8. `internal/agent/executor`: poll loop implementing the send flow —
      claim, re-check policy with fresh profile/conversation, edit/delete
      invalidation via `source_event_id` + task 5's delete events,
      claim-for-send + disclosure append + `SendToInputPeerWithRandomID`,
      mark executed, `IncrementAutonomousTurns`,
      `InsertConversationMessage`. (depends on 2, 3, 4, 5) — DoD: unit
      tests for the full state machine including every case the issue
      names explicitly: kill-switch flip mid-flow, crash-and-retry-by-
      `random_id` (same id reused, no second RPC attempted when the store
      already shows `executing`), policy-changed-between-approve-and-send,
      concurrent-owner-reply-cancels-pending (via `Conversation.State`
      flipping to `taken_over` mid-loop), edit/delete-invalidates-draft.

- [ ] 9. Observability: add `AgentActionsTotal`, `AgentActionExecutingStuck`,
      `AgentApprovalLatency`, `AgentExecutorRestartsTotal` to
      `internal/metrics/metrics.go`'s Communication agent section,
      registered in `New()`. (depends on 8 for the call sites) — DoD:
      `metrics_test.go` confirms registration; executor emits each metric
      at the documented transition points.

- [ ] 10. Sweeper notification: extend `sweeper.AgentJobs` (or add a
      sibling call) so an `ExpireStaleAgentActions` expiry also triggers an
      owner notification that the draft lapsed. (depends on 6 for the
      Notifier) — DoD: test confirms one notification per newly-expired
      action, none for actions already expired on a prior tick.

- [ ] 11. Wire everything into `cmd/server/main.go`: replace the `nil`
      `CommandRouter` argument to `listener.New` with `control.Router`;
      construct `profile.OwnerProfileProvider` and call
      `agentSrv.WithProfile(...)` when `AGENT_PROFILE_PATH` is set; start
      `executor.Run` as a new background goroutine gated on
      `cfg.AgentEnabled`. (depends on 6, 7, 8) — DoD:
      `cmd/server/main_test.go`-style smoke test that the server still
      starts with `AGENT_ENABLED=false` (no behavior change) and with it
      `true` plus a profile path configured (recruiter-profile endpoint no
      longer 501s).

- [ ] 12. Audit/redaction: confirm no new log call anywhere in tasks 6-11
      emits a raw command string, draft body, or approval code; add any
      newly-introduced sensitive key names to
      `internal/audit/redact.go`'s `sensitiveKeys`. (depends on 6, 8) —
      DoD: `redact_test.go` extended with the new key(s) if any were added;
      manual grep of new packages for `slog.*` calls confirms only
      metadata (ids, statuses, kinds) is logged.

## Tests

- [ ] T1. `ParseCommand` table-driven tests: all eight verbs, case
      variants on `/mctl` and the verb, extra/missing whitespace, missing
      required arg, unknown verb, empty/whitespace-only input, non-`/mctl`
      text.
- [ ] T2. Executor state machine: crash-and-retry-by-`random_id` (row
      already `executing` at startup, same id reused, no double RPC).
- [ ] T3. Executor state machine: kill-switch flips true between approval
      and the pre-send re-check — action denied, not sent.
- [ ] T4. Executor state machine: profile/conversation state changes
      (autopilot re-paused, rate limit newly exceeded) between approval and
      send — action denied with reasons from the second `Evaluate` call,
      not the first.
- [ ] T5. Executor state machine: owner sends in the original chat (or
      issues `/mctl takeover <id>`) while an action is `pending_approval`
      or `executing` — action denied, no duplicate/late send.
- [ ] T6. Executor state machine: source incoming message edited or
      deleted after the draft was proposed but before send — action
      denied/expired with a reason; a new incoming event for the edit
      re-enters the pipeline as its own job.
- [ ] T7. `ClaimAgentActionForSend`/`InvalidateAgentAction`/
      `ClaimApprovedAgentActions` DB-layer tests (CAS correctness, SKIP
      LOCKED claim scoping) mirroring the existing `agent_actions_test.go`/
      `agent_jobs_test.go` style.
- [ ] T8. `OwnerProfileProvider` restricted-field stripping: reflection/
      round-trip test that no key under `restricted` in a fixture YAML ever
      appears in `PublicProfile`'s returned map.
- [ ] T9. Notifier formatting: approval-request message contains the draft
      text and both `/mctl approve <code>`/`/mctl reject <code>` lines;
      summary formatting round-trips through `SendToSelf`'s mocked sender.
- [ ] T10. Listener delete-message extraction/dispatch test (new, per task
      5), mirroring `extract_test.go`/`listener_test.go` conventions.
- [ ] T11. `internal/audit/redact_test.go` — any new sensitive key added by
      this work is redacted; a raw draft/command string passed through
      `RedactingHandler` never reaches the inner handler unredacted.

## Rollback

- All schema changes are additive (new nullable columns only); reverting
  the code without reverting the migration is safe — unused columns are
  simply ignored by the previous binary.
- The three new packages (`control`, `executor`, `profile`) are only
  reachable through `cmd/server/main.go`'s wiring (task 11) and through
  `AGENT_ENABLED`/`AGENT_PROFILE_PATH` gates. Rollback path: redeploy the
  prior image (or revert task 11's wiring commit) — the listener falls
  back to `Router == nil` (Saved Messages commands silently ignored, same
  as today) and `agentapi.Server.Profile == nil` (recruiter-profile
  endpoint 501s again, same as today). No data loss: `agent_actions` rows
  already `executing` at rollback time simply stop being retried until the
  executor is redeployed — they are not lost, and MTProto's `random_id`
  dedup means a subsequent redeploy can safely resume them.
- If the new listener delete-dispatcher misbehaves (e.g. false-positive
  invalidations), it can be disabled independently by reverting task 5
  alone; the executor's edit/delete check degrades to edit-only detection
  without affecting the approve/send/crash-recovery core.
- The global `AGENT_KILL_SWITCH` remains the fastest full stop for any
  autonomous send regardless of what this proposal ships, unchanged from
  today.
