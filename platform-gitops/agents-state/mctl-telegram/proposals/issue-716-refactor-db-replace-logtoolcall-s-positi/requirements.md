# Replace LogToolCall's positional string parameters with a db.ToolCall params struct

## Context
`Store.LogToolCall` in `internal/db/store.go` (currently line 1957 on `main`, not 1752 as the issue says) has the signature
`LogToolCall(ctx context.Context, userID int64, tool, peerRedacted, status, errMsg, callPath, reason string)`.
It ends in six consecutive `string` parameters. If two of them are swapped (`status`/`errMsg`, `callPath`/`reason`), the code still compiles but writes a wrong, hash-chained audit row. Nothing catches the mistake at build time, and because the row is part of the per-user hash chain it cannot be fixed afterwards without breaking the chain.

Issue #716 (split out of #703) asks for a shape-only refactor. Add a `db.ToolCall` struct with named fields, change the method to `LogToolCall(ctx, db.ToolCall)`, and migrate every call site in a single commit with no positional wrapper. The audit-row content, the hash input, and the `reason` exclusion from `hashAuditEntry` must not change.

## User stories
- AS a contributor adding an audit event I WANT to name each audit field at the call site SO THAT swapping two string arguments cannot silently produce a wrong audit row.
- AS a reviewer I WANT the refactor to be purely mechanical and separate from behaviour changes SO THAT I can verify that no audit row changes.
- AS an operator I WANT audit rows and hash-chain verification to stay byte-identical across the change SO THAT existing chains keep verifying after deploy and after rollback.

## Acceptance criteria (EARS)
- WHEN the change is merged THE SYSTEM SHALL expose `db.ToolCall` with exported fields `UserID int64`, `Tool`, `PeerRedacted`, `Status`, `ErrMsg`, `CallPath`, `Reason string`, and `(*Store).LogToolCall(ctx context.Context, c ToolCall)` as the only LogToolCall method.
- WHEN any caller writes an audit row THE SYSTEM SHALL persist the same column values (`user_id`, `tool_name`, `peer_redacted`, `status`, `error`, `call_path`, `reason`, edge columns) and the same `entry_hash` that the positional version wrote for the same inputs.
- WHILE `LogToolCall` builds the row THE SYSTEM SHALL keep `Reason` out of `hashAuditEntry`'s input, and SHALL keep storing `CallPath` as a non-NULL string (empty for hosted calls).
- WHEN a `ToolCall` field is left at its zero value THE SYSTEM SHALL treat it exactly as the positional `""` / `0` argument was treated (NULL for `peer_redacted`, `error`, `reason`; `""` for `call_path`; user 0 for `UserID`).
- IF any non-test or test code in the module still calls `LogToolCall` positionally THEN THE SYSTEM SHALL fail to compile. No positional overload or wrapper may exist.
- WHEN `go build ./... && go vet ./... && go test ./...` run on the change THE SYSTEM SHALL pass. The audit-chain tests (`TestLogToolCall_ReasonIsExcludedFromTheHash`, `TestLogToolCall_ChainsAcrossEntries`, the `TestVerifyAuditChain_*` tests) SHALL pass with their assertions unchanged. Only their `LogToolCall(...)` call expressions are rewritten to the struct form.

## Out of scope
- Any behaviour change: new audit fields, new `reason` values, changed `status` vocabulary, or wiring edge context into web/OAuth handlers (#703, #700, #617).
- Changes to `hashAuditEntry`, `VerifyAuditChain`, the `audit_logs` schema, or migrations.
- Making `LogToolCall` return an error.
- Refactoring the `agentapi` `audit` helper or the `internal/mcp` `writeAuditRow` record type beyond what the new call shape needs.

## Open questions
- The issue says the audit-chain tests must "pass unchanged", but those tests (`internal/db/audit_chain_test.go`, `audit_edge_test.go`, `connect_step_test.go`, `store_audit_test.go`, `identity_migration_test.go`) call `LogToolCall` positionally and cannot compile against the new signature. This proposal reads "unchanged" as "assertions and expected values unchanged; only the call expressions migrate to `db.ToolCall{...}` literals". `hashAuditEntry` calls inside the tests stay positional because that function is not in scope.
- Struct name: the issue proposes `ToolCall`. `internal/db` has no existing `ToolCall` symbol, so the name is free. `ToolCallEntry` or `AuditRecord` would also work, but this proposal keeps the issue's `ToolCall`.
