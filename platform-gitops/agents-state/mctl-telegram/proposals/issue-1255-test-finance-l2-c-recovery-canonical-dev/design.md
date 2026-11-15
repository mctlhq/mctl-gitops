# Design: issue-1250-test-finance-l2-c-agent-api-isolation-re

## Current state

Pinned revision: `mctl-telegram` main `c4b2927a51197e2e887900272f3056122710c071`
("Merge pull request #1253", slice B). All references are from that clone. The implementer
must re-pin to `git rev-parse HEAD` at implementation time and record the value in the report.

Prior L2 slices (dependencies, both merged)
- #1247 (merge `3107baf`): `internal/agent/policy/l2finance_test.go` and
  `l2finance_result_test.go`. The report is `docs/reports/finance-assistant-l2-results.md`, with
  T7.1 PASS, T7.2 FAIL/GAP (`InstallRevision=0` skips the fence), T9.reply_observe PASS,
  T9.finance_tier NOT-IMPLEMENTED and T10.denycode PASS (policy view).
- #1249/#1253: `internal/agent/listener/l2finance_*_test.go`,
  `internal/agent/control/l2finance_*_test.go` and `docs/reports/finance-assistant-l2-slice-b.md`.
  These files establish the harness conventions this slice copies:
  - outcome constants `l2Pass`, `l2FailGap`, `l2NotImplemented` and `l2CannotObserve`;
  - a `TestMain` that requires `L2FINANCE_SOURCE_REV` to be 40-hex, unsets `TG_API_ID`,
    `TG_API_HASH` and `DATABASE_URL`, replaces `net.DefaultResolver`, and sets `l2GuardDial` on
    `http.DefaultTransport` (loopback only);
  - `l2Record` writing `L2RESULT ... rev=<sha>`, and `expectGap`, which fails once a gap stops
    reproducing.
- Neither `internal/agentapi` nor `internal/telegram` has a `TestMain` in any untagged test file
  (`grep -l "func TestMain"`), so a tagged `TestMain` does not collide.

Agent API (`internal/agentapi`)
- `server.go` `Register` mounts `POST /actions/propose_reply`, `POST /notify/summary`,
  `GET /conversations/{id}/context` and other routes through `requireNotPool` and `toolGate`.
  `Server` has no Telegram sender field: handlers only persist rows.
- `binding.go` `enforceBinding` is a no-op for an account identity. For a job-bound identity
  (`JobID != 0`) it refuses a different `conversation_id`, `job_id` or `attempt` with 403 via
  `denyBinding`, which also writes `audit(..., "denied", "conversation binding: ...")`. A zero
  request value is "not named" and is not compared.
- `actions.go` `handleOwnerFacing` (backs `/notify/summary` = `send_owner_summary` and
  `request_owner_approval`):
  - It fills `req.ConversationID` from a job-bound identity, but never `req.JobID`.
  - It loads `jobRevision` only `if req.JobID != 0`, then calls `policy.Evaluate` with
    `InstallRevision: jobRevision`.
  - It inserts an `agent_actions` row with status `executed` or `denied`, re-reads the persisted
    row, and on `executed` calls `InsertOwnerNotification`.
  - `GetConversation(ctx, id.UserID, convID)` is scoped by `user_id` (`internal/db/agent_domain.go:960`)
    and returns 404 for a foreign conversation.
- `internal/db/agent_actions.go:284-287` and `344-347`: an action without a job is stamped with
  `COALESCE((SELECT install_revision FROM agent_profiles ...), 1)`, the current revision. A
  job-bound summary that omits `job_id` therefore lands with `job_id=0` and a current-looking
  revision.
- `actions.go` `handleProposeReply`: there is no peer parameter, and the peer comes from the
  conversation row. On `Deny` the status is `denied`. On `RequireApproval` it is
  `pending_approval`, with an approval code and notification. On `Allow` it is `approved`, and the
  send happens later in the executor, not in the handler.
- `json.go`: `audit` calls `Store.LogToolCall`, which writes `audit_logs`. `LogToolCall` passes
  `ErrMsg` through `audit.ScrubText` (peer-like strings only). `logHandlerErr` writes
  `slog.Warn(..., "err", err)`.
- Existing coverage reused as patterns, not modified: `server_test.go` `newHarness` (shared-cache
  memory DB `file::memory:?cache=shared`, `doAs`, `seedConversation`, `seedJob`), the
  job-identity fixture in `binding_test.go:43-45`, and `intent_never_test.go`
  `TestInstallRevisionFencesOwnerSummary`. That last test covers only the with-`job_id` case.

Policy (`internal/agent/policy/policy.go`)
- The order of checks is `GlobalKill`, then user mismatch (reply only), then
  `in.InstallRevision != 0 && != Profile.InstallRevision` -> `DenyInstallChanged`, then mode.
  Owner-facing types then return `Allow`.
- Reasons quote agent-supplied values: `"intent "+strconv.Quote(denied)+" is never sent"` (line 490)
  and `"unrecognized agent mode "+...`.
- DenyCode is not persisted: `grep deny_code internal/db` finds nothing. It is visible only
  through `metrics.Registry.CountPolicyDenial(code, surface)`.
- There is no finance action type or tier. The profile modes are `observe`, `guarded` and `off`
  (`internal/db/agent_domain.go:29-31`).

Redaction
- `internal/audit/redact.go` `sensitiveKeys` includes `text`, `body`, `payload` and
  `proposed_text`. Redaction is by attribute key. `cmd/server/main.go:85` installs
  `slog.SetDefault(slog.New(audit.NewRedactingHandler(inner)))`.
- `agent_actions` stores the payload as `payload_encrypted`. `intent` and `policy_reasons` are
  plaintext columns.
- Tracing: only `internal/mcp/audit_span.go` builds spans. `internal/agentapi` imports no otel, and
  `go.opentelemetry.io/otel/sdk` is not in `go.mod`.

Telegram send path (`internal/telegram/sendself.go`)
- `SendToSelf` (line 112) and `SendToSelfWithRandomID` (line 122) pass `&tg.InputPeerSelf{}` to
  `SendToInputPeer[WithRandomID]`. That calls `c.API().MessagesSendMessage` on a concrete gotd
  `*telegram.Client` (gotd `v0.163.0`) and refuses `randomID == 0`.
- The test precedent `floodwait_observer_test.go` uses `telegram.MiddlewareFunc` and
  `captureSlog`. `clientpool.go:221-225` builds options with `DCList` and `Middlewares`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: tenant `labs`, image tag `0.137.1`,
  `AGENT_ENABLED: "true"`, `AGENT_KILL_SWITCH: "false"`. The agent API is live in production, so
  the harness must never target it. It is offline only.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-telegram/proposals/`:
  - `issue-1244-...` is `status: merged` (PR #1247, merge `3107baf`, grant
    `aar_5dc0456105f442829583adaa101516c6`). Its `design.md` assigns T2, T3, T7.3, T9, T10 and M4 to
    `internal/agentapi/l2finance_test.go`, and T1 wire to `internal/telegram/l2finance_test.go`.
  - `issue-1249-...` exists. Slice B is merged on `main` (#1253).
- mctl MCP tools were not called. The gitops checkout covered every fact used, and this proposal
  changes no deployed state. Live pods and logs were not observed and are not needed.
- The gotd module source was not available in the local module cache, so the T1 middleware
  behaviour is unverified. See Open questions in requirements.md.

## Proposed solution

The harness is test-only, behind the `l2finance` build tag, in two packages so it can reach
unexported seams (`ownerNotifyRequest`, `proposeReplyRequest`, `Server.Register`).

| New file | Content |
| --- | --- |
| `internal/agentapi/l2finance_harness_test.go` | `TestMain` (copied from slice B), outcome constants, `l2Record`, `expectGap`, `l2NewAPIHarness`, slog capture, assertion helpers |
| `internal/agentapi/l2finance_api_test.go` | T2, T3, T7.3, T9, T10, M4, OFFLINE |
| `internal/telegram/l2finance_sendself_test.go` | own `TestMain` + helpers (duplicated per package), T1.wire_input_peer_self, T1.source_pin |
| `docs/reports/finance-assistant-l2-slice-c.md` | evidence report |

Helpers are duplicated per package. Slice B did the same, because a shared package would put
code in the production tree.

Harness (`l2NewAPIHarness(t)`)
- Each test gets a named memory DB, `file:l2c_<sanitized t.Name()>?mode=memory&cache=shared`. This
  avoids the package-wide shared cache that `newHarness` uses. Setup is `db.MigrateCached`,
  `crypto.New(32-byte test key)` and `db.NewStore`.
- Users are `EnsureUser("l2-alice")` and `EnsureUser("l2-carol")`. Each has an `agent_profiles`
  row (mode set per case, with disclosure text).
- Telegram ids are Alice 91001, Bob 91002 (peer in Alice's conversation), Carol 91003, and Carol's
  peer 91004. The block was unused at the pinned revision (`git grep -w 91001`/`91003` returned
  no Go file). The implementer re-checks all four.
- The server is `New(store, queue.New(store, "l2c", nil), time.Minute, metrics.New())`, mounted on
  `chi.NewRouter()`, with requests driven by `httptest.NewRecorder`. Identities come from
  `auth.With`:
  - account identity: `{UserID, Subject, TelegramID}`;
  - job-bound identity: `{..., JobID, JobAttempt, ConversationID}` from a real `ClaimAgentJobs`
    claim.
- Jobs come from `InsertIncomingEvent` plus `EnqueueAgentJob`, with sender 91002 (Bob), then
  `ClaimAgentJobs(ctx, "l2c", uid, db.RuntimeOwn, 1)`.
- Marker: `L2SYNTH-TXN-7f3a`. Finance-looking text is `"L2SYNTH-TXN-7f3a total 12.34 card ending 0000"`,
  with no real merchant data.
- `l2PeerSink` is a counter that no production path can reach, because `Server` has no sender.
  Every runnable case asserts it is 0 to detect inadvertent direct API sends,
  but this cannot prove that the separate executor will not later send;
  `T9.executor_peer_send` remains CANNOT-OBSERVE.
- `l2CaptureSlog(t, handler)` installs `slog.SetDefault(slog.New(handler))` and restores it in
  `t.Cleanup`. Production capture uses `audit.NewRedactingHandler(slog.NewJSONHandler(&buf, nil))`.
  These cases do not use `t.Parallel`.
- `l2AssertNoMarker(tb, sources map[string]string) error` is the single assertion. It returns an
  error naming the first source that contains the marker. T10 and M4 both call it.

Cases (expected outcomes follow from the code reading above. The recorded outcome is whatever is
observed. Gap rows use `expectGap`.)

| id | stimulus | assertion / classification |
| --- | --- | --- |
| T2.bob_job_owner_summary | Alice job-bound identity (Bob conversation) posts `/notify/summary` with synthetic marker, intent `lead` | One notification belongs to Alice and routes only to her owner channel; no cross-user row or peer send -> PASS for ordinary owner routing. A Bob-conversation job is not finance-source authorization evidence |
| T2.finance_origin_authorization | Same request with finance-looking synthetic text, no recognized finance-source or consent model | NOT-IMPLEMENTED for financial-source authorization; record absent enforcement. An actual wrong-user/peer disclosure is a separate FAIL/GAP with sink evidence |
| T3.account_foreign_conversation | Alice account identity, `conversation_id`=Carol's conversation, on `/notify/summary` and `/actions/propose_reply` | 404; zero action and notification rows for both users -> PASS |
| T3.account_foreign_context | `GET /conversations/{carolConv}/context` as Alice | 404 -> PASS |
| T3.job_foreign_conversation | Alice job-bound identity naming Carol's conversation | 403 plus `audit_logs` `denied` row under Alice; no rows under Carol -> PASS |
| T3.account_foreign_job | Alice account identity, `job_id`=Carol's job, no conversation | 4xx; no rows -> PASS |
| T3.finance_source_consent | body carries extra field `finance_source` | 400 (`decodeStrict`); recorded `NOT-IMPLEMENTED` (no consent/source concept), never mocked |
| T7.3.with_job_id | job-bound, `BumpInstallRevision`, summary with `job_id` and attempt | denied, `ReasonInstallChanged` -> PASS (control) |
| T7.3.omit_job_id | same identity and state, `job_id` omitted | executed and queued; persisted `job_id=0`, current `install_revision` -> `FAIL/GAP` |
| T7.1, T7.2 | not re-run | cited from #1247 report unchanged |
| T9.observe_no_peer_send | observe mode, Bob conversation job, `propose_reply` marker text | status `pending_approval`; no `approved`/`executed`; peer sink 0 -> PASS |
| T9.guarded_allowlisted | guarded mode, `IntentAllowlist: "discovery"`, intent `discovery`, marker text | Record actual policy result and persisted status; if allowlisted -> `approved`, zero synchronous peer sends: PASS for API behaviour, NOT proof of later executor send or non-send. FAIL/GAP only for an actual API policy violation |
| T9.executor_peer_send | Delivery after API `approved` occurs in executor, outside this offline agentapi harness | CANNOT-OBSERVE; no no-peer-send claim from API having no sender or an inert peer sink |
| T9.finance_tier | body with extra field `tier: "finance"` | 400; `NOT-IMPLEMENTED` |
| T10.action_rows | every action row from T2/T3/T7.3/T9 | non-empty status and decision; denied rows have reasons -> PASS |
| T10.denycode_persisted | inspect persisted action/audit denial records and `AgentPolicyDenialsTotal` independently | FAIL/GAP when structured deny code is present only in transient metrics but absent from the durable audit record required by #1244. This is not a missing finance feature; no production schema edits |
| T10.redaction_text | redacting slog capture plus raw SELECTs of `audit_logs.*`, `agent_actions.intent/policy_reasons/payload_encrypted`, `owner_notifications` stored body | `l2AssertNoMarker` returns nil -> PASS |
| T10.intent_channel | marker placed in `intent` (also on the intent-never path) | observed. Marker in `audit_logs` or plaintext column -> `FAIL/GAP`; else PASS |
| T10.traces | inspect spans emitted by the actually exercised agent API instrumentation without adding fake spans or an exporter | No real spans or no accessible production instrumentation -> CANNOT-OBSERVE, record `spans=0`; never claim trace redaction PASS from an empty test-local provider |
| M4 | harness-only handler that logs `slog.Info("l2 m4", "text", marker)` through `slog.NewJSONHandler` (no redaction) | `l2AssertNoMarker` must return an error -> `PASS (detected)`; otherwise `t.Fatal` |
| M4.redacted_twin | same handler, production redacting handler | helper returns nil (shows the detection comes from missing redaction) |
| OFFLINE.default_paths | dial TEST-NET-1 `192.0.2.1:443` via default transport; `net.LookupHost("example.invalid")` | both refused with `errL2ExternalDial`; loopback `httptest.NewServer` reachable -> PASS |
| OFFLINE.whole_process | none | `CANNOT-OBSERVE` (guards only default paths), as in slice B |

T1 wire layer (`internal/telegram/l2finance_sendself_test.go`)
- Build `telegram.NewClient(1, "l2-synthetic-hash", telegram.Options{...})` with:
  - `SessionStorage: &session.StorageMemory{}` and `NoUpdates: true`;
  - a `Resolver` whose dial function records an attempt and returns `errL2ExternalDial` without
    dialing (implemented with `dcs.Plain(dcs.PlainOptions{Dial: ...})`);
  - `Middlewares: []telegram.Middleware{capture}`, where `capture` never calls `next`. It records
    the `*tg.MessagesSendMessageRequest` peer and decodes a synthetic `*tg.Updates` (an
    `UpdateMessageID`) into the output.
- Call `SendToSelfWithRandomID(ctx, c, 91001, 1, "L2SYNTH-TXN-7f3a")` with a 2 s context and
  `client.Run` never invoked.
- If the captured peer is `*tg.InputPeerSelf` and the resolver count is 0, the result is PASS.
- If the call times out or the resolver count is above 0, the result is `CANNOT-OBSERVE` and the
  case still passes. Nothing is dialed either way.
- `T1.source_pin` always runs. It reads `sendself.go` and asserts that the bodies of `SendToSelf`
  and `SendToSelfWithRandomID` contain `&tg.InputPeerSelf{}`. It records PASS as source evidence,
  labelled as such, so it is not wire evidence.
- The Run-less call reaches `notifyAgentSent(userID, messageID)`, a package-level marker map.
  The test uses a synthetic user id and clears nothing global beyond that.

Commands (recorded in the report)
```
L2FINANCE_SOURCE_REV=$(git rev-parse HEAD) go test -tags l2finance -race -count=1 -run L2Finance -v ./internal/agentapi/ ./internal/telegram/ | grep L2RESULT
go vet -tags l2finance ./internal/agentapi/ ./internal/telegram/
go test -race -count=1 ./internal/agentapi/ ./internal/telegram/   # untagged, unchanged
```

## Alternatives

1. Add a finance consent store or finance action tier as fakes so T3 and T9 "pass". Dropped: the
   issue forbids it, and it would be the made-up layer that masks missing security.
   `NOT-IMPLEMENTED` with observed 400 evidence is the honest result.
2. Mint real job tokens through `handleClaimJobs` and the `agent-job` auth middleware instead of
   injecting identities with `auth.With`. Dropped for this slice: it needs a signer and auth
   provider wiring that `newHarness` does not have, and token verification is a separate concern.
   The report states the layer boundary.
3. Observe T1 through a fake MTProto server on loopback (gotd `tgtest`). Dropped: it needs a
   key exchange and DC config, and it risks pulling in gotd test dependencies not already in
   `go.sum`. The middleware capture plus a refusing resolver is smaller, and it falls back to
   `CANNOT-OBSERVE` with a source pin.
4. Put all cases in one cross-package file. That is not possible: agentapi request types are
   unexported. It would also overlap slice B's files.

## Platform impact

- Migrations: none. Schema, `go.mod` and `go.sum` are unchanged. Production code is unchanged.
- Backward compatibility: untagged builds are identical, so default CI (`go test -race ./...`)
  ignores the files.
- Resource impact: a few seconds of CPU for the tagged run, in-memory SQLite only.
- Risks and mitigations:
  - Accidental egress. The `TestMain` guards apply, gotd gets a refusing resolver, and no client
    `Run` is called. `OFFLINE.whole_process` stays `CANNOT-OBSERVE`, so no wider claim is made.
  - Gap renamed to PASS. `expectGap` fails the test when a gap stops reproducing.
  - Tautological redaction check. M4 must be detected by the same helper, or the suite fails.
  - Global slog/otel state leaking between tests. Every override is restored in `t.Cleanup`, and
    these cases do not run in parallel.
  - Harness PASS mistaken for a security PASS. The report header keeps
    `FINANCE_SECURITY_GATE=BLOCKED` and states that this is slice C only.
  - Fixture ids colliding with real accounts. The ids are synthetic and checked with `git grep`.
    The personas Alice, Bob and Carol are from CLAUDE.md.
