# Tasks: issue-718-follow-ups-from-717-tool-call-reason-and

- [ ] 1. Move `pin_message:blocked` (`internal/mcp/tools.go` ~759) to `s.auditRefusal(..., ReasonRefused)` — DoD: no `s.audit` call remains for that label; client text unchanged.
- [ ] 2. Move the demo-reviewer guards in `toolDisconnectAccount` / `toolDeleteAccount` (`tools.go` ~825, ~880) to `s.auditRefusal(..., ReasonRefused)` — DoD: guards still return `demoReviewerAccountMgmtRefusal` before any pool/DB mutation.
- [ ] 3. Move `revoke_local_bridge_device`'s ownership refusal (`tools.go` ~1389) to `s.auditRefusal(..., ReasonNotFound)` — DoD: same generic text `no such device on your account` for both unknown and foreign devices.
- [ ] 4. In `get_media` (`internal/mcp/media_tools.go` ~206-226), derive the reason from `cerr` (mismatch/wrong-user -> `ReasonConfirmationRejected`, in-flight -> `ReasonRefused`, default -> `ReasonNotFound`) and record via `s.auditRefusal`; move the missing-ref refusal (~242) to `s.auditRefusal(..., ReasonNotFound)` — DoD: `MediaStore.Delete` guard on non-in-flight failures and client texts unchanged.
- [ ] 5. Change `toolProvisionLocalAccount`'s `refuse` closure (`tools.go` ~1650) to take a reason and call `s.auditRefusal`; pass `ReasonInvalidArgument` for the bad `telegram_id` and `ReasonRefused` for `db.ErrAccountAlreadyActive` — DoD: store-error branches still use `s.audit` + `s.storeErr`.
- [ ] 6. Delete `classifyReason` from `internal/mcp/record.go`; replace both call sites in `flushRecordedCall` with `classifyToolResultReason(final)`; fix the comment in `recordToolCall` that names `classifyReason` — DoD: `git grep classifyReason` returns nothing; `go build ./...` passes.
- [ ] 7. (depends on 1-5) Update the `auditRefusal` doc comment in `tools.go` and the refusal paragraph in `docs/runbook.md` (~1522-1527) to list the new refusal classes — DoD: docs match the code's call sites.
- [ ] 8. (depends on 1-7) Run `go fmt`, `go vet ./...`, `golangci-lint run`, `go test ./...` — DoD: all green.

## Tests
- [ ] T1. Extend `TestRefusalPaths_AuditOneErrorRow` (`internal/mcp/record_test.go`) or add a table test driving each refusal through `newMCPServer()` with a `metrics.New()` registry: `pin_message` with send disabled, demo-reviewer disconnect and delete, `revoke_local_bridge_device` with a foreign device id, `get_media` with an unknown confirmation id, `get_media` with a claimed confirmation whose media ref was deleted, `provision_local_account` for an already-active account and with `telegram_id=0`. For each assert: exactly one `audit_logs` row, status `error`, expected reason, `ToolInvocationsTotal{tool,*}` == 0, `ToolCallErrorsTotal{tool,reason}` == 1.
- [ ] T2. `get_media` claim reason mapping: mismatch and wrong-user -> `confirmation_rejected`; in-flight -> `refused` (and `MediaStore` ref preserved); expired -> `not_found`.
- [ ] T3. Replace `TestClassifyReason_CallPathDoesNotSteerClassification` with `TestFlushRecordedCall_CallPathDoesNotSteerClassification`: a handler stages `s.audit(..., callPath "local")` and returns `query is required` without a hint -> reason `invalid_argument`; a handler that stages nothing (Rule 2) -> `invalid_argument`.
- [ ] T4. Existing tests remain green unchanged: `TestToolPinMessage_ConsentBlocksWithoutConsumingConfirmation`, `TestToolDisconnect_DemoReviewerBlocked`, `TestToolDelete_DemoReviewerBlocked`, `TestGetMedia_GateRefusalPreservesConfirmation`, and the `reasons_test.go` table.
- [ ] T5. Regression guard: a genuine server failure path (e.g. `pin_message` MTProto error via `borrowWithRetry`) still increments `ToolInvocationsTotal{tool,"error"}`.
- Test fixtures use synthetic ids/personas only (Alice, Bob, Carol, Dana); check new numeric ids with `git grep` first.

## Rollback
The change is code-only in `internal/mcp` plus docs; no migrations, metric renames, or alert
edits. Roll back by reverting the merge commit and cutting a new patch release (or redeploying
the previous image tag via `mctl_rollback_service`). The only effect of rolling back is that
these refusals resume feeding the availability SLO and some rows revert to `reason=unknown`.
