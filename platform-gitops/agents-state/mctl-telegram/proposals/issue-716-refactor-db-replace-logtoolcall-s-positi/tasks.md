# Tasks: issue-716-refactor-db-replace-logtoolcall-s-positi

- [ ] 1. Add the `ToolCall` struct (fields `UserID`, `Tool`, `PeerRedacted`, `Status`, `ErrMsg`, `CallPath`, `Reason`) to `internal/db/store.go` above `LogToolCall`, with field doc comments. Change the signature to `LogToolCall(ctx context.Context, c ToolCall)`. Keep the body semantics identical: same SQL, same `nullable(...)` wrapping, same `hashAuditEntry` arguments, `Reason` not hashed. Update the doc comment to the field names and drop the "~25 existing call sites" remark. — DoD: `go build ./internal/db/` passes for non-test code, and the diff of the method body only renames identifiers.
- [ ] 2. (depends on 1) Migrate the non-test callers in `internal/agentapi` (`json.go:75`, `profilehandler.go:195,214`) and `internal/mcp/tools.go:2551` to keyed `db.ToolCall{...}` literals. — DoD: every `rec.*` field in `writeAuditRow` maps to the field of the same meaning.
- [ ] 3. (depends on 1) Migrate the `internal/oauth` callers: `demo_login.go`, the 15 calls in `enable_access.go`, `local_bridge_activate.go`, the 6 calls in `local_bridge_credential.go`, and `server.go`. Omit zero-valued fields, but keep the `UserID: 0` intent visible at `local_bridge_credential.go:307,391`. — DoD: `go build ./internal/oauth/` passes.
- [ ] 4. (depends on 1) Migrate the `internal/web` callers: `account.go:121` (keep `Reason: reasonScopeDenied`), `account.go:384`, `broadcasts.go:105,459`, `manage_notifications.go:186`. — DoD: `go build ./internal/web/` passes.
- [ ] 5. (depends on 1) Migrate the test call sites in `internal/db` (`audit_chain_test.go`, `audit_edge_test.go`, `connect_step_test.go`, `store_audit_test.go`, `identity_migration_test.go`) to `ToolCall{...}`. Change only the call expressions; leave assertions, expected values and the `hashAuditEntry` calls untouched. — DoD: `git diff` on these files contains only `LogToolCall(` lines.
- [ ] 6. (depends on 2-5) Check for leftovers with `rg -n 'LogToolCall\(' --type go`. Every match must be a `ToolCall{` literal or a comment, and no wrapper may exist. Run `gofmt`, `go vet ./...` and `golangci-lint run`. Commit everything as a single `refactor(db):` commit. — DoD: lint is clean, the PR contains one commit, and the PR description states that the change is shape-only.

## Tests
- [ ] T1. `go build ./... && go vet ./... && go test ./...` pass.
- [ ] T2. `TestLogToolCall_ReasonIsExcludedFromTheHash`, `TestLogToolCall_ChainsAcrossEntries`, `TestLogToolCall_RecordsHowTheCallArrived`, `TestLogToolCall_LeavesCorrelationEmptyWithoutAnEdgeContext`, all `TestVerifyAuditChain_*` tests, and the `connect_step_test.go` / `store_audit_test.go` tests pass with unchanged assertions.
- [ ] T3. `internal/mcp`, `internal/oauth`, `internal/web` and `internal/agentapi` tests that read audit rows (for example the scope-denied reason path in `internal/web/account.go` and the MCP `writeAuditRow` tests) pass unchanged.
- [ ] T4. A grep for a positional `LogToolCall(ctx, <int>, "...", ...)` pattern returns no Go matches. No new test is needed: the compiler enforces the new shape.

## Rollback
Revert the single refactor commit. The change touches no schema, migration, config or stored data, and rows written by either binary hash identically. A revert therefore restores the positional signature with no data or audit-chain impact.
