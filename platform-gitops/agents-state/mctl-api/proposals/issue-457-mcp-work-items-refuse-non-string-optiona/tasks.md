# Tasks: issue-457-mcp-work-items-refuse-non-string-optiona

- [ ] 1. In `internal/mcp/workitems.go`, change `idArg` to look up the raw argument and return an error
  result `"<name> must be a string id"` when the key is present and the value is not a `string`
  (including nil from JSON null); keep trim, required-empty and `workItemIDPattern` checks unchanged.
  — DoD: absent / "" / whitespace optional ids behave as before; non-string values are refused before any HTTP call.
- [ ] 2. Rename `requiredPathArg` to `requiredIDArg` (function, doc comment, and all call sites in
  `toolGetWorkItem`, `toolListWorkItemExecutions`, `toolListWorkItemSnapshots`,
  `toolListWorkItemExecutionRequests`, `toolRequestWorkItemExecution`). (independent of 1) —
  DoD: `grep -rn requiredPathArg` returns nothing; `go build ./...` passes.
- [ ] 3. Add tests (depends on 1). — DoD: tests T1-T4 pass; `go fmt`, `go vet ./...`,
  `golangci-lint run`, `go test ./...` clean.

## Tests
- [ ] T1. New table test in `internal/mcp/workitems_test.go`: for each of `float64(5)`, `true`, `nil`,
  `map[string]any{}`, `[]any{"cs_1"}`, call `toolListWorkItemSnapshots` with `snapshot_id` set and
  `toolListWorkItemExecutionRequests` with `request_id` set; assert `IsError`, the message names the
  argument, and the backend recorded zero calls.
- [ ] T2. Extend `TestRequestWorkItemExecutionRefusesBadArgumentsWithoutCalling` with cases
  "numeric from" (`resumed_from_execution_id = float64(5)`) and "null from" (`= nil`), and
  "numeric work item" (`work_item_id = float64(1)`); still zero API calls.
- [ ] T3. Regression: `snapshot_id` / `request_id` absent and `""` still hit the list path
  (`GET /api/v1/work-items/wi_1/snapshots`, `.../execution-requests`), and absent
  `resumed_from_execution_id` is still omitted from the POST body.
- [ ] T4. Existing tests (`TestWorkItemToolsRefuseIDsThatAreNotOneSegment`, the route table test,
  token-forwarding test) pass unchanged.

## Rollback
Revert the single commit (one Go file plus its test file) and redeploy the previous mctl-api image.
No data, schema or config changes need to be undone.
