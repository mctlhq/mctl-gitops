# Tasks: issue-651-feat-finops-expose-model-usage-devloop-c

- [ ] 1. Create `internal/mcp/usage.go` with `toolGetUsageSummary()`. It defines `mctl_get_usage_summary` with title "Model usage summary" and annotations readOnly=true, destructive=false, idempotent=false. Args:
  - string args `workflow_id`, `run_id`, `execution_id`, `work_item_id`, `repository`, `agent`, `stage`, `provider`, `model`, `outcome`, `since`, `until`;
  - integer args `issue`, `pr`, `limit` (limit 1..`usage.MaxQueryLimit`);
  - an enum arg `group_by` over the nine `usage.GroupBy` values plus the aliases `stage` and `model`, defaulting to `devloop_stage`.

  The description covers admin-only access, cost semantics, the total/truncation rule, 503 = UNKNOWN, and incomplete producer coverage.

  DoD: args are parsed with `strictStringArg` and integer validation, and a bad value returns a tool error before any HTTP call. `group_by` is always sent explicitly.
- [ ] 2. Implement the handler (depends on 1). It calls `s.apiGetStatus("/api/v1/usage/summary?...")` with the caller's token:
  - 503 maps to the error "usage ledger unavailable: spend is UNKNOWN, not zero";
  - any other status of 400 or above maps to `Failed to get usage summary (HTTP n): <msg>`;
  - a transport error maps to a tool error.

  DoD: no path returns a success result on a non-2xx response.
- [ ] 3. Implement `sumUsageBuckets` and the output assembly (depends on 2). Decode with `UseNumber` and pass buckets through verbatim:
  - when `truncated=false`, add `total`: count, the six token dimensions as int64 sums (null if absent in every bucket), and the three costs each summed separately with `big.Rat` (null if absent in every bucket);
  - when `truncated=true`, add `total_unavailable_reason` instead of `total`;
  - always add the static `cost_semantics`;
  - on an empty bucket list, add a `note` that no records matched (not evidence of zero spend).

  DoD: `truncated`, `truncated_by`, `limit` and `group_by` are re-emitted unchanged, and no cost field is ever added into another.
- [ ] 4. Register the tool in `NewMCPServer` (`internal/mcp/server.go`) next to the commerce reads, with a `// Model-usage ledger reads (mctl-api#651, ADR-012).` comment (depends on 1). DoD: the tool shows up in `ListTools()`.
- [ ] 5. Add `mctl_get_usage_summary` to `recordedHints` and to the `want` list in `TestReadOnlyToolsAreTheRecordedSet` (`internal/mcp/annotations_test.go`) (depends on 4). DoD: `TestNewMCPServer_ToolCount` and the annotation tests pass.
- [ ] 6. Add an explicit entry to `docs/portal-allowlist.json`: `"enabled": false`, with a tool-specific reason (internal workflow/repo/issue ids and estimated spend, no model content, pending owner decision, mctl-api#651) (depends on 4). DoD: `portal_allowlist_test.go` passes. The reviewer is told the vendored copy in mctl-gitops needs the same entry.
- [ ] 7. Add an "MCP" subsection for the tool to `docs/model-usage-ledger.md`: name, default grouping, the total-only-when-not-truncated rule, and cost labels. DoD: the doc matches the behaviour.
- [ ] 8. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run` and `go test ./...`. DoD: all clean, and `internal/api/handlers_usage_test.go` passes unmodified.

## Tests

All the tests below go in a new `internal/mcp/usage_test.go`, against an `httptest.NewServer` fake API, as in `commerce_test.go`.

- [ ] T1. A #663-shaped workflow. The fake API asserts it received `workflow_id=dev-loop-mctlhq-mctl-agents-663&group_by=devloop_stage` and returns `truncated=false` with these buckets:
  - `investigator`: count 1, calculated_cost "1.25", input_tokens 100;
  - `implementer`: count 2 (two models), calculated_cost "3.40", input_tokens 300, cache_read_tokens 50.

  Assert that both buckets come back unchanged and that `total` is count 3, input_tokens 400, cache_read_tokens 50, calculated_cost exactly 4.65, with provider_reported_cost and invoice_reconciled_cost null (not 0). Nothing is double counted.
- [ ] T2. A truncated response (`truncated=true`, `truncated_by=record_count`, `limit=2`). Assert there is no `total`, `total_unavailable_reason` is set, and the truncation metadata is preserved.
- [ ] T3. Distinct costs. Buckets carry provider_reported_cost 0.5, calculated_cost 0.7 and invoice_reconciled_cost 0.9. Assert the totals are 0.5, 0.7 and 0.9 separately, that no field equals 2.1, and that `cost_semantics.calculated_cost` contains "estimate" and "not provider-billed".
- [ ] T4. The fake API returns 503 `usage ledger not configured`. Assert `IsError` is set and the text contains "UNKNOWN, not zero". No result has a zero total.
- [ ] T5. The fake API returns 403 `usage ledger is admin-only`. Assert the tool error relays that message and the request carried the caller's bearer token.
- [ ] T6. Argument validation. A non-string `workflow_id`, `issue=0`, `issue=1.5`, `limit=1001`, and `group_by=bogus` are each refused before any HTTP call (the fake server counts zero requests). `group_by=stage` is sent as `devloop_stage`. An omitted `group_by` is sent as `devloop_stage`.
- [ ] T7. Filter mapping. Every filter arg appears as the identically named query parameter, and an empty string is not sent.
- [ ] T8. An empty bucket list. Assert `total.count == 0`, the costs are null, and `note` is present.
- [ ] T9. Existing `TestUsageHandlers_*` in `internal/api/handlers_usage_test.go` pass unmodified, which shows the HTTP semantics are unchanged.

## Rollback

The change is purely additive in `internal/mcp` and `docs`. Roll back by reverting the PR: delete `internal/mcp/usage.go` and its test, and remove the registration line, the `recordedHints` entry, the read-only list entry and the `docs/portal-allowlist.json` entry. Then redeploy mctl-api. No data, schema or HTTP contract is touched, so nothing needs migrating back. If the portal entry was enabled and vendored into mctl-gitops, set it back to `enabled: false` there as well.
