# Tasks: issue-1250-test-finance-l2-c-agent-api-isolation-re

Preconditions:
- This proposal has its own reviewed digest and exact-content owner approval. The #1244 and
  slice-B grants do not apply.
- #1247 and #1249 are merged on `main`. This was verified at `c4b2927`.

- [ ] 1. Pin the revision and check fixture ids — DoD: `git rev-parse HEAD` is recorded for the report. `git grep -w` for 91001, 91002, 91003 and 91004 returns no Go file, or a free block is chosen and recorded. No production file is touched.
- [ ] 2. Add `internal/agentapi/l2finance_harness_test.go` (`//go:build l2finance`) (depends on 1) — DoD:
  - It contains a `TestMain` copied from `internal/agent/control/l2finance_harness_test.go` (40-hex `L2FINANCE_SOURCE_REV` check with exit 2, env unset, resolver and default-transport guard).
  - It contains the outcome constants, `l2Record` and `expectGap`.
  - `l2NewAPIHarness` provides a per-test named memory DB, users l2-alice and l2-carol with profiles, conversations with peers 91002 and 91004, claimed jobs, account and job-bound identities via `auth.With`, a `metrics.New()` registry, and a chi router from `Server.Register`.
  - It also provides `l2PeerSink`, `l2CaptureSlog` and `l2AssertNoMarker`.
  - `go vet -tags l2finance ./internal/agentapi/` is clean.
- [ ] 3. Add T2, T3 and T7.3 cases in `internal/agentapi/l2finance_api_test.go` (depends on 2) — DoD: rows T2.bob_job_owner_summary, T3.account_foreign_conversation, T3.account_foreign_context, T3.job_foreign_conversation, T3.account_foreign_job, T3.finance_source_consent, T7.3.with_job_id and T7.3.omit_job_id each emit exactly one `L2RESULT`. Gap rows go through `expectGap`. The persisted `job_id`/`install_revision` of T7.3.omit_job_id appear in the evidence.
- [ ] 4. Add T9 cases (depends on 2) — DoD: T9.observe_no_peer_send, T9.guarded_allowlisted and T9.finance_tier are recorded with the observed status, decision and HTTP code. The peer sink is 0 in every row.
- [ ] 5. Add T10 cases and M4 (depends on 3, 4) — DoD:
  - T10.action_rows, T10.denycode_persisted, T10.redaction_text, T10.intent_channel and T10.traces are recorded.
  - Raw SQL reads cover `audit_logs`, `agent_actions` and `owner_notifications`.
  - The slog capture goes through `audit.NewRedactingHandler`.
  - The trace provider is test-local, with no new module.
  - M4 fails the suite unless `l2AssertNoMarker` reports the leak, and M4.redacted_twin returns nil.
- [ ] 6. Add OFFLINE.default_paths and OFFLINE.whole_process rows in agentapi (depends on 2) — DoD: a TEST-NET-1 dial and an external lookup are refused with `errL2ExternalDial`, loopback `httptest.NewServer` works, and whole_process is `CANNOT-OBSERVE`.
- [ ] 7. Add `internal/telegram/l2finance_sendself_test.go` (depends on 1) — DoD:
  - It has its own `TestMain` and helpers.
  - T1.wire_input_peer_self uses a terminating capture middleware and a refusing `dcs.Plain` resolver, never calls `Run`, and has a 2 s timeout. It records PASS or `CANNOT-OBSERVE` and never dials (the resolver dial counter is in the evidence).
  - T1.source_pin asserts `&tg.InputPeerSelf{}` in `SendToSelf` and `SendToSelfWithRandomID`, labelled as source evidence.
- [ ] 8. Write `docs/reports/finance-assistant-l2-slice-c.md` (depends on 3-7) — DoD:
  - The header has `FINANCE_SECURITY_GATE=BLOCKED`, "Slice C only; not L2 completion; no aggregation across slices", and the harness status kept separate from security PASS.
  - It records the pinned rev, Go version and approval reference of this proposal, the exact commands, one row per `L2RESULT`, counts, T7.1/T7.2 cited from #1247 unchanged, the layer boundary (identities injected; token minting not exercised), the offline-guard limitations and the open questions.
  - The existing reports are untouched.
- [ ] 9. Run the verification (depends on 8) — DoD: the tagged run exits 0. Untagged `go test -race -count=1 ./internal/agentapi/ ./internal/telegram/` is green and unchanged. `git diff --stat` against the base lists only the three test files and the report. `go.mod` and `go.sum` are unchanged.

## Tests

- [ ] T1. `L2FINANCE_SOURCE_REV=$(git rev-parse HEAD) go test -tags l2finance -race -count=1 -run L2Finance -v ./internal/agentapi/ ./internal/telegram/ | grep L2RESULT` prints one line per sub-case listed in design.md, each with an outcome in {PASS, FAIL/GAP, NOT-IMPLEMENTED, CANNOT-OBSERVE}.
- [ ] T2. `L2FINANCE_SOURCE_REV=bad go test -tags l2finance ./internal/agentapi/` exits 2 before any case runs.
- [ ] T3. M4 is detected. Temporarily making `l2AssertNoMarker` always return nil (a local experiment, not committed) makes the M4 test fail.
- [ ] T4. `go vet -tags l2finance ./internal/agentapi/ ./internal/telegram/` is clean, and untagged `go test -race ./...` is unchanged.
- [ ] T5. OFFLINE.default_paths is PASS, and the T1 resolver dial counter equals 0 in the evidence.

## Rollback

Delete the three `l2finance` test files and `docs/reports/finance-assistant-l2-slice-c.md`, or
revert the merge commit. No production code, schema, dependency, configuration or deployment
changes, so nothing else needs to be rolled back. `FINANCE_SECURITY_GATE` stays BLOCKED either way.
