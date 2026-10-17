# Tasks: issue-651-feat-finops-expose-model-usage-devloop-c

- [ ] 1. Extract a raw-body GET helper from `workItemCall` in `internal/mcp/workitems.go` (same request, token and `Failed to <what> (HTTP n): body` error behaviour), and make `workItemCall` use it — DoD: existing work-item and commerce MCP tests pass unchanged.
- [ ] 2. Create `internal/mcp/usage.go` with `toolGetUsageSummary()`: read-only/non-destructive/idempotent=false annotations, argument set from requirements.md, validation (`strictStringArg`, integral positive `issue`/`pr` requiring `repository`, `limit` in 1..`usage.MaxQueryLimit`), `group_by` default `devloop_stage` and `stage` alias, relay to `GET /api/v1/usage/summary` (depends on 1) — DoD: tool compiles, description states admin-only, ledger-backed, default grouping, cost semantics, 503 meaning.
- [ ] 3. Implement response post-processing in `usage.go`: decode buckets as `[]*usage.Bucket`, preserve every original API key, add `total` via per-field nil-preserving `sumBuckets` only when `truncated` is false, else `total: null` + `total_unavailable_reason`; add `cost_semantics` (depends on 2) — DoD: provider_reported, calculated and invoice_reconciled stay separate fields in buckets and total.
- [ ] 4. Register the tool in `NewMCPServer` (`internal/mcp/server.go`) near the DevLoop/agent-registry admin reads (depends on 2) — DoD: `tools/list` includes `mctl_get_usage_summary`.
- [ ] 5. Add `mctl_get_usage_summary` to `recordedHints` and to `TestReadOnlyToolsAreTheRecordedSet` in `internal/mcp/annotations_test.go` (depends on 4) — DoD: `TestNewMCPServer_ToolCount` and annotation tests pass.
- [ ] 6. Add an explicit `docs/portal-allowlist.json` entry (`enabled: true`, tool-specific reason >= 40 chars, no invented owner-decision date) (depends on 4) — DoD: `TestPortalAllowlist_CoversEveryRegisteredTool` passes; PR description asks the owner to confirm the enablement.
- [ ] 7. Document the tool in `docs/model-usage-ledger.md` and `CHANGELOG.md` — DoD: docs show the DevLoop-by-stage example and the cost/total semantics.
- [ ] 8. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run`, `go test ./...` — DoD: all clean.

## Tests

- [ ] T1. #663-shaped workflow (`internal/mcp/usage_test.go`, httptest stub API): `workflow_id=dev-loop-mctlhq-mctl-agents-663`, buckets `implementer` (count 2) and `investigator` (count 1) with tokens and `calculated_cost`; assert the stub received `group_by=devloop_stage&workflow_id=...`, both buckets are returned unchanged, and `total.count == 3`, `total.input_tokens` and `total.calculated_cost` equal the bucket sums exactly once (no double counting).
- [ ] T2. Cost separation: buckets carry `provider_reported_cost` only on one, `calculated_cost` on both, `invoice_reconciled_cost` on none; assert total has three distinct values, `invoice_reconciled_cost` absent (not 0), and no field equals the sum of different cost classes.
- [ ] T3. Nil-preserving totals: a field absent in all buckets is absent in `total`; a field present in only one bucket totals to that bucket's value.
- [ ] T4. Truncation: stub returns `truncated: true, truncated_by: "record_count"`; assert `total` is null, `total_unavailable_reason` is set, buckets and truncation metadata preserved.
- [ ] T5. Unconfigured ledger: stub returns 503 "usage ledger not configured"; assert the result is a tool error mentioning HTTP 503, not an empty/zero result. Same for 403 (non-admin).
- [ ] T6. Argument validation without calling the API: `issue` without `repository`, `issue=0`, `issue=1.5`, `limit=0`, `limit=1001`, `workflow_id` as a number; stub asserts it was never hit.
- [ ] T7. `group_by` handling: omitted -> `devloop_stage`; `stage` -> `devloop_stage`; `agent` forwarded as `agent`; all filter args forwarded under the HTTP names (`repository`, `issue`, `pr`, `run_id`, `since`, ...).
- [ ] T8. Pass-through of unknown keys: stub adds an extra top-level field; assert it survives in the tool result.
- [ ] T9. Regression: existing `internal/api/handlers_usage_test.go` passes untouched, confirming `/api/v1/usage/summary` default `group_by=agent` and semantics are unchanged.

## Rollback

The change is additive and stateless. Revert the PR (removes the tool, its
test entries and the allowlist entry) and redeploy mctl-api; the HTTP usage
endpoints and ledger data are unaffected. To hide the tool from portal users
without a redeploy, set its `enabled` to `false` in `docs/portal-allowlist.json`
and let the dispatch workflow re-vendor it into mctl-gitops.
