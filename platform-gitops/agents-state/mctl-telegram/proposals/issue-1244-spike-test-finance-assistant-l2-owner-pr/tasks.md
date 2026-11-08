# Tasks: issue-1244-spike-test-finance-assistant-l2-owner-pr

Precondition: exact-content owner approval of this proposal. Only `_test.go` files with
`//go:build l2finance`, one optional workflow file and one report may be added. No non-test Go
file may change.

- [ ] 1. Re-pin the revision. Record `git rev-parse HEAD`, re-read the symbols listed in design.md
  (`sendself.go`, `extract.go`, `history.go`, `notifier.go`, `router.go`, `command.go`,
  `policy.go:414`, `actions.go handleOwnerFacing`, `binding.go enforceBinding`,
  `agent_actions.go ListPendingOwnerNotifications`) and note any drift from `248db4f`. — DoD:
  pinned SHA and drift notes in the report draft. On drift, re-derive the expected-outcome table
  before writing tests.
- [ ] 2. Pick ids. Run `git grep -n '\b<id>\b'` for each candidate id (start at 91001-91004) and
  map them to Alice, Bob, Carol and Dana. Define the synthetic marker `L2SYNTH-TXN-7f3a`. — DoD:
  the id table with grep results is in the report. No id collides with a different meaning in
  the same package.
- [ ] 3. Write per-package result helpers `l2finance_result_test.go` (`l2Record`, `expectGap`,
  `expectNotImplemented`, `cannotObserve`) in listener, control, policy, agentapi and telegram.
  (depends on 2) — DoD: each emits one `L2RESULT id= outcome= rev= evidence=` line. `expectGap`
  fails when the gap no longer reproduces.
- [ ] 4. `internal/agent/listener/l2finance_test.go`: T1/T2 intake, T4, T5.1, T5.3, T6, M1.
  (depends on 3) — DoD: cases use `newTestListener` and `fakeSavedHistoryAPI` patterns, with
  synthetic `*tg.Message`. Zero network.
- [ ] 5. `internal/agent/control/l2finance_test.go`: T1 router and sink (including `/mctl finance`
  NOT-IMPLEMENTED), T3 per-UserID delivery, T5.2 random-id reuse, T8 (kill, mode off before and
  after queue, `revoked_at` after queue), M2, M3. (depends on 3) — DoD: `peerSink` is zero in
  every non-mutation case, and the T8 post-queue cases use `expectGap`.
- [ ] 6. `internal/agent/policy/l2finance_test.go`: T7.1 stale revision -> `DenyInstallChanged`,
  T7.2 revision 0 -> `expectGap`, T9 policy view of reply/owner-summary, T10 DenyCode table.
  (depends on 3) — DoD: direct `Evaluate` table test with no mocks of `Evaluate`.
- [ ] 7. `internal/agentapi/l2finance_test.go`: T2 owner summary queued by a Bob-conversation job
  token, T3 Alice token on Carol's conversation, T7.3 job token omitting `job_id`, T9
  `propose_reply` with finance text, T10 `agent_actions` rows plus redacted slog capture, M4.
  (depends on 3) — DoD: real `httptest` server from the `server_test.go` setup, with real policy
  and store.
- [ ] 8. `internal/telegram/l2finance_test.go`: try a no-network `telegram.Options.Middlewares`
  interceptor that captures `MessagesSendMessageRequest.Peer` from `SendToSelfWithRandomID`.
  (depends on 3) — DoD: either it asserts `*tg.InputPeerSelf` with `NoWebpage` and a non-zero
  `RandomID` (PASS), or it records `CANNOT-OBSERVE` with the concrete reason. If a dial or a hang
  is possible, the test uses a context timeout and is bounded to under 5s.
- [ ] 9. Optional: `.github/workflows/l2-finance.yml`, `workflow_dispatch` only,
  `permissions: contents: read`, no secrets. It runs the tagged command and uploads the
  `L2RESULT` artifact. (depends on 4-8) — DoD: actionlint is clean, and no `pull_request` or
  `push` trigger exists.
- [ ] 10. Run locally and record the results in `docs/reports/finance-assistant-l2-results.md`.
  The report holds the pinned SHA, the exact commands, the `L2RESULT` table, the mutation table
  (all four `MUTATION-DETECTED`), the future contract tests for each `NOT-IMPLEMENTED` row, and a
  statement that #325/#1240 verdicts are unchanged and that no pilot is allowed. (depends on 4-9)
  — DoD: every T1-T10 row has exactly one outcome from the rubric, and no row is left
  unclassified.
- [ ] 11. Prove the change is limited to tests: `git diff --name-only main` shows only the
  `l2finance*_test.go` files, the optional workflow and the report. `go test -race ./...`
  (untagged) result is unchanged. `go vet -tags l2finance ./...` and
  `golangci-lint run --build-tags l2finance` are clean. (depends on 10) — DoD: command output is
  pasted into the PR description.

## AMEND tasks: hermetic execution and security-gate accounting

- [ ] 8a. Add a **test-only** network boundary for every tagged L2 package
  and fake adapter. Permit loopback `httptest` and local Unix sockets,
  but explicitly reject non-loopback outbound dials, DNS and live
  Telegram/MTProto. Assert fail-closed behavior when an external
  destination is attempted. If concrete gotd cannot be driven without
  external calls, mark the wire-layer check `CANNOT-OBSERVE`;
  do not dial. — DoD: test setup and results record the deny-egress
  method and bounded network-negative control; no real network use.
- [ ] 10a. Introduce a case-manifest-based L2 result validator in
  **test-only code**, with one classified `L2RESULT` per mandatory T1–T10
  sub-case. Validate all four outcome counts and IDs, reject missing,
  duplicate or unclassified rows, and record `harness_status` separately
  from `security_gate_status`. — DoD: `go test` exit 0 with
  expected `FAIL/GAP` produces the explicit independent
  `FINANCE_SECURITY_GATE=BLOCKED` security verdict; never a false PASS.
- [ ] 10b. Publish the independent gate status prominently in
  `docs/reports/finance-assistant-l2-results.md` and optional
  manual `workflow_dispatch` job summary and artifact. — DoD: green
  harness CI cannot hide any `FAIL/GAP`, `NOT-IMPLEMENTED`,
  `CANNOT-OBSERVE` or missing mandatory row; no production/pilot
  promotion. The L2 research PR remains separately reviewed and
  the parent #325 verdict `RESEARCH_ONLY_DEFER` unchanged.

## Tests

- [ ] T1. Owner `/mctl status` in Saved Messages (push and history) yields one router call and
  one `SendToSelf`, with zero peer sends. `/mctl finance` gets `unknownCommandReply` and is
  recorded NOT-IMPLEMENTED. Wire-level `InputPeerSelf` is PASS or CANNOT-OBSERVE.
- [ ] T2. Bob's DM finance text, `/mctl status` and `/mctl approve X` produce no saved command,
  no router call and no SelfSender call. A Bob-conversation job queueing `send_owner_summary` is
  recorded as observed (expected FAIL/GAP vs the finance contract).
- [ ] T3. An Alice token on Carol's conversation returns 404. `DeliverPending` sends each row
  under its own `UserID`. Finance source isolation is NOT-IMPLEMENTED.
- [ ] T4. `FwdFrom`, a foreign `SavedPeerID`, a foreign `FromID` and a group peer each give
  `ok=false` and no router call (push and history).
- [ ] T5. T5.1 the same event twice or push+history gives one effect. T5.2 a `DeliverPending`
  retry reuses the persisted random id and sends once. T5.3 out-of-order history with cursor
  persistence across restart gives no replay.
- [ ] T6. `Out=false` on push and on history after a fresh-Listener restart is classified once.
- [ ] T7. T7.1 stale revision gives `DenyInstallChanged`. T7.2 `InstallRevision=0` is
  `expectGap`. T7.3 a job-bound `/notify/summary` without `job_id` is `expectGap` if allowed.
- [ ] T8. GlobalKill with a queued row gives no send and the row stays pending. Mode off before
  queueing gives `DenyModeOff` and no notification. Mode off after queueing and `revoked_at` after
  queueing are `expectGap` if a send occurs.
- [ ] T9. `propose_reply` with finance text produces no immediate peer send, and the decision and
  DenyCode are recorded. Finance job kind and `never` tier are NOT-IMPLEMENTED, with the contract
  spec.
- [ ] T10. Every denial has an `agent_actions` row with `PolicyDecision`, `PolicyReasons`,
  `Status`, and a DenyCode metric. A redacted slog capture contains no `L2SYNTH-TXN-7f3a`. A
  missing field is FAIL/GAP.
- [ ] M1-M4. Unguarded extraction, nil GlobalKill, leaking SelfSender and an unredacted slog
  handler are each detected by the real assertions. An undetected mutation fails the suite.

## Rollback

All additions are build-tagged test files, an optional manual-only workflow and a markdown
report. Rollback is reverting the test PR (`git revert -m 1 <merge sha>`). No runtime, schema,
config or deployment state changes, so the deployed service needs no action. If execution
exposes an unexpected network dial or flakiness, delete the affected `l2finance_test.go` file and
record that case as CANNOT-OBSERVE in the report.
