# Tasks: issue-703-follow-ups-from-700-mcp-tool-call-failur

Ordered so each task compiles and tests green on its own. Tasks 1-4 are the
classification slice, 5-8 the recording-semantics slice, 9-12 the
API/docs/tests slice.

- [ ] 1. Add the reason-hint channel in `internal/mcp/record.go`: a `hint
  string` field on `callRecorder` (guarded by its existing mutex, last writer
  wins), `hintReason(ctx, reason)` (no-op with no recorder in ctx), and a
  `snapshotHint()` accessor. Wire the precedence in `flushRecordedCall`:
  `explicitReason` > hint > `classifyReason`. — DoD: `go build ./...` clean;
  a new unit test proves a hinted reason beats a contradicting result text, and
  that `ReasonPanic`/`ReasonHandlerError` still beat a hint; every existing
  test in `internal/mcp` passes unchanged.

- [ ] 2. Emit `ReasonStoreError` (depends on 1): add `func (s *Server)
  storeErr(ctx context.Context, tool string, err error) *mcplib.CallToolResult`
  that hints `ReasonStoreError` and returns `toolErr("%s: %v", tool, err)`, and
  convert the `*db.Store`-failure sites in `internal/mcp/tools.go`,
  `media_tools.go` and `broadcast_tools.go` (the `toolErr("<tool>: %v", err)`
  shape following a `s.Store.*` call) to use it. — DoD: `grep -rn
  ReasonStoreError internal/mcp` shows at least one non-test emitting site;
  a table test asserts a forced store failure on `get_my_send_status` (or
  another store-backed tool) records `reason=store_error`; the constant's doc
  comment in `reasons.go` names `Server.storeErr` as its emitter.

- [ ] 3. Fix the two misclassifications (depends on 1):
  (a) move `"confirmation_id required"` out of the `ReasonNotFound` arm of
  `classifyToolResultReason` into the argument-validation switch, and hint
  `ReasonInvalidArgument` at the `get_media` / `prepare_pin_message` /
  `prepare_send_message` confirmation-required refusals;
  (b) hint `ReasonTelegramError` from `borrowErrResult` (adding a leading `ctx
  context.Context` parameter) and its session-sentinel / `ErrPoolFull` /
  `mtprotoErrResult` branches, so an MTProto code in neither catalog no longer
  classifies as `unknown`. — DoD: `reasons_test.go` row for `"confirmation_id
  required — call prepare_get_media first"` expects `ReasonInvalidArgument`; a
  new test drives an unenumerated `tgerr.Error` through `borrowErrResult` and
  gets `telegram_error`; `go vet ./...` clean.

- [ ] 4. Bridge/`callPath` correction (depends on 1): hint `ReasonBridgeError`
  at the sites where the call actually reached the daemon (`bridgeCall`'s
  failure returns and the `bridgeResultErr` audit sites in `tools.go` /
  `media_tools.go`), hint `ReasonModeUnsupported` at the local-mode refusals
  that never call the bridge (`tools.go:280-286`, `tools.go:549-555`, the
  media equivalents), then delete the `callPath == "local"` shortcut from
  `classifyReason` (leaving it as a thin alias for
  `classifyToolResultReason`). The `s.audit(..., "local")` calls keep writing
  `call_path="local"` — routing fact, not classification. — DoD: a test proves
  `get_unread_messages` with `fetch_media=true` on a `local` account records
  `reason=mode_unsupported` with `call_path="local"`, and that a failing bridge
  relay still records `bridge_error`.

- [ ] 5. `errors.As` for `jsonrpcCoder` in `Server.jsonrpcHooks`
  (`record.go:301`). — DoD: a test wraps a `requestError`-shaped error with
  `fmt.Errorf("%w")` and asserts the `mcp jsonrpc error` slog line carries the
  real non-zero `jsonrpc_code`.

- [ ] 6. Rule 1 split (depends on 1): reconcile in place only when the last
  staged record has `status == "error"`; when it has `status == "ok"`, leave it
  and append a new synthesized error record for `req.Params.Name`. — DoD:
  a test audits `send_message:sent` as `ok` then forces an encode failure and
  asserts two rows — `send_message:sent`/`ok` intact plus
  `send_message`/`error`/`encode_failed`;
  `TestFlushRecordedCall_ReconcilesEncodeFailureAfterOKAudit` is updated to the
  two-row expectation and renamed to match what it now pins; Rule 5 still
  increments exactly one `ToolCallErrorsTotal` sample.

- [ ] 7. **AMENDED (human review, 2026-10-01):** rename `exemptFromSLO` →
  `synthesized` and set it on every record `flushRecordedCall` creates (Rule 1
  append, Rule 2, Rule 3); gate `writeAuditRow`'s SLO samples on
  `feedsSLO() = !r.synthesized`. Do NOT add `serverFaultReason`. — DoD:
  scope-denied, a panicking handler, a handler_error and a Rule 3 success
  each contribute 0 to both SLO series; a record staged by `Server.audit`
  contributes exactly as today; `grep -rn exemptFromSLO` and
  `grep -rn serverFaultReason` return nothing.
  Original task, superseded: ~~`exemptFromSLO` → `synthesized` + `feedsSLO` (depends on 6): rename the
  `callRecord` field, set it on every record `flushRecordedCall` creates (Rule
  1's append, Rule 2, Rule 3), add `serverFaultReason` (`panic`,
  `handler_error`, `store_error`, `encode_failed`) next to the `Reason*` block,
  and gate `writeAuditRow`'s `ToolInvocationDuration`/`ToolInvocationsTotal`
  samples on `rec.feedsSLO()`. — DoD: scope-denied (Rule 2, client fault) still
  contributes 0 to both SLO series; a panicking handler contributes 1 to
  `ToolInvocationsTotal{tool,"error"}` and one duration sample; a Rule 3
  success contributes 0; `grep -rn exemptFromSLO` returns nothing.~~

- [ ] 8. `labelTool` allowlist (independent of 1-7): thread an
  `atomic.Pointer[map[string]struct{}]` from `newMCPServer` into
  `s.jsonrpcHooks(...)`, populate it from `srv.ListTools()` after every
  `addTool`/`addToolUI` call, and emit the verbatim `tool` label only for a
  name in that set — `"unregistered"` otherwise, including when the pointer is
  nil. — DoD: a test asserts `capability_disabled` with a client-supplied name
  labels `unregistered`; a registered tool name still labels verbatim; the
  `mcp jsonrpc error` slog line still carries the verbatim name.

- [ ] 9. **WITHDRAWN (human review, 2026-10-01) → mctlhq/mctl-telegram#716.**
  Do not change `Store.LogToolCall`'s signature in this PR.
  Original task, not to be implemented: ~~`db.ToolCall` params struct (independent): introduce the struct in
  `internal/db/store.go`, change `Store.LogToolCall` to
  `(ctx, ToolCall)`, and migrate every call site —
  `internal/mcp/tools.go:2403`, `internal/agentapi/json.go:75`,
  `internal/agentapi/profilehandler.go:182,201`, and the `internal/db` tests
  (`audit_chain_test.go`, `audit_edge_test.go`, `connect_step_test.go`,
  `identity_migration_test.go`, `store_audit_test.go`). — DoD: `go build
  ./... && go test ./...` clean; no positional-string overload left behind; the
  doc comment block above `LogToolCall` is preserved verbatim apart from the
  parameter description.~~

- [ ] 10. `MctlToolHandlerFaults` alert (depends on 7): add the rule to the
  `mctl-telegram-tool-availability` group in
  `deploy/alerts/mctl-telegram.rules.yaml`, a silence/firing pair in
  `deploy/alerts/mctl-telegram.rules_test.yaml`, and the runbook section with
  an explicit `<a id="mctltoolhandlerfaults"></a>` anchor. **AMENDED:** the
  expression stays `reason=~"panic|handler_error"`; the runbook section states
  that `store_error` and `encode_failed` are observable in
  `mctl_tool_call_errors_total` but not alerted by this rule. — DoD:
  `go test ./deploy/alerts/...` passes (`TestRunbookURLsResolve` resolves the
  new anchor) and the promtool job in `.github/workflows/build.yml` passes both
  the silence and the firing case.

- [ ] 11. Runbook prose (depends on 7, 10): in `docs/runbook.md`'s
  `#### Tool-call error breakdown (mctl-telegram#696)` section add (a) the
  "why the two families deliberately disagree" paragraph, (b) the Rule 2 row
  volume + chain-lock paragraph naming `RATE_LIMIT_PER_USER` (default 30/min →
  ≤1800 rows/hour/identity) and `AUDIT_RETENTION_DAYS`, and (c) update the
  reason list if any reason's meaning changed. **AMENDED:** (a) must state
  that synthesized records (every Rule 1 append, Rule 2 and Rule 3 record)
  never feed the SLO pair, so server faults are visible in the error counter
  and the `MctlToolHandlerFaults` alert, not in the availability SLO. It must
  also state, next to the alert description from task 10, that `store_error`
  and `encode_failed` are observable in `mctl_tool_call_errors_total` but are
  not alerted. — DoD: section reads correctly
  against the shipped rule file; `internal/mcp/troubleshooting_doc_test.go` and
  `deploy/alerts/runbook_links_test.go` pass.

- [ ] 12. Test-comment corrections (depends on 7): rewrite the comment at
  `internal/mcp/record_test.go:155-166` to name `synthesized`
  (**AMENDED:** not `serverFaultReason`, which is not added) instead of a missing elapsed duration, and fix
  `histogramSampleCount`'s doc line to describe the single `tool` label on
  `mctl_tool_invocation_duration_seconds`. — DoD: comments match the code they
  sit above; no behavioural change in the diff for this task.

## Tests

- [ ] T1. `TestHintReason_BeatsTextClassification` — a handler hints
  `store_error` while returning text that would classify as `not_found`; the
  audit row and `ToolCallErrorsTotal` both read `store_error`.
- [ ] T2. `TestHintReason_LosesToPanicAndHandlerError` — a hinting handler that
  then panics records `panic`, not the hint.
- [ ] T3. `TestClassifyToolResultReason_ConfirmationRequiredIsInvalidArgument` —
  table row for each `confirmation_id required — call prepare_* first` literal.
- [ ] T4. `TestBorrowErrResult_UnenumeratedMTProtoIsTelegramError` — a
  `tgerr.Error` with a code in neither catalog records `telegram_error`.
- [ ] T5. `TestMTProtoCatalog_NoMessageIsAPrefixOfAnother` — guards the
  `mtprotoErrCatalog` prefix loop against map-iteration-order dependence.
- [ ] T6. `TestFlushRecordedCall_KeepsCompletedActionRow` — `send_message:sent`
  audited `ok`, then an encode failure: two rows, the `ok` row byte-identical,
  one `ToolCallErrorsTotal{send_message,encode_failed}` increment.
- [ ] T7. `TestRecordToolCall_LocalRefusalIsNotBridgeError` —
  `fetch_media=true` on a `local` account: `reason=mode_unsupported`,
  `call_path="local"`.
- [ ] T8. **AMENDED:** `TestFeedsSLO_SynthesizedNeverFeedsSLO` — panic,
  handler_error, scope_denied, invalid_argument and a Rule 3 success each
  contribute zero `ToolInvocationsTotal` samples and zero duration samples; a
  record staged by `Server.audit` still contributes one. Mutation-check: making
  `feedsSLO` return true for a panic must fail the test.
  Original, superseded: ~~`TestFeedsSLO_ServerFaultCountsClientFaultDoesNot` — panic and
  handler_error each contribute one sample; client faults and Rule 3 contribute zero.~~
- [ ] T9. `TestJSONRPCHook_WrappedErrorKeepsCode` — a wrapped `requestError`
  logs a non-zero `jsonrpc_code`.
- [ ] T10. `TestJSONRPCHook_UnregisteredLabelIsAllowlisted` — a
  `capability_disabled` rejection with an arbitrary client-supplied name labels
  `unregistered`; a registered name labels verbatim; the filtered-out case
  (`ToolFilter: "read-only"` on a write tool) also labels `unregistered`.
- [ ] T11. **WITHDRAWN → #716.** ~~`go test ./internal/db/...` after the `ToolCall` migration —
  `TestLogToolCall_ReasonIsExcludedFromTheHash` and the chain tests pass
  unchanged, proving the struct move is shape-only.~~
- [ ] T12. `go test ./deploy/alerts/...` plus the promtool unit test for
  `MctlToolHandlerFaults` (silence and firing).
- [ ] T13. Snapshot guard: `docs/tool-descriptors.json` and
  `portal_allowlist_test.go` unchanged — no client-visible surface moved.

## Rollback

Every change is code, docs and one alert rule; there is no migration, no schema
change and no persisted state to unwind, so a `git revert` of the merge commit
restores the previous behaviour exactly. Rows written while the change was live
keep the reason they were written with (`reason` is outside the audit hash
chain, so nothing re-verifies inconsistently) and the two extra Prometheus
sample sources simply stop.

Partial rollbacks, in increasing order of preference:

1. **AMENDED: not applicable.** `feedsSLO` already is `!r.synthesized`, so the
   SLO input set does not change and there is no SLO-noise rollback. Original:
   ~~**SLO noise only**: change `feedsSLO` back to `return !r.synthesized`.~~ One line; keeps
   every classification fix and the new `MctlToolHandlerFaults` alert, which
   then carries the handler-fault signal alone (design.md Alternative 4).
2. **Alert too noisy:** raise `for:` on `MctlToolHandlerFaults` or drop the rule
   from `deploy/alerts/mctl-telegram.rules.yaml`; the runbook anchor may stay,
   and `runbook_links_test.go` only checks the alert → runbook direction.
3. **Rule 1 append unwanted:** revert task 6 alone; tasks 1-5 and 7-12 do not
   depend on the append except through `synthesized`, which stays correct for
   Rules 2 and 3.

Deploy verification before considering it done: for one 24h window after
rollout, compare `sum(rate(mctl_tool_invocations_total[1h]))` against the same
window pre-deploy on `deploy/grafana/mctl-telegram-beta.json`, and confirm
`sum by (reason) (rate(mctl_tool_call_errors_total[1h]))` shows no `unknown`
growth where `store_error` / `telegram_error` should now appear.
