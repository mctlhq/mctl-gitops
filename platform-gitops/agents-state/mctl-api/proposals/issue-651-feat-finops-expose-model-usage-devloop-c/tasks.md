# Tasks: issue-651-feat-finops-expose-model-usage-devloop-c

- [ ] 1. Factor a raw-response helper out of `workItemCall` in `internal/mcp/workitems.go`
  (for example `s.apiGetJSON(ctx, path) (status int, body []byte, err error)`), using
  the same token forwarding through `s.effectiveToken(ctx)` and the same `Accept`
  header, and rebuild `workItemCall` on top of it. — DoD: existing work-item and
  commerce tests pass unchanged, and error strings stay the same.
- [ ] 2. (depends on 1) Create `internal/mcp/usage.go` with `toolGetUsageSummary()`:
  arguments `workflow_id`, `run_id`, `execution_id`, `work_item_id`, `repository`,
  `issue`, `pr`, `agent`, `stage`, `provider`, `model`, `outcome`, `since`, `until`,
  `group_by` (string) and `limit` (number). Set `WithReadOnlyHintAnnotation(true)` and
  `WithDestructiveHintAnnotation(false)`. The description states the admin-only rule,
  the three distinct cost classes, that calculated cost is a list-price estimate and
  not billed or invoice spend, that 503 means unknown rather than zero, that
  truncation is by record count, and the producer-coverage caveat. — DoD: the tool
  compiles, and filter names map 1:1 to the HTTP query names in
  `usageFilterFromQuery`.
- [ ] 3. (depends on 2) Pre-flight validation in the handler: `strictStringArg` for
  every string; `issue`/`pr` must be positive integers and need `repository`;
  `since`/`until` must be RFC3339; `limit` must be an integer in
  `1..usage.MaxQueryLimit`. `group_by` defaults to `devloop_stage`, the alias `stage`
  maps to `devloop_stage`, and other values are lowercased and forwarded. — DoD:
  invalid input returns a tool error and sends no HTTP request.
- [ ] 4. (depends on 2) Implement a pure `sumUsageBuckets([]*usage.Bucket)`: per-field
  nil-preserving sums for count, the six token dimensions and the three cost classes
  (never combined); `missing_in_buckets` per field; costs rounded to 9 decimal
  places. — DoD: unit-tested in isolation (T2, T3).
- [ ] 5. (depends on 1, 3, 4) Handler body: one `GET /api/v1/usage/summary`. A status
  >= 400 becomes the tool error `Failed to read usage summary (HTTP n): body`. On
  success, decode into `usage.SummaryResult` plus `group_by` and emit `group_by`,
  `query`, `buckets`, `truncated`, `truncated_by`, `limit`, `total_status`
  (`complete_buckets_summed` | `withheld_truncated` | `no_matching_records`), `total`
  (null when truncated), `cost_semantics` and `coverage_note`. — DoD: the response
  matches the shape in design.md.
- [ ] 6. (depends on 2) Register `srv.AddTool(s.toolGetUsageSummary())` in
  `NewMCPServer` (`internal/mcp/server.go`, next to the lifecycle / agent-registry
  reads). — DoD: the tool appears in `ListTools()`.
- [ ] 7. (depends on 6) Update the guard tests and data: add
  `"mctl_get_usage_summary": {readOnly: true, destructive: false, idempotent: false}`
  to `recordedHints` and the name to `TestReadOnlyToolsAreTheRecordedSet` in
  `internal/mcp/annotations_test.go`; add a `docs/portal-allowlist.json` entry with
  `"enabled": false` and a reason of at least 40 characters (admin-only, commercially
  sensitive aggregate spend, enabling it is a separate owner decision). — DoD:
  `go test ./internal/mcp/...` passes, including the tool-count and allowlist tests.
- [ ] 8. Docs: add an MCP section to `docs/model-usage-ledger.md` (default group_by,
  total rules, withheld on truncation, error semantics) and a `CHANGELOG.md` entry.
  — DoD: the docs match the implemented behaviour.
- [ ] 9. Run `go fmt`, `go vet` and `golangci-lint`, and confirm there is no diff in
  `internal/api/handlers_usage.go`, `internal/api/router.go` or `internal/usage/`.
  — DoD: lint is clean, and the HTTP usage tests pass untouched.

## Tests

All in `internal/mcp/usage_test.go`, against an `httptest.Server` backend unless noted.

- [ ] T1. Shaped like #663: the backend returns a `devloop_stage` summary for
  `workflow_id=dev-loop-mctlhq-mctl-agents-663` with buckets `investigator` (count 1)
  and `implementer` (count 2, from two models). Each has token counts and
  `calculated_cost`, and `provider_reported_cost` / `invoice_reconciled_cost` are null.
  Assert:
  - the request path is `/api/v1/usage/summary`, with `workflow_id` and
    `group_by=devloop_stage`;
  - both stage buckets are passed through;
  - `total.count == 3`;
  - `total.calculated_cost` equals the exact sum of the two bucket costs (no double
    counting);
  - token totals equal the bucket sums;
  - `total.provider_reported_cost` and `total.invoice_reconciled_cost` are null, not 0;
  - `total_status == "complete_buckets_summed"`.
- [ ] T2. `sumUsageBuckets`: a field that is nil in all buckets stays nil; a field
  that is nil in some buckets sums the rest and lists the nil keys in
  `missing_in_buckets`; the empty-key `""` bucket is included in the total.
- [ ] T3. Rounding: buckets with 0.1 and 0.2 sum to 0.3 exactly after rounding.
- [ ] T4. Truncation: the backend returns `truncated: true, truncated_by:
  "record_count"`. Assert `total` is null, `total_status == "withheld_truncated"`, and
  `truncated_by` is passed through.
- [ ] T5. Unconfigured ledger: the backend answers 503 `usage ledger not configured`.
  Assert the result is a tool error containing "HTTP 503", with no `total`, no
  `buckets` and no zero values.
- [ ] T6. Authorization: a backend 403 `usage ledger is admin-only` becomes a tool
  error, and the request carried the caller's bearer token.
- [ ] T7. Default and alias: with `group_by` omitted, or `group_by=stage`, the request
  sends `group_by=devloop_stage`. `group_by=agent` is forwarded as `agent`.
- [ ] T8. Pre-flight refusals send no request: `issue` without `repository`; a
  non-integer `pr`; `since` that is not RFC3339; `limit` 0, 1.5 or 1001; a numeric
  value for a string filter such as `workflow_id`.
- [ ] T9. Field-name guard: the serialised response contains no key that combines cost
  classes (no `total_cost`, `cost`, `billed`, `charge` keys), and `cost_semantics`
  describes `calculated_cost` as an estimate.
- [ ] T10. End-to-end through the real handler (optional, if the test DB fixture
  `newTestUsageStore` is reachable from the mcp package; otherwise this goes as an
  e2e test under `e2e/`): ingest an investigator record and an implementer record
  sharing one `temporal_workflow_id`, call the tool against an `httptest.Server`
  wrapping `NewRouter`, and assert two stage buckets and a total equal to the
  per-record sum.
- [ ] T11. The existing `internal/api/handlers_usage_test.go` passes unchanged (HTTP
  semantics preserved).

## Rollback

The change is additive and stateless: one new MCP tool, one refactored helper, docs,
and one disabled allowlist entry. To roll back, revert the PR and release the previous
mctl-api image. Nothing needs migrating or cleaning up, and the HTTP usage routes and
ledger data are untouched. If only the tool misbehaves, the portal entry is already
`enabled: false`, so portal users never see it. Direct MCP clients stop seeing it once
the revert ships. If the `workItemCall` refactor (task 1) causes a regression, revert
that commit alone and inline the raw fetch in `usage.go` instead.
