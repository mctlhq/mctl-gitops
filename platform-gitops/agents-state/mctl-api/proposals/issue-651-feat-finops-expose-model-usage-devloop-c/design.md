# Design: issue-651-feat-finops-expose-model-usage-devloop-c

## Current state

Ledger and HTTP surface (mctl-api#266, ADR-012):

- `internal/usage/types.go` — `usage.Record` with nullable token counters
  (`InputTokens`, `OutputTokens`, `CacheReadTokens`, `CacheWriteTokens`,
  `ReasoningTokens`, `WebSearchRequests`) and three separate cost fields
  (`ProviderReportedCost`, `CalculatedCost` + `PricingVersion`,
  `InvoiceReconciledCost`). Correlation fields include `TemporalWorkflowID`,
  `TemporalRunID`, `ExecutionID`, `Agent`, `DevLoopStage`, `TargetRepo`,
  `IssueNumber`, `PRNumber`, `WorkItemID`.
- `internal/usage/store.go`
  - `DefaultQueryLimit = 200`, `MaxQueryLimit = 1000`, `clampLimit`.
  - `GroupBy` closed set: `agent`, `devloop_stage`, `canonical_model`,
    `provider`, `target_repo`, `temporal_workflow_id`, `work_item_id`,
    `execution_id`, `outcome`; `ParseGroupBy` maps request strings to fixed
    SQL columns via `groupColumns`. Grouping columns such as `agent` and
    `devloop_stage` are `TEXT NOT NULL DEFAULT ''`, so unattributed rows land in
    a bucket with key `""`.
  - `Bucket` — `Key`, `Count`, nullable token sums and the three cost sums,
    kept apart on purpose ("never summed into one number").
  - `SummaryResult` — `Buckets`, `Truncated`, `TruncatedBy` (`record_count`),
    `Limit`. `Store.Summary` fetches `limit+1` rows ordered by `COUNT(*) DESC`
    to detect truncation. There is no grand total.
- `internal/api/handlers_usage.go`
  - `requireUsageAdmin`: nil store -> 503 "usage ledger not configured"
    (explicitly never an empty result), no user -> 401, non-admin -> 403.
  - `usageFilterFromQuery`: query params `workflow_id`, `run_id`,
    `execution_id`, `work_item_id`, `repository`, `agent`, `stage`, `provider`,
    `model`, `outcome`, `issue`, `pr` (integers; require `repository`),
    `since`/`until` (RFC3339), `limit` (1..`usage.MaxQueryLimit`, larger is 400).
  - `GetUsageSummary`: default `group_by=agent`; responds
    `summaryUsageResponse{GroupBy, *usage.SummaryResult}`.
- `internal/api/router.go` lines ~783-796 register `/usage/records` and
  `/usage/summary` in the authenticated API group. `usageWriterGate` confines
  the usage-writer principal to POST records only.
- `cmd/api/main.go` ~lines 459-495: the store is built only when
  `USAGE_DB_URL` or `AUDIT_DB_URL` is set; otherwise `Usage` is nil and the
  routes return 503.

MCP surface:

- `internal/mcp/server.go` `NewMCPServer` registers every tool with
  `srv.AddTool(...)`; admin tools such as `toolGetLifecycleOwnership`
  (`internal/mcp/lifecycle.go`) and `toolListAgentExecutions` are visible to all
  callers and rely on the API's own admin check on the caller's token.
- `internal/mcp/commerce.go` is the closest template: read-only tools with
  `WithReadOnlyHintAnnotation(true)` / `WithDestructiveHintAnnotation(false)`,
  argument validation via `strictStringArg` (refuses a non-string value so a
  mistyped filter cannot widen the result), integer `limit` validation, and
  relay through `s.workItemCall` (`internal/mcp/workitems.go`), which sends the
  caller's token (`s.effectiveToken`) to `s.apiURL+path` and turns any HTTP
  status >= 400 into `NewToolResultError("Failed to ... (HTTP n): body")`.
- `internal/mcp/annotations_test.go` — `recordedHints` holds every tool's hints;
  `TestReadOnlyToolsAreTheRecordedSet` pins the read-only list.
  `internal/mcp/server_test.go` `TestNewMCPServer_ToolCount` asserts the
  registered count equals `len(recordedHints)`.
- `docs/portal-allowlist.json` + `internal/mcp/portal_allowlist_test.go`
  (`TestPortalAllowlist_CoversEveryRegisteredTool`): every registered tool needs
  an explicit `enabled` decision and a reason of >= 40 tool-specific characters.
  The file is vendored byte-identical into mctl-gitops.
- `internal/mcp/commerce_test.go` shows the test pattern: an `httptest.Server`
  stub standing in for the API, asserting path/query and the relayed result.

Deployed state checked:

- `mctl_list_services(team=admins)`: lists mctl-agents-worker(-exec,-implement),
  mctl-design, mctl-docs, mctl-web. mctl-api is not a catalogue service in any
  tenant observed, so its deployed config is not visible through this tool.
- `$MCTL_GITOPS_ROOT/services/` (admins, karabu, labs): no `mctl-api/values.yaml`;
  `grep USAGE_|AUDIT_DB_URL` returned nothing. mctl-api is deployed outside the
  tenant services tree (its own `helm/` chart), which this run could not read
  in deployed form.
- Gap: whether production sets `USAGE_DB_URL`/`AUDIT_DB_URL` and
  `USAGE_PRICING_CATALOG` was NOT observed (recorded under Open questions in
  requirements.md). This is "could not observe", not "absent".

## Proposed solution

Add one MCP tool in a new file `internal/mcp/usage.go`:
`func (s *Server) toolGetUsageSummary() (mcplib.Tool, server.ToolHandlerFunc)`,
registered in `NewMCPServer` next to the agent-registry / DevLoop admin reads.

Tool definition:

- Name `mctl_get_usage_summary`, title "Model usage summary",
  `WithReadOnlyHintAnnotation(true)`, `WithDestructiveHintAnnotation(false)`,
  `WithIdempotentHintAnnotation(false)` (matching the other recorded reads).
- Arguments (all optional): strings `workflow_id`, `run_id`, `execution_id`,
  `work_item_id`, `repository`, `agent`, `stage`, `provider`, `model`,
  `outcome`, `since`, `until`, `group_by`; numbers `issue`, `pr`, `limit`.
- Description states: admin-only; backed by the usage ledger, not logs; default
  grouping is `devloop_stage` (HTTP default is `agent`); allowed `group_by`
  values (`stage` alias accepted); `workflow_id=dev-loop-...` returns one
  DevLoop by stage; the cost semantics below; a tool error from a 503 means the
  ledger is unavailable (unknown spend), never zero; a truncated result carries
  no total.

Handler:

1. Validate and build `url.Values`. String args via `strictStringArg`, trimmed,
   empty skipped, forwarded under the same names `usageFilterFromQuery` reads.
   `issue`, `pr`: must be float64 integral and > 0; require `repository`.
   `limit`: integral in 1..`usage.MaxQueryLimit` (import the constant so it
   cannot drift). `group_by`: default `devloop_stage`; `stage` -> `devloop_stage`;
   anything else forwarded so the API's `ParseGroupBy` stays authoritative.
   `since`/`until` are forwarded; the API rejects non-RFC3339 with 400.
2. Call the API: reuse the HTTP plumbing of `s.workItemCall` but obtain the raw
   body, so the handler can post-process. Implement a small helper
   `s.apiGetJSON(ctx, path, what) ([]byte, *mcplib.CallToolResult)` in
   `workitems.go` (or `usage.go`) that shares the request/token/error logic
   with `workItemCall` (refactor `workItemCall` to call it for GET so error
   text stays identical). Any status >= 400, including 503, returns the same
   `Failed to read usage summary (HTTP n): body` tool error.
3. Decode the 2xx body into a local struct that embeds the API type shape:
   `GroupBy string`, `Buckets []*usage.Bucket`, `Truncated bool`,
   `TruncatedBy string`, `Limit int` (reusing `usage.Bucket` keeps field names
   and nullability in lock-step with the store). Also decode into
   `map[string]json.RawMessage` and re-emit all original keys so any field the
   API adds later is not dropped.
4. If `!Truncated`, compute `total` with `sumBuckets(buckets) usage.Bucket`
   (Key = "total"): `Count` summed; for each `*int64` / `*float64` field,
   result stays nil until some bucket has a non-nil value, then accumulates.
   Each bucket is visited once; fields are never cross-added. If `Truncated`,
   `total` = null and `total_unavailable_reason` = "summary truncated by
   <truncated_by> at limit <n>; narrow the filter or raise limit (max 1000)
   before totalling".
5. Add `cost_semantics` (constant string): calculated_cost is a list-price
   estimate under pricing_version, not provider-billed or invoice spend;
   provider_reported_cost and invoice_reconciled_cost are separate
   classifications and are never summed with it; each cost sum covers only the
   records that carried that cost, so compare with `count`; a missing field
   means not reported, not zero; key "" is records with no value for the
   grouped dimension.
6. Return `mcplib.NewToolResultText(json)`.

Authorization: unchanged and in one place: the API's `requireUsageAdmin`
(admin-only) on the caller's own token. The MCP tool is not hidden by a tool
filter, matching `mctl_get_lifecycle_ownership` and other admin reads.

Bookkeeping:

- `internal/mcp/annotations_test.go`: add
  `"mctl_get_usage_summary": {readOnly: true, destructive: false, idempotent: false}`
  and add the name to `TestReadOnlyToolsAreTheRecordedSet`.
- `docs/portal-allowlist.json`: add an explicit entry (alphabetical position),
  `enabled: true`, reason describing the exposure (aggregate per-stage/agent/
  model/repository token and cost sums, admin-only via the API's admin check
  on the caller's token, no prompt content because the record type has no field
  for it, no credentials). Owner confirmation flagged in Open questions.
- `docs/model-usage-ledger.md`: add an "MCP: mctl_get_usage_summary" section.
- `CHANGELOG.md`: entry under the unreleased section.

Example result for the #663 shape (`workflow_id=dev-loop-mctlhq-mctl-agents-663`):

```json
{
  "group_by": "devloop_stage",
  "buckets": [
    {"key": "implementer", "count": 2, "input_tokens": ..., "calculated_cost": 4.1},
    {"key": "investigator", "count": 1, "input_tokens": ..., "calculated_cost": 2.3}
  ],
  "truncated": false,
  "limit": 200,
  "total": {"key": "total", "count": 3, "input_tokens": ..., "calculated_cost": 6.4},
  "cost_semantics": "..."
}
```

## Alternatives

1. Call `usage.Store.Summary` in-process from the MCP package. Dropped: the MCP
   server is built around relaying to the API with the caller's token
   (`NewServer(apiURL, ...)`, `workItemCall`); bypassing HTTP would duplicate
   `requireUsageAdmin` and `usageFilterFromQuery`, and authorization would then
   live in two places that can drift.
2. Add a `total` to the HTTP `/api/v1/usage/summary` response. Dropped for this
   issue: the acceptance criteria require existing HTTP semantics to be
   unchanged, and the handler comment documents that the API deliberately
   returns no combined number. Can be revisited as an additive change later.
3. Relay the raw API body unchanged and make the client sum. Dropped: the issue
   asks for a safe total where possible, and LLM clients summing nullable
   floats are error-prone; computing it server-side only on non-truncated
   results is deterministic and testable. The raw buckets remain present, so
   a client can still verify.

## Platform impact

- Migrations: none. No schema or store change.
- Backward compatibility: purely additive MCP tool; HTTP routes untouched. MCP
  tool count rises by one (tests updated in the same change). The portal
  allowlist is vendored into mctl-gitops by the existing dispatch workflow.
- Resource impact: one bounded Postgres GROUP BY per call (limit <= 1000),
  same as the existing HTTP endpoint; operator-driven and infrequent.
- Risks and mitigations:
  - Misreading an estimate as spend -> `cost_semantics` note, three cost fields
    never combined, description wording.
  - Totalling a partial result -> total withheld when `truncated`.
  - Reading an unconfigured ledger as zero -> 503 relayed as tool error.
  - Partial cost coverage inside a bucket (NULL ignored by SUM) -> documented
    in `cost_semantics`; structural fix left as an open question.
  - Commercially sensitive data on a shared portal -> API admin check remains
    the access control; owner confirms portal enablement.
