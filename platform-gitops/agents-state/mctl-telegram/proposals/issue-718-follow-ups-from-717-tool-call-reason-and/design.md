# Design: issue-718-follow-ups-from-717-tool-call-reason-and

## Current state
Tool-call recording (mctl-telegram#696, #717) lives in `internal/mcp`:

- `Server.audit` (`internal/mcp/tools.go` ~line 2397) stages a non-synthesized `callRecord`
  into the per-call `*callRecorder` (or writes through when no recorder is in ctx).
  Non-synthesized records pass `callRecord.feedsSLO()` (`internal/mcp/record.go` ~line 49),
  so `Server.writeAuditRow` increments `ToolInvocationsTotal{tool,status}` and observes
  `ToolInvocationDuration` — the availability SLO inputs.
- `Server.auditRefusal` (`tools.go` ~line 2433) calls `hintReason(ctx, reason)` and stages a
  record with `status="error"`, explicit `reason`, `synthesized=true`. It is used today by the
  `:rate_limited` refusals (`prepare_pin_message`, `edit_message`, `delete_messages`,
  `forward_messages`, `set_reaction`) and by the `rows == 0` paths in `set_account_send` /
  `set_send_consent`.
- `Server.flushRecordedCall` (`record.go` ~line 213), Rule 1: when the call failed and a
  record was staged, the last record's reason is reconciled from `explicitReason`, then
  `rec.snapshotHint()`, then `classifyReason(records[last].callPath, final)`. Rule 2 uses
  `classifyReason("", final)`.
- `classifyReason(_ string, final)` (`record.go` ~line 149) is a pure alias of
  `classifyToolResultReason(final)` (`internal/mcp/reasons.go` ~line 103). Its only test is
  `TestClassifyReason_CallPathDoesNotSteerClassification` (`reasons_test.go` ~line 108).

Refusal sites still using `s.audit` with an error (from the #717 review thread, r4150348371):

| Site | Tool label | Today's reason (classifier) |
|---|---|---|
| `tools.go:759` | `pin_message:blocked` | `refused` (text `pin blocked: ...` matches ` blocked: `) |
| `tools.go:825` | `disconnect_telegram_account` (demo reviewer) | `refused` (`demoReviewerAccountMgmtRefusal`) |
| `tools.go:880` | `delete_telegram_account` (demo reviewer) | `refused` |
| `tools.go:1389` | `revoke_local_bridge_device` (foreign/unknown device) | `unknown` (text `no such device on your account`) |
| `media_tools.go:207` | `get_media` `Confirms.Claim` failure | `confirmation_rejected` / `not_found` / `unknown` (in-flight) |
| `media_tools.go:242` | `get_media` media ref expired | `not_found` |

All of these feed `mctl_tool_invocations_total{status="error"}`.

`provision_local_account` (`tools.go` ~lines 1650-1676) uses a local `refuse` closure that
calls `s.audit(... err ...)`. The `db.ErrAccountAlreadyActive` branch (line ~1668) returns
"telegram id N already has an active account — use set_account_mode ..." which matches no
classifier literal, so the row reads `reason=unknown` and burns the SLO. By contrast the
`db.ErrUserNotFound` branches elsewhere (`tools.go` ~1248, 1587, 1735, 1788) call
`hintReason(ctx, ReasonNotFound)`.

`MctlToolHandlerFaults` (`deploy/alerts/mctl-telegram.rules.yaml` ~line 556) matches
`reason=~"panic|handler_error"`; `encode_failed` records are Rule 1 appended/synthesized and
never feed the SLO. Its scope is a recorded human decision (mctlhq/mctl-gitops#1478).

## Proposed solution
A mechanical, per-site change with no new helpers, constants, or metrics.

### 1. Move refusal sites to `auditRefusal`
- `pin_message` (`tools.go:759`):
  `s.auditRefusal(ctx, id, "pin_message:blocked", telegram.RedactPeer(peer), errors.New(blockReason), startedAt, ReasonRefused)`.
- Demo-reviewer guards (`tools.go:825`, `tools.go:880`):
  `s.auditRefusal(ctx, id, "<tool>", "", errors.New(demoReviewerAccountMgmtRefusal), startedAt, ReasonRefused)`.
- `revoke_local_bridge_device` (`tools.go:1389`): `auditRefusal(..., refuseErr, startedAt, ReasonNotFound)`.
  The single generic error text is kept so existence for another account is still not leaked
  (T7); the reason is the same for both "not found" and "wrong owner", which reveals nothing
  to the client (the reason is server-side only).
- `get_media` claim failure (`media_tools.go:206-226`): compute the reason from `cerr` before
  auditing — `ErrConfirmationMismatch`/`ErrConfirmationWrongUser` -> `ReasonConfirmationRejected`,
  `ErrConfirmationInFlight` -> `ReasonRefused`, default -> `ReasonNotFound` — then call
  `s.auditRefusal(ctx, id, "get_media", telegram.RedactPeer(peer), cerr, startedAt, reason)`.
  The `MediaStore.Delete` guard and the client-facing switch are unchanged (the reason switch
  can be folded into the existing switch by building `(reason, text)` then auditing once).
- `get_media` missing ref (`media_tools.go:242`): `auditRefusal(..., fmt.Errorf("media ref expired"), startedAt, ReasonNotFound)`.

Because `auditRefusal` both hints the reason and stages an error record, Rule 1 in
`flushRecordedCall` reconciles the record in place with the same reason; the record keeps
`synthesized=true`, so `writeAuditRow` skips the SLO pair while still writing the audit row,
the slog line and (Rule 5) `ToolCallErrorsTotal{tool,reason}`.

### 2. Retire `classifyReason`
Delete `classifyReason` from `record.go`; replace the two call sites in `flushRecordedCall`
with `classifyToolResultReason(final)`; update the stale comment in `recordToolCall`'s panic
branch that mentions `classifyReason`. Retarget
`TestClassifyReason_CallPathDoesNotSteerClassification` to the middleware: rename it
`TestFlushRecordedCall_CallPathDoesNotSteerClassification` (in `record_test.go`), with a test
tool whose handler stages `s.audit(..., errors.New("x"), startedAt, "local")` and returns
`NewToolResultError("query is required")` with no hint; assert the flushed `audit_logs.reason`
is `invalid_argument` (not `bridge_error`). A second sub-case with `callPath=""` covers Rule 2.

### 3. Explicit reason for `ErrAccountAlreadyActive`
Change the `refuse` closure in `toolProvisionLocalAccount` to take a reason and use
`s.auditRefusal(ctx, id, "provision_local_account", "", err, startedAt, reason)`. Callers:
non-positive `telegram_id` -> `ReasonInvalidArgument` (matches what the classifier already
yields for "must be"), `ErrAccountAlreadyActive` -> `ReasonRefused`. Store failures keep
`s.audit` + `s.storeErr` (genuine server faults keep feeding the SLO).

### 4. `encode_failed` alerting
No change. Recorded as an open question requiring an operator decision.

### Docs
Update the `auditRefusal` paragraph in `docs/runbook.md` (~lines 1522-1527) to list the new
classes of refusal: write-gate blocks, demo-reviewer guards, device-ownership refusals,
`get_media` confirmation/ref refusals and `provision_local_account` refusals. Extend the
`auditRefusal` doc comment in `tools.go` the same way.

## Alternatives
- **Classify synthesized-ness by reason instead of by call site** (e.g. `feedsSLO` returns
  false for `refused|not_found|confirmation_rejected|invalid_argument`). Rejected: it would
  silently drop genuine server-side `not_found` outcomes from the SLO and couples the SLO to
  a best-effort text classifier, which `classifyToolResultReason`'s doc comment explicitly
  says is never an authorization/control input. Per-site opt-in matches #717's design.
- **Add a new `ReasonAlreadyExists` / `ReasonConflict` constant for `ErrAccountAlreadyActive`.**
  Rejected for now: the `Reason*` set is a deliberately closed, bounded label set, and a new
  label needs dashboard/runbook updates for a single admin-only path. Recorded as an open
  question.
- **Keep `classifyReason` and just delete the parameter.** Rejected: an alias with no
  behaviour of its own adds an indirection with no benefit; the issue asks to fold it in.

## Platform impact
- Migrations: none. No schema, metric name, or label changes; `audit_logs.reason` values
  stay within the existing closed set.
- Backward compatibility: client-visible error texts are unchanged; audit rows keep the same
  tool names, status (`error`) and peer redaction. The only observable change is that these
  refusals stop incrementing `mctl_tool_invocations_total{status="error"}` /
  `mctl_tool_invocation_duration_seconds` and that `revoke_local_bridge_device`,
  `get_media` in-flight and `provision_local_account` rows gain explicit reasons instead of
  `unknown`. The SLO error ratio can drop slightly; that is the intended correction.
- Resource impact: negligible (fewer metric samples).
- Risks: (a) misclassifying a server fault as a refusal would hide it from the SLO — mitigated
  by touching only sites where the handler declined before doing any Telegram/store work
  (the `GetDevice` error at `tools.go:1387` collapses store errors into the refusal today;
  a transient store failure there will now skip the SLO too — accepted, since it already
  returns the generic refusal text and the row is still audited and counted in
  `mctl_tool_call_errors_total`). (b) Existing tests asserting `status="error"` for these rows
  (`TestToolPinMessage_ConsentBlocksWithoutConsumingConfirmation`,
  `TestToolDisconnect_DemoReviewerBlocked`, `TestToolDelete_DemoReviewerBlocked`) keep
  passing because `auditRefusal` still writes `status="error"` with the same message.
