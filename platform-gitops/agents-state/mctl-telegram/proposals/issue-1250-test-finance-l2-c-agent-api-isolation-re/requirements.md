# Finance Assistant L2 slice C: agent API isolation, revision binding and redaction evidence (test-only)

## Context

Issue mctlhq/mctl-telegram#1250 is the third test-only slice of the L2 harness that the #1244 spike
approved. The policy-package slice (#1247, merge `3107baf`) and the Saved Messages listener and
owner notifier slice B (#1249, merged as #1253, `c4b2927`) are both on `main`. Slice C covers the
cases #1244 assigned to `internal/agentapi` and `internal/telegram`:

- T2: an owner summary queued by a job bound to the Bob conversation.
- T3: Alice's credential naming Carol's conversation or job.
- T7.3: a job-bound `/notify/summary` call that omits `job_id`, and with it the
  `InstallRevision=0` fence.
- T9: finance-looking text sent through `propose_reply`.
- T10: `agent_actions` status, decision and deny-code fields, plus audit and slog redaction of a
  synthetic marker, with negative control M4.
- T1 wire layer: whether `SendToSelf*` puts `InputPeerSelf` on the wire, observed offline.

The work matters because the parent gate `FINANCE_SECURITY_GATE=BLOCKED` (mctlhq/.github#325,
`RESEARCH_ONLY_DEFER`) can only be decided once every slice has recorded observed outcomes. The
slice adds no product code. It records what the current code does, classifies the result as
`PASS`, `FAIL/GAP`, `NOT-IMPLEMENTED` or `CANNOT-OBSERVE`, and repairs nothing.

## User stories

- AS the security reviewer of the finance gate I WANT observed, reproducible outcomes for the
  agent API isolation, revision-fence, peer-reply and redaction cases SO THAT the later slice-D
  aggregator and the security decision rest on evidence, not on code reading.
- AS the repository owner I WANT these tests to sit behind the `l2finance` build tag, change no
  production Go file and never touch the network SO THAT default CI, the deployed service and real
  Telegram accounts are unaffected.
- AS a future maintainer I WANT each reproduced gap to fail its test once it stops reproducing SO
  THAT a gap is never renamed to PASS without a reviewed rubric change.

## Acceptance criteria (EARS)

Scope and safety
- THE SYSTEM SHALL add only files whose first line is `//go:build l2finance` and whose names end
  in `_test.go`, under `internal/agentapi/` and `internal/telegram/`, plus one Markdown report
  `docs/reports/finance-assistant-l2-slice-c.md`. No other file is created or modified. That
  includes `go.mod`, `go.sum`, slice-B files, policy-package files, and both existing reports
  (`finance-assistant-l2-results.md` and `finance-assistant-l2-slice-b.md`).
- WHILE the `l2finance` tag is not set THE SYSTEM SHALL compile and run exactly the same tests as
  before (`go test -race ./...` unchanged).
- WHEN the tagged test binary starts and `L2FINANCE_SOURCE_REV` is not a 40-hex commit sha THE
  SYSTEM SHALL exit with status 2 before any case runs.
- WHEN the tagged test binary starts THE SYSTEM SHALL unset `TG_API_ID`, `TG_API_HASH` and
  `DATABASE_URL`. It SHALL replace `net.DefaultResolver` with one that refuses every lookup, and
  SHALL make `http.DefaultTransport` refuse every non-loopback dial.
- IF any harness path attempts a non-loopback dial or an external DNS lookup THEN THE SYSTEM SHALL
  fail that test with `errL2ExternalDial`, never retry it, and never dial.
- THE SYSTEM SHALL use only per-test named in-memory SQLite databases, in-process `httptest`
  recorders or loopback servers, and synthetic personas (Alice owner, Bob peer, Carol second
  owner) with Telegram ids from a block that `git grep` confirms is unused.
- THE SYSTEM SHALL emit exactly one `L2RESULT id=<id> outcome=<outcome> rev=<sha> evidence=<...>`
  line per sub-case.

T2 (owner summary from a Bob-conversation job)
- WHEN a job-bound identity for a job on Alice's conversation with Bob posts `/notify/summary`
  with finance-looking text containing the marker THE SYSTEM SHALL record the observed decision,
  the action status and whether an `owner_notifications` row was queued.
- IF the summary is executed and queued THEN THE SYSTEM SHALL record `T2.bob_job_owner_summary`
  as `FAIL/GAP` against the finance contract (peer-originated finance content reaches the owner
  channel) through `expectGap`, and SHALL NOT change policy.

T3 (cross-tenant isolation)
- WHEN Alice's account identity or Alice's job-bound identity names Carol's conversation id on
  `/notify/summary`, `/actions/propose_reply` or `GET /conversations/{id}/context` THE SYSTEM SHALL
  require 403 (binding) or 404 (not found), and SHALL require that no `agent_actions` row or
  `owner_notifications` row exists under either user. If those hold, the result is `PASS`.
- WHEN Alice's account identity names Carol's job id THE SYSTEM SHALL require a 4xx and no row
  under either user.
- WHEN a request carries a finance-source or consent field THE SYSTEM SHALL record the observed
  rejection (`decodeStrict` refuses unknown fields) and classify `T3.finance_source_consent` as
  `NOT-IMPLEMENTED`. It SHALL NOT mock a consent store.

T7.3 (job binding and install-revision fence at the API)
- WHEN a job-bound identity posts `/notify/summary` with its `job_id` after the install revision
  is bumped THE SYSTEM SHALL require denial with `ReasonInstallChanged`
  (`T7.3.with_job_id`, PASS control).
- WHEN the same job-bound identity posts `/notify/summary` without `job_id` after the bump THE
  SYSTEM SHALL record the observed decision, status, the persisted `job_id` and
  `install_revision`, and whether a notification was queued. IF the summary is executed THEN it
  SHALL be recorded as `FAIL/GAP` (`T7.3.omit_job_id`) through `expectGap`.
- THE SYSTEM SHALL NOT re-run or overwrite T7.1 and T7.2. The report SHALL cite them from
  `finance-assistant-l2-results.md` unchanged (T7.1 PASS, T7.2 FAIL/GAP).

T9 (no immediate peer send for finance text)
- WHEN `propose_reply` carries finance-looking text in `observe` mode THE SYSTEM SHALL require
  that the persisted status is not `approved` or `executed`. It SHALL also require that the
  handler performs no peer send: the API server has no sender, and the peer sink stays empty. If
  both hold, the result is `PASS`.
- WHEN the same request runs in `guarded` mode with an allowlisted intent THE SYSTEM SHALL record
  the observed decision. IF the status is `approved` (the executor would send without a human)
  THEN it SHALL be recorded as `FAIL/GAP`. Otherwise it is `PASS`.
- IF the request names a finance tier or action field THEN THE SYSTEM SHALL record the observed
  400 and classify `T9.finance_tier` as `NOT-IMPLEMENTED`.

T10 (audit rows and redaction)
- WHEN any T2, T3, T7.3 or T9 request completes THE SYSTEM SHALL require that each resulting
  `agent_actions` row has a non-empty `status`, `policy_decision` and, for denials,
  `policy_reasons`.
- THE SYSTEM SHALL record whether a deny code is persisted on the action row. IF it is not (it is
  observed only through the `CountPolicyDenial` metric) THEN it SHALL be recorded as
  `T10.denycode_persisted` `FAIL/GAP`.
- WHILE the T10 calls run THE SYSTEM SHALL capture all slog output through the production
  pipeline (`audit.NewRedactingHandler` over a JSON handler), and SHALL require that the marker
  appears neither there nor in plaintext in `audit_logs`, `agent_actions` or
  `owner_notifications` columns. If both hold, the result is `PASS`.
- WHEN the marker is placed in the agent-supplied `intent` field instead of `text` THE SYSTEM
  SHALL record whether it surfaces in `audit_logs` or in `agent_actions.intent`/`policy_reasons`
  (`T10.intent_channel`). If it surfaces, that is `FAIL/GAP`.
- WHEN harness-only control M4 logs the marker under key `text` through a JSON handler with no
  redaction THE SYSTEM SHALL require that the same assertion helper used by T10 reports the leak.
  The row is recorded as `M4 PASS (detected)`. IF the helper does not report it THEN the suite
  SHALL fail.

T1 wire layer
- WHEN `SendToSelfWithRandomID` runs against a gotd `*telegram.Client` whose terminating test
  middleware captures `messages.sendMessage` and whose DC resolver refuses every dial THE SYSTEM
  SHALL record `T1.wire_input_peer_self` as `PASS` if the captured peer is `*tg.InputPeerSelf`.
- IF the call blocks, or the resolver is reached before the middleware captures the request, THEN
  THE SYSTEM SHALL not dial. It SHALL record `T1.wire_input_peer_self` as `CANNOT-OBSERVE` and
  source-pin `internal/telegram/sendself.go`, asserting that `SendToSelf` and
  `SendToSelfWithRandomID` pass `&tg.InputPeerSelf{}`.

Reporting
- THE SYSTEM SHALL write `docs/reports/finance-assistant-l2-slice-c.md` with the pinned source
  revision, the Go version, the exact commands, one table row per sub-case and the counts. It SHALL
  state `FINANCE_SECURITY_GATE=BLOCKED` and "Slice C only; not L2 completion; no aggregation
  across slices". It SHALL keep the harness status (all cases executed) separate from any
  financial-security PASS.

## Out of scope

- Any production Go change, policy fix or security fix for a reproduced gap.
- Finance Assistant implementation: finance commands, jobs, consent store, CSV, connectors or
  live financial integrations.
- New user data, commands, runtime auth, database schema or migrations, and new module
  dependencies.
- The L2 listener and notifier cases (slice B, #1249) and the cross-slice aggregator (slice D).
- Editing PR #1247's files or its report, or reusing #1244's approval grant.
- Job-token minting and verification (`mintJobToken`, auth middleware). Identities are injected
  with `auth.With` as the existing `binding_test.go` does. The report must state this layer
  boundary.
- Deployment, preview environments or any call against the live `labs/mctl-telegram` service.

## Open questions

- T2 classification: queuing an owner summary from a peer-conversation job is the product's
  normal behaviour. The proposal follows the #1244 rubric (`FAIL/GAP` vs the finance contract).
  The reviewer should confirm that framing.
- T9 guarded mode: `handleProposeReply` records `approved` and leaves the actual send to the
  executor, which is outside this slice. Is the persisted `approved` status sufficient evidence of
  an "immediate send"?
- T10 traces: `internal/agentapi` emits no OpenTelemetry spans, and `go.opentelemetry.io/otel/sdk`
  is not a dependency. Trace redaction is therefore recorded from a test-local `TracerProvider` as
  "0 spans observed". Is a vacuous result acceptable, or should it be `CANNOT-OBSERVE`?
- T1: the gotd module source (`v0.163.0`) was not in the investigator's module cache. Whether a
  terminating middleware captures `Invoke` before any connection exists is unverified. Both
  outcomes are defined above.
- Should `T10.denycode_persisted` be `FAIL/GAP` (the #1244 rubric: "any missing field") or
  `NOT-IMPLEMENTED`?
- This proposal needs its own approval grant. #1244's grant (`aar_5dc0456105f442829583adaa101516c6`)
  and slice B's grant (`aar_9020e7a758204906b74b976033994fe6`) do not transfer.
