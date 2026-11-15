# Design: issue-1244-spike-test-finance-assistant-l2-owner-pr

## Current state

Pinned revision: `mctl-telegram` main `248db4f5a8cbb4ce0c1296c072547a70007246fc`
(2026-11-08, "Merge pull request #1241", release-please). All references below are from that
clone.

Owner-private transport
- `internal/telegram/sendself.go`: `SendToSelf` / `SendToSelfWithRandomID` call
  `SendToInputPeer[WithRandomID]` with a hard-coded `&tg.InputPeerSelf{}`. The peer never comes
  from input. `SendToInputPeerWithRandomID` refuses `randomID == 0` and wraps `RANDOM_ID_DUPLICATE`
  as `ErrRandomIDDuplicate`. It takes a concrete gotd `*telegram.Client`, so existing fakes
  (`tg.NewClient(fake)` in `internal/telegram/broadcast_content_test.go`) cannot reach it directly.
- `cmd/server/agentwiring.go` `poolSelfSender` adapts `ClientPool.Borrow` to `control.SelfSender`
  and maps duplicates to `executor.ErrAlreadyDelivered`.

Command intake
- `internal/agent/listener/extract.go`: `ExtractMessage` and `ExtractSavedHistoryMessage` call
  `classifySavedCommand`. That function rejects `FwdFrom`, a non-self `SavedPeerID` and a non-self
  `FromID`, and retains only `/mctl`-prefixed text. It deliberately ignores `msg.Out` (live
  observations 2026-07-26 and 2026-08-01, #354). `eventIDForMessage` is the dedupe key
  (`evt:v1:acct:chat:msg[:e<editDate>:<hash>]`).
- `internal/agent/listener/history.go`: `pollSavedHistory` and `initializeSavedHistoryCursor`
  operate over the `savedHistoryAPI` interface (`MessagesGetHistory`). The first poll sets a
  baseline without replay.
- `internal/agent/listener/listener.go`: `onMessage(ctx, acct, ents, m, isEdit)`;
  `CommandRouter` interface (`HandleSavedText`).
- `internal/agent/control/command.go` / `router.go`: `ParseCommand` knows status, leads, show,
  continue, pause, unpause, assistant, takeover, approve, reject, conversations, work, link and
  input. No finance command exists. An unknown verb returns `unknownCommandReply` through
  `Notifier.Reply`.

Owner notification delivery
- `internal/agent/control/notifier.go`: `SelfSender` interface (`SendToSelf`,
  `SendToSelfWithRandomID`), optional `SelfDeliveryLocator`. `DeliverPending` returns early when
  `GlobalKill()` is true (rows stay pending), then calls `ListPendingOwnerNotifications`,
  `ClaimOwnerNotification` (persists `random_id` once, COALESCE) and `SendToSelfWithRandomID`,
  then `MarkOwnerNotificationSent`. It does not re-check profile mode, install revision or account
  revocation at delivery time.
- `internal/db/agent_actions.go:1430` `ListPendingOwnerNotifications` filters only on `status`
  and `claimed_until`. It does not join `telegram_accounts.revoked_at`. `revoked_at IS NULL` is
  checked elsewhere (`internal/agent/listener/supervisor.go:43`, `internal/db/agent_domain.go:818`).

Policy and agent API
- `internal/agent/policy/policy.go` `Evaluate` checks, in order: `GlobalKill` ->
  `DenyUserMismatch` (only for `ActionTypeReply`) -> `if in.InstallRevision != 0 && in.InstallRevision != in.Profile.InstallRevision`
  `DenyInstallChanged` (line 414; revision 0 skips the fence) -> mode (`off` ->
  `DenyModeOff`). `ActionTypeOwnerSummary` and `ActionTypeOwnerApproval` then return `Allow`
  before any per-conversation, blocklist or audience gate.
- `internal/agentapi/actions.go` `handleOwnerFacing` (backs `/notify/summary` =
  `send_owner_summary`, see `internal/agent/tools/endpoints.go`) fills `ConversationID` from a
  job-bound token. It does not fill `JobID`. `jobRevision` is loaded only when `req.JobID != 0`,
  and `enforceBinding` (`binding.go:34`) accepts `jobID == 0`. A job-bound caller that omits
  `job_id` is therefore evaluated with `InstallRevision: 0`. This is read from the code, not yet
  observed. Making that observation is T7.3.
- `handleOwnerFacing` writes an `agent_actions` row (decision, reasons, status) for every
  decision, then `s.audit(...)`, then `InsertOwnerNotification` (idempotent per `action_id`).
- `internal/audit/redact.go` `sensitiveKeys` includes `text`, `body` and `payload`.

Existing test seams (reused, not modified)
- `internal/agent/control/router_test.go`: `fakeSelfSender`, `fakeApprover`, `newTestRouter`
  (in-memory SQLite, `crypto.New(testKey())`).
- `internal/agent/listener/history_test.go`: `fakeSavedHistoryAPI`, `capturedSelfSender`,
  `lockedRecordingRouter`.
- `internal/agent/listener/listener_test.go`: `newTestListener`, per-test named memory DB.
- `internal/agentapi/server_test.go`: in-memory store + `httptest` server.
- Existing coverage that L2 cases re-run under one fixture set rather than duplicate:
  `TestExtractMessage_RejectsIndirectSavedCommands`, `TestPollSavedHistory_PushAndHistoryRouteOnce`,
  `TestPollSavedHistory_RoutesCommandWithOutFalse`, `TestNotifier_DeliverPending_KillSwitchSilencesQueuedDelivery`,
  `TestNotifier_DeliverPending_UsesAndPersistsRandomID`. Build-tag precedent:
  `internal/telegram/live_integration_test.go` (`//go:build livetg`).
- Main CI (`.github/workflows/build.yml`) runs `go test -race ./...`. Files under a build tag it
  does not set are excluded.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: image tag `0.137.0`,
  `AGENT_ENABLED: "true"`, `AGENT_KILL_SWITCH: "false"`. The service lives in tenant `labs`. This
  shows the owner-facing path is live in production, so the suite must never run against the
  deployment. It is offline only.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-telegram/proposals/`: only
  `issue-1240-spike-finance-assistant-owner-private-de` is related. No existing L2 proposal.
- mctl MCP tools were not called. The gitops checkout was sufficient for the facts needed, and
  the proposal changes no deployed state. Live pod or log state was not observed and is not
  needed.

## Proposed solution

A test-only harness, split by package so each file can reach the unexported seams it needs
(`onMessage`, `pollSavedHistory`, `classifySavedCommand`, `handleOwnerFacing` via HTTP). Every new
file starts with `//go:build l2finance` and lives next to the code it exercises:

| File (new, test-only) | Cases |
| --- | --- |
| `internal/agent/listener/l2finance_test.go` | T1 (intake), T2 (intake), T4, T5.1 source dedupe, T5.3 cursor, T6, mutation M1 |
| `internal/agent/control/l2finance_test.go` | T1 (router + sink), T3 (delivery per UserID), T5.2 random id, T8, mutations M2/M3 |
| `internal/agent/policy/l2finance_test.go` | T7.1/T7.2 direct `Evaluate`, T9 policy view, T10 DenyCode table |
| `internal/agentapi/l2finance_test.go` | T2 (owner summary from Bob-conversation job), T3 (foreign conversation), T7.3, T9 propose_reply, T10 audit rows + slog redaction, mutation M4 |
| `internal/telegram/l2finance_test.go` | T1 wire-level `InputPeerSelf` feasibility (middleware interceptor), else `CANNOT-OBSERVE` |
| `internal/<pkg>/l2finance_result_test.go` (one per package, roughly 30 lines, duplicated) | `l2Record(t, id, outcome, evidence)` emitting `L2RESULT ...` via `t.Log`, plus `expectGap` helper |

Helpers are duplicated per package on purpose. A shared non-test package would add production-tree
code, which is not authorized.

Fixtures
- Personas: Alice = owner account (users row via `EnsureUser`, profile mode `observe`, Saved
  Messages self id), Bob = peer in Alice's DM (conversation row under Alice), Carol = second
  users row with her own profile, conversation and notification, Dana = forward origin
  (`FwdFrom`) and foreign `FromID`/`SavedPeerID`. Numeric Telegram ids are drawn from a block
  confirmed unused by `git grep` (91001-91004 were unused at the pinned revision; re-check at
  implementation time). Inside `internal/agent/listener` the existing `selfTG`, `ownerUID` and
  `recruit` constants may be reused where a case extends an existing test.
- Synthetic finance text: a fixed marker `L2SYNTH-TXN-7f3a` embedded in fake merchant-free amounts
  (for example "L2SYNTH-TXN-7f3a total 12.34"). No real merchant or statement data. T10 greps for
  this marker.
- Deterministic time: the harness passes explicit timestamps where the API takes them, and it
  sets `ClaimLease`/`MaxPendingAge` explicitly. Random ids are not made deterministic in
  production code (`newSelfRandomID` stays as is). Tests assert reuse of the persisted value, not
  a specific value.

Sinks
- `recordingSelfSender` (copy of `fakeSelfSender`, records `(userID, randomID, text)`).
- `peerSink`: a fake `executor.Sender` / counter that every test asserts stays at zero. Only
  mutation M3 writes to it.
- `slogCapture`: `slog.New(audit redaction handler(JSON handler over bytes.Buffer))`, installed
  with `slog.SetDefault` for the test and restored in `t.Cleanup`. Tests in the package then run
  without `t.Parallel` for these cases.

Outcome rubric and gap handling
- `PASS`: the guard exists and the stimulus is denied or contained as required.
- `FAIL/GAP`: the guard is absent or bypassable. Implemented as `expectGap(t, id, observed bool)`:
  if the unsafe behaviour is observed, record `FAIL/GAP` and the Go test passes. If it is not
  observed, `t.Fatalf("T#: gap no longer reproduces; update rubric via reviewed PR")`. A gap
  therefore can never be silently renamed to PASS, and a later fix forces an explicit rubric
  change.
- `NOT-IMPLEMENTED`: the capability does not exist (`ParseCommand("/mctl finance")` error, no
  finance `ActionType`, no consent table in `db.MigrateCached` schema). The harness asserts the
  absence (so the label is evidence-backed) and the report carries the future contract test text.
- `CANNOT-OBSERVE`: the layer cannot be driven offline. The reason is recorded and nothing is
  asserted.

Expected outcomes, to be confirmed by execution (hypotheses from code reading, not results)

| Case | Expected outcome |
| --- | --- |
| T1 router/SelfSender sink only | PASS; finance verb NOT-IMPLEMENTED; wire-level InputPeerSelf PASS or CANNOT-OBSERVE |
| T2 Bob DM never reaches router | PASS; Bob-conversation job can queue owner summary: FAIL/GAP vs finance contract |
| T3 foreign conversation / per-UserID delivery | PASS; finance source isolation NOT-IMPLEMENTED |
| T4 fwd_from / saved_peer_id / from_id / group | PASS |
| T5 dedupe / random id / cursor | PASS (three separate sub-cases) |
| T6 Out=false push + history after restart | PASS |
| T7.1 stale revision | PASS (`DenyInstallChanged`) |
| T7.2 revision 0 on Evaluate | FAIL/GAP |
| T7.3 job-bound summary omitting job_id | FAIL/GAP if allowed |
| T8 GlobalKill queued / mode off before queue | PASS |
| T8 mode off after queue, revoked_at after queue | FAIL/GAP (no delivery-time re-check) |
| T9 propose_reply finance text | observe-mode containment PASS or recorded DenyCode; finance tier NOT-IMPLEMENTED |
| T10 action rows + DenyCode + redaction | PASS per row field; any missing field FAIL/GAP |

Negative controls (harness only)
- M1: a harness function calls `Router.HandleSavedText` directly with Dana-forwarded text,
  bypassing `classifySavedCommand`. The T4 assertion "no router call" must fail on it. The harness
  inverts that and records `MUTATION-DETECTED`.
- M2: a Notifier built with `GlobalKill: nil` must produce a send that the T8 assertion catches.
- M3: a `leakingSelfSender` wrapper also writes to `peerSink`. The "zero peer sends" assertion
  must catch it.
- M4: a JSON slog handler without redaction must let `L2SYNTH-TXN-7f3a` through, and the T10 grep
  must catch it.
- Each mutation runs the same assertion helper as the real case, with `testing.TB` replaced by a
  recorder, so "detected" means the real assertion fired.

Commands
- Local and CI: `go test -tags l2finance -race -count=1 -run 'L2Finance' -v ./internal/agent/... ./internal/agentapi/... ./internal/telegram/... 2>&1 | tee l2.log`
  then `grep '^.*L2RESULT' l2.log`.
- Regression check that default CI is untouched: `go test -race ./...` (no tag), `go vet -tags l2finance ./...`,
  `golangci-lint run --build-tags l2finance`.
- Optional `.github/workflows/l2-finance.yml`: `workflow_dispatch` only, no secrets, no
  `id-token`, `permissions: contents: read`. It runs the command above and uploads the
  `L2RESULT` lines as an artifact.

Report
- `docs/reports/finance-assistant-l2-results.md`: pinned SHA, Go version, exact command, `L2RESULT`
  table, mutation table, `git grep` id checks, future contract tests for each `NOT-IMPLEMENTED`
  row. It states that test approval is not pilot approval and that #325 and #1240 verdicts are
  unchanged.

## AMEND: execution boundary and unambiguous evidence reporting

**Hermetic L2 boundary.** Tests may use `httptest.NewRecorder` in-process
or a locally bound `httptest` listener on loopback, plus local Unix
sockets and in-memory SQLite. No non-loopback outbound TCP/UDP, external
DNS, real MTProto, Telegram, SaaS, or production calls are permitted.
Use a guarded test transport/dialer and fail assertions on any attempted
external dial. If `SendToSelfWithRandomID` cannot be intercepted
without connecting to a remote DC, do not attempt the connection:
record `CANNOT-OBSERVE` with source-pinned reasoning. Any CI
dependency fetch is a separate build setup action, not part of L2
execution and never a justification for test-time egress.

**Two independent summaries.** The `l2finance` test runner must validate
one structured `L2RESULT` per required T1-T10 sub-case (and all
mutation controls), with exact IDs and counts per rubric category.
`harness_status=PASS` means that the tests ran and correctly detected
their intentionally reproduced missing guards; it is **not**
`security_gate_status=PASS`. A separate aggregation always reports
`FINANCE_SECURITY_GATE=BLOCKED` if any required row has
`FAIL/GAP`, `NOT-IMPLEMENTED`, `CANNOT-OBSERVE`, missing,
duplicate or unclassified status. Never collapse a recorded gap into
a green security conclusion. Report both statuses prominently in
`docs/reports/finance-assistant-l2-results.md` and, if the optional
manual `workflow_dispatch` is added, in its step summary and attached
results. Do not wire the status to a deploy, pilot, product approval,
or production promotion. No runtime fix is within the proposal scope.

## Alternatives

1. Put the cases in default `go test ./...` without a build tag. Dropped: green main CI would
   display FAIL/GAP rows as passing checks, which is exactly the "waiver by renaming" the issue
   forbids, and gap-tracking tests would fail main CI when an unrelated fix lands.
2. A shared `internal/l2finance` helper package or a new `test/l2/` black-box package. Dropped:
   a non-`_test.go` helper is new production-tree code, and a black-box package cannot reach
   `onMessage`, `pollSavedHistory` or `classifySavedCommand` without exporting them, which would
   be a runtime change.
3. Model the finance job and consent grant with fakes so T3 and T9 can "pass". Dropped: it
   mocks the very authorization layer under test, which the issue forbids. Those rows stay
   `NOT-IMPLEMENTED` with contract specs.
4. Exercise the wire path with gotd's real client over a local fake DC. Dropped: heavy, brittle,
   and close to "real MTProto network". The middleware interceptor or `CANNOT-OBSERVE` is the
   bounded option.

## Platform impact

- Migrations: none. Backward compatibility: no runtime, API or schema change, and default builds
  and tests are byte-identical because of the build tag.
- Resource impact: one optional manual CI job, a few minutes of runner time. No cluster, Helm or
  tenant change. `labs/mctl-telegram` (0.137.0) is unaffected.
- Risks and mitigations:
  - Fixture leaks real data: synthetic personas only, `git grep` id check recorded, synthetic
    marker text, and the repo's CLAUDE.md fixture rule.
  - Global slog swap races other tests: those cases are not parallel and restore in `t.Cleanup`.
    The build tag isolates them from default CI.
  - Gap rows misread as approval: the rubric is explicit, `expectGap` fails if a gap disappears,
    and the report repeats that #325 stays `RESEARCH_ONLY_DEFER`.
  - Tautological pass: the M1-M4 mutation controls must all be detected, or the suite fails.
  - Scope creep into fixing T7 or T8: fixes are out of scope and need a separate
    bounded-extension proposal.
