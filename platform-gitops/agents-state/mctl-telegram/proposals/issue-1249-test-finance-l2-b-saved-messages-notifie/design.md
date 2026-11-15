# Design: issue-1249-test-finance-l2-b-saved-messages-notifie

## Current state
Grounded in the clone at `361c4fe` (main, after the release-please merge #1248). The implementer must re-pin against whatever main is at implementation time and record that SHA, not this one.

Listener (`internal/agent/listener`):
- `listener.go`: `Listener.dispatcherFor(acct)` builds a `tg.UpdateDispatcher`. `OnNewMessage` and `OnEditMessage` call `onMessage`, and `OnDeleteMessages` calls `onDelete`. In production it is wrapped in `updates.Manager` (`SetAccountProfile`). `RunFor` calls `a.mgr.Reset()` then `mgr.Run` on every pool reconnect, and `runWithPoller` runs the Saved Messages history poller beside it.
- `onMessage`: (1) consumes agent-send markers (`consumeSent`, `MatchUnconfirmedAgentSend`); (2) calls `ExtractMessage`; (3) applies `senderAllowed` and `IsDialogHidden` (Saved Messages commands are exempt from hiding); (4) calls `persistExtracted`, which serializes saved commands on `account.savedCommandMu`.
- `persist` for `db.EventKindSavedCommand` checks `GetIncomingEvent(EventID)` first and returns early on a hit (dedupe). Otherwise it calls `Router.HandleSavedText(ctx, control.SavedMeta{...}, ex.SavedCommandText)` and only then `insertAuditEvent`. A router error leaves no audit row, so the command retries.
- `extract.go`: `ExtractMessage` routes any message whose `PeerID == PeerUser{selfTGID}` to `classifySavedCommand`, deliberately ignoring `msg.Out` (live evidence #354: `Out=false` on owner pushes). `classifySavedCommand` rejects `FwdFrom`, a foreign `SavedPeerID` and a foreign `FromID`, and keeps only text whose first field is `/mctl` (`isMCTLCommand`). The event id is `evt:v1:<self>:<self>:<msgid>`, made by `eventIDForMessage`. Messages to non-user peers (`PeerChat`/`PeerChannel`) return `ok=false`. An inbound DM from another user becomes `EventKindPrivateMessage`, which is ingested as a job and never routed to the command router.
- `history.go`: `pollSavedHistory` reads `GetSavedCommandCursor`. The first poll only sets a baseline (`initializeSavedHistoryCursor`, no replay). Later polls fetch `MessagesGetHistory(InputPeerSelf, MinID=cursor)`, sort ascending, run `ExtractSavedHistoryMessage` → `persistExtracted`, and advance `AdvanceSavedCommandCursor` per message. They return before advancing past a command whose routing failed.
- Existing non-tagged tests already provide reusable fakes in package `listener`: `newTestListener`, `newListenerTestStore` (in-memory SQLite plus `db.MigrateCached`), `fakeSavedHistoryAPI`, `capturedSelfSender`, `notFoundApprover`, `savedHistoryMessage`, `ents`, and constants `selfTG=100`, `ownerUID=7`, `recruit=555` (`extract_test.go`, `history_test.go`). Related existing coverage: `TestPollSavedHistory_PushAndHistoryRouteOnce`, `TestPollSavedHistory_RoutesCommandWithOutFalse`, `TestPollSavedHistory_PersistedCursorAvoidsReplayAfterRestart`. The L2 slice re-asserts those boundaries through the real `control.Router` instead of `recordingRouter`, and emits `L2RESULT` rows.

Control (`internal/agent/control`):
- `command.go`: `ParseCommand` is pure and case-insensitive. `CmdStatus` is a real, existing owner verb. No finance verb exists, and none is invented.
- `router.go`: `NewRouter(store, executor, notifier)`. `HandleSavedText` replies with `unknownCommandReply` on parse errors. `handleStatus` replies with mode, paused state and limits through `Notifier.Reply`. The Router has no `GlobalKill` field.
- `notifier.go`: `SelfSender{SendToSelf, SendToSelfWithRandomID}` and optional `SelfDeliveryLocator`. `Notifier.Reply` calls `Sender.SendToSelf` with no kill-switch check. `Notifier.DeliverPending`:
  1. Returns immediately if `GlobalKill()` is true, leaving rows pending.
  2. Calls `ListPendingOwnerNotifications(50)`, which is system-wide, ordered by `created_at`, and skips claimed rows.
  3. Calls `ClaimOwnerNotification(userID, id, candidate, lease)`, which persists `random_id` once via `COALESCE`.
  4. Calls `format`, then `SendToSelfWithRandomID(notif.UserID, randomID, text)`. `executor.ErrAlreadyDelivered` is treated as delivered.
  5. Calls `MarkOwnerNotificationSent` (compare-and-set from pending).
  There is **no check of `AgentProfile.Mode` and no session-validity check** at delivery time. In production, revocation is enforced only beneath the `SelfSender`: `cmd/server/agentwiring.go` `poolSelfSender` → `ClientPool.Borrow` → `Store.CheckSessionValid` (`internal/telegram/clientpool.go:254`).
- `db/agent_domain.go`: `AgentModeObserve`, `AgentModeGuarded`, `AgentModeOff`. `db/store.go:1132` `RevokeActiveSession`.
- Existing helpers in package `control`: `newTestRouter` (in-memory SQLite, `crypto.New(testKey())`, observe-mode profile), `fakeSelfSender`, `fakeApprover` (`router_test.go`). Related existing tests: `TestNotifier_DeliverPending_KillSwitchSilencesQueuedDelivery`, `TestNotifier_DeliverPending_UsesAndPersistsRandomID`, `notifier_duplicate_test.go`.
- `cmd/server/main.go:269-296`: `agentGlobalKill := func() bool { return cfg.AgentKillSwitch }`, wired into `executor.New` and `agentNotifier.GlobalKill`, but not into `Router`/`Reply`.

PR #1247 (read with `gh pr view 1247`): OPEN, head `4aad2920482f005af28d0996d1c4b19882af4f8b`. It adds only `internal/agent/policy/l2finance_test.go`, `internal/agent/policy/l2finance_result_test.go` (helpers `l2Record` and `expectGap`, with hardcoded `rev=248db4f`) and `docs/reports/finance-assistant-l2-results.md`. That report states that the listener and control cases are not written. The repo has no other `l2finance` tag today. Existing build tags in tests are `livetg`, `smoke` and OS tags.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: image tag `0.137.0`, `AGENT_ENABLED: "true"`, `AGENT_KILL_SWITCH: "false"`. This confirms the notifier and kill-switch paths are live in production. This slice changes nothing deployed.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`: tag `main-193dd9c`, `AGENT_ENABLED: "true"`, `AGENT_KILL_SWITCH: "false"`.
- `gh pr view 1247 -R mctlhq/mctl-telegram`: state OPEN, 3 files, as above.
- mctl MCP tools were not called. They are not needed for a test-only change, and the deployed config above was read from gitops directly. DevLoop liveness for `dev-loop-mctlhq-mctl-telegram-1244` was **not observed** in this run (see Open questions in requirements.md). Its ownership is taken from the issue text.

## Proposed solution
Add build-tagged test files only. They are invisible to the default `go test ./...` and to the production binary.

### Files (all new, all starting with `//go:build l2finance`)
1. `internal/agent/listener/l2finance_harness_test.go`: package `listener`. Contains:
   - `l2Record(t, id, outcome, evidence)`, `expectGap(t, id, observed, evidence)` and the four outcome constants, mirroring #1247's shape. The revision is read from `L2FINANCE_SOURCE_REV`, and the run fails if that value is missing or not 40-hex. Test binaries carry no VCS stamp (`debug.ReadBuildInfo` has no `vcs.revision` under `go test`), so the env var is the honest source.
   - `TestMain`, which installs an offline guard. It replaces `net.DefaultResolver` with `PreferGo: true` plus a `Dial` that refuses every address. It replaces `http.DefaultTransport`'s `DialContext` with one that allows only loopback IPs and Unix sockets and returns `errL2ExternalDial` otherwise. It also unsets `TG_API_ID`, `TG_API_HASH` and `DATABASE_URL` for the process.
   - `l2NewHarness(t)`: an in-memory store via the existing `newListenerTestStore`, owner Alice (`EnsureUser`, observe-mode `AgentProfile`), `selfTG=100`, and a real `control.NewRouter(store, notFoundApprover{}, control.NewNotifier(store, sink))`. `sink` is an `l2SelfSink` that records `(userID, randomID, text)`. A separate `l2PeerSink` exists only so M3 has something to leak into.
   - Assertion helpers that **return an error instead of failing the test**: `l2CheckRoutedOnce(h, wantReplies int) error`, `l2CheckNotRouted(h) error`, `l2CheckSavedEvents(h, want int) error`. The real cases wrap them with `t.Fatal`, and the M-controls assert that they return non-nil.
2. `internal/agent/listener/l2finance_listener_test.go`: cases T1, T2, T4, T5.1, T5.3, T6 and M1.
3. `internal/agent/control/l2finance_harness_test.go`: package `control`. Contains the same helper and offline guard (duplicated, roughly 60 lines, because test helpers cannot cross packages without production source). Also contains `l2NotifierHarness` with Alice and Carol as two owners, `l2SelfSink`, `l2PeerSink`, and the helpers `l2CheckOnlyOwnUser`, `l2CheckNoSend` and `l2CheckNoPeerSink`, all returning errors.
4. `internal/agent/control/l2finance_notifier_test.go`: notifier cases T1, T3, T5.2, T8 and controls M2, M3.
5. `docs/reports/finance-assistant-l2-slice-b.md`: a slice-specific addendum. It holds the command, the pinned SHA, the case table with observed outcomes copied from the run, and the gate statement. It never edits #1247's report.

Every test function is named `TestL2Finance_<case>`, so `-run L2Finance` selects exactly this slice plus #1247's policy cases.

### Case table (expected classification from code reading; the run is authoritative)
| id | seam | assertion | expected |
| --- | --- | --- | --- |
| T1.listener_status | `dispatcherFor(acct).Handle(ctx, &tg.Updates{UpdateNewMessage{Message: &tg.Message{ID:10, Out:true, PeerID:PeerUser{selfTG}, Message:"/mctl status"}}})` through the real Router | 1 reply on `l2SelfSink` for Alice containing `Mode: observe`; 1 `saved_command` event; `l2PeerSink` empty | PASS |
| T1.notifier_self_only | `DeliverPending` with a summary row | send only via `SendToSelfWithRandomID`; peer sink empty | PASS |
| T2.bob_dm | `onMessage` with a DM from Bob (`PeerID:PeerUser{600}`, text `/mctl status`) | router not called; no `saved_command` event (a `private_message` event is expected and recorded as evidence) | PASS |
| T2.spoof_from | Saved Messages peer with `FromID:PeerUser{600}` | not routed | PASS |
| T4.group_chat / T4.channel | `PeerChat{1}` / `PeerChannel{2}` with `/mctl status`, `Out` true and false | not routed, no event | PASS |
| T4.forwarded | Saved Messages peer with `FwdFrom` set | not routed | PASS |
| T4.saved_peer | `SavedPeerID:PeerUser{600}` | not routed | PASS |
| T5.1.push_then_history | push id 20 then `pollSavedHistory` returns id 20 (cursor seeded at 19) | 1 reply total; cursor = 20 | PASS |
| T5.3.cursor_monotonic | history returns 21 (note), 22 (`/mctl status`), 23 (`/mctl status`) with the sink failing on the first send of 22 | cursor stops at 21; next tick routes 22 and 23 once each; cursor = 23; never decreases | PASS |
| T6.out_false_push | push with `Out:false` in the self dialog | routed once | PASS |
| T6.reconnect_replay | a second `Listener` built by `New` on the same store and account (simulated reconnect/restart) receives the same update again, plus the history poll | no second reply; cursor unchanged | PASS |
| T6.gap | `updates.Manager` getDifference after a real reconnect | needs a fake MTProto server; not in this slice | CANNOT-OBSERVE |
| T3.per_user | Alice and Carol each have one pending summary | each text delivered only under its own UserID | PASS |
| T3.finance_source | finance-source tagging and isolation | no such field exists | NOT-IMPLEMENTED |
| T5.2.random_id | first `SendToSelfWithRandomID` records the id and then returns an error; the lease is expired by `UPDATE owner_notifications SET claimed_until=...` in the test DB; second sweep: the sink returns `executor.ErrAlreadyDelivered` for a seen id | same `random_id` on both attempts; row `sent`; exactly one distinct id seen | PASS |
| T8.kill | `GlobalKill` true, then false | 0 sends and row pending; then 1 send | PASS |
| T8.mode_off_after_queue | row queued, profile `Mode=off`, then `DeliverPending` | the send happens | FAIL/GAP via `expectGap` |
| T8.mode_off_before_queue.delivery | profile off, row inserted directly into the store, then `DeliverPending` | the send happens; queue-time refusal is #1247's policy row and is cross-referenced, not re-claimed | FAIL/GAP via `expectGap` |
| T8.revoked_after_queue | row queued, `RevokeActiveSession`, then `DeliverPending` | the Notifier calls the sink (no Notifier-level fence) | FAIL/GAP via `expectGap` |
| T8.revoked_pool_fence | `ClientPool.Borrow` → `CheckSessionValid` | outside the fake boundary | CANNOT-OBSERVE |
| T8.reply_kill | `GlobalKill` true, `Router.HandleSavedText("/mctl status")` | the Reply is sent | FAIL/GAP via `expectGap` (see Open questions) |

### Negative controls (inside the test harness only)
- **M1, classifier bypass**: build an `Extracted{Event: Kind saved_command, ChatTGID: 600, SenderTGID: 600, ...; SavedCommandText:"/mctl status"}` by hand for Bob's DM and call `l.persistExtracted`. This skips `ExtractMessage`/`classifySavedCommand`, so the real Router replies. The test requires `l2CheckNotRouted` (the T2 helper) to return non-nil.
- **M2, kill hook omitted**: the harness holds `killOn := true`, but builds the Notifier with `GlobalKill = nil` and calls `DeliverPending`. The test requires `l2CheckNoSend` (the T8.kill helper) to return non-nil.
- **M3, peer leak**: wrap `l2SelfSink` in `l2LeakySink`, which also appends each text to `l2PeerSink`, then run the T1/T3 delivery. The test requires `l2CheckNoPeerSink` to return non-nil.

Each control passes only when the helper detects the leak. A helper that returns nil under mutation fails the run with "negative control Mx not detected". Each control emits `L2RESULT id=Mx outcome=PASS evidence=detected` on success. None of these are tautological: each mutation drives real production code (`persist`, `Router`, `DeliverPending`) to produce a real observable output, and the assertion reads only those outputs.

### Offline proof
`TestL2Finance_OfflineGuard` dials `192.0.2.1:443` through `http.DefaultTransport` and resolves `example.invalid` through `net.DefaultResolver`. Both must fail with `errL2ExternalDial`, and a dial to an `httptest.NewServer` loopback address must succeed. No test constructs a gotd client. The listener receives `tg.UpdatesClass` values directly, and the history poller gets `fakeSavedHistoryAPI`.

### Commands
```
L2FINANCE_SOURCE_REV=$(git rev-parse HEAD) go test -tags l2finance -count=1 -run L2Finance -v ./internal/agent/listener/ ./internal/agent/control/ | grep L2RESULT
go vet -tags l2finance ./internal/agent/listener/ ./internal/agent/control/
go test ./...   # unchanged; the tagged files are excluded
```

## AMEND: evidence provenance and boundary limitations

**Two-layer offline proof:** the listener/control test harness must
construct no network-enabled Telegram clients and use only fake
`SelfSender`, fake saved history and synthetic identities. Its
`TestMain` hooks for `http.DefaultTransport` and
`net.DefaultResolver` are useful negative controls, but do not
intercept arbitrary `net.Dialer`, custom transports or gotd internals.
Document the tested dial paths and their limitations; record
`CANNOT-OBSERVE` wherever a system-wide no-egress guarantee is
unavailable. Do not initiate external traffic to test the limitation.
A loopback `httptest` server remains allowed.

**Source and stage binding:** after #1247's partial merge and lifecycle
release, pin `main` again, then feed its actual SHA into
`L2FINANCE_SOURCE_REV` at test execution and put it on every row of
the addendum. Include #1247's final merge SHA, the fresh #1249
proposal digest/approval reference, exact `-race -count=1` tagged
commands and negative-control outcomes. Record `harness_status` as
distinct from the perpetual `FINANCE_SECURITY_GATE=BLOCKED` for this
incomplete suite; this is a report-only bridge to #1251, not a
production permission.

## Alternatives
- **Extend #1247's branch or helpers.** Rejected: that branch is owned by another DevLoop, and the issue forbids concurrent edits of the canonical report. Adding a shared non-test helper package would be production source.
- **Run the listener through a real `updates.Manager` against a fake MTProto server (`gotd/td` `tgtest`).** This would make T6.gap observable, but it adds a large, fragile harness and pulls in crypto handshakes. Deferred: T6.gap is recorded CANNOT-OBSERVE.
- **Use mocked command classification (a `recordingRouter`, as in existing tests).** Rejected by the issue ("do not mock the actual command classifier"), and it would make M1 tautological.
- **Fix the mode/revocation and Reply kill gaps in the same PR.** Rejected: the scope is test-only. `expectGap` makes a later fix visible by failing the gap test, which forces a reviewed rubric update.

## Platform impact
- No migrations, no production code, no config or deployment changes. The default build and `go test ./...` are unaffected because every new file is tag-gated. CI does not run the tag unless someone adds a job, and adding one is out of scope.
- Resource impact: an in-memory SQLite per test and well under a second per case. Nothing changes at runtime.
- Risks:
  - Name collisions with existing package-level test symbols. Mitigated with an `l2` prefix on every identifier, and `go vet -tags l2finance` in the DoD.
  - Shared-cache in-memory DBs across tests. `newListenerTestStore` already uses unique names. The control harness must use a unique `file:l2_<nanos>?mode=memory&cache=shared` DSN rather than `newTestRouter`'s fixed `file::memory:?cache=shared`.
  - Global `http.DefaultTransport`/`net.DefaultResolver` mutation is process-wide but limited to the tagged test binary.
  - Misreading as gate promotion. The addendum and every run header print `FINANCE_SECURITY_GATE=BLOCKED`.
  - Sequencing: implementation must wait for #1247's disposition and a fresh approval of this exact proposal.
