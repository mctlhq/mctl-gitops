# Design: issue-651-feat-finops-expose-model-usage-devloop-c

## Current state

Ledger and HTTP read surface (unchanged by this proposal):

- `internal/usage/types.go`: `Record` has correlation fields (`TemporalWorkflowID`, `TemporalRunID`, `ExecutionID`, `Agent`, `DevLoopStage`, `TargetRepo`, `IssueNumber`, `PRNumber`, `WorkItemID`), nullable token counters, and three separate nullable costs: `ProviderReportedCost`, `CalculatedCost` (which requires `PricingVersion`) and `InvoiceReconciledCost`. The package doc states the rule "absent is not zero".
- `internal/usage/store.go`:
  - `Filter` lists the filter fields.
  - `clampLimit` uses `DefaultQueryLimit` = 200 and `MaxQueryLimit` = 1000.
  - `GroupBy` is a closed set mapped to fixed columns in `groupColumns` (`agent`, `devloop_stage`, `canonical_model`, `provider`, `target_repo`, `temporal_workflow_id`, `work_item_id`, `execution_id`, `outcome`).
  - `Store.Summary` runs `SELECT <col>, COUNT(*), SUM(...)... GROUP BY <col> ORDER BY COUNT(*) DESC LIMIT limit+1` and sets `Truncated` / `TruncatedBy="record_count"`.
  - `Bucket` keeps nullable sums. Its comment says the three costs "are never summed into one number".
  - Costs are `NUMERIC` columns, scanned into `*float64`.
  - Each record lands in exactly one bucket, because the GROUP BY is on a single column. Summing buckets therefore never double counts a record, including a run that used two models (two records, one stage bucket).
- `internal/api/handlers_usage.go`:
  - `requireUsageAdmin` returns 503 `usage ledger not configured` when `opts.Usage == nil`, 401 without a user, and 403 `usage ledger is admin-only` unless `user.IsAdmin()`.
  - `usageFilterFromQuery` maps the query parameters `workflow_id`, `run_id`, `execution_id`, `work_item_id`, `repository`, `issue`, `pr`, `agent`, `stage`, `provider`, `model`, `outcome`, `since` / `until` (RFC3339) and `limit` (1..1000, otherwise 400). It returns 400 when `issue` or `pr` is given without `repository`.
  - `GetUsageSummary` defaults `group_by` to `agent` and returns `summaryUsageResponse{group_by, buckets, truncated, truncated_by, limit}`. The response has no grand total.
- `internal/api/router.go` (around lines 783-796) registers `GET /usage/summary` in the authenticated group. `usageWriterGate` confines the usage-writer principal to `POST /usage/records`.
- `cmd/api/main.go` (around lines 460-480) builds the store only when `USAGE_DB_URL` or `AUDIT_DB_URL` is set. Otherwise the store is nil and the endpoint answers 503.
- `docs/model-usage-ledger.md` documents the summary semantics: truncation by record count, and costs never summed together.

MCP surface:

- `internal/mcp/server.go` `NewMCPServer` registers tools with `srv.AddTool(s.toolX())`. Admin reads such as `toolListAgentExecutions` (around line 3270) relay to the API with the caller's token through `s.apiGet`. The API, not the MCP layer, enforces admin.
- `s.apiGetStatus` (server.go, around line 2378) returns the body and the status code, so a caller can tell 503 (unknown) apart from other failures. The lifecycle tools use it.
- `internal/mcp/commerce.go` has `strictStringArg`, which refuses a non-string filter instead of widening the result, and the integer-limit validation pattern.
- `internal/mcp/annotations_test.go` `recordedHints` holds every tool's hints. `TestReadOnlyToolsAreTheRecordedSet` pins the read-only list.
- `internal/mcp/server_test.go` `TestNewMCPServer_ToolCount` checks that the registered tool count equals `len(recordedHints)`.
- `docs/portal-allowlist.json` needs an explicit `enabled` and `reason` for every tool. `internal/mcp/portal_allowlist_test.go` enforces that, including the `minReasonLen` floor on the tool-specific part of the reason. The commerce reads, for example, are `enabled: false` pending an owner decision.
- `internal/openapi/openapi.yaml` has no usage routes. Nothing in this proposal touches it.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/`: only `admins`, `karabu` and `labs` are present. There is no `services/*/mctl-api/values.yaml`, so mctl-api's deployed env (`USAGE_DB_URL`, `AUDIT_DB_URL`, `USAGE_PRICING_CATALOG`) could not be observed from this checkout. mctl-api is apparently deployed from outside the tenant `services/` tree.
- `mctl_get_service_config(team=admins, service=mctl-api)` returned `service not found: admins/mctl-api`. That is not a catalogue service, so it is not evidence about the ledger configuration.
- Result: this run did not observe whether the production ledger is configured. That is recorded under Open questions. The design does not depend on it, because an unconfigured ledger is handled as an explicit "unknown" error.

## Proposed solution

Add one file, `internal/mcp/usage.go`, with `func (s *Server) toolGetUsageSummary() (mcplib.Tool, server.ToolHandlerFunc)`. Register it in `NewMCPServer` next to the commerce reads, under the comment `// Model-usage ledger reads (mctl-api#651, ADR-012).`

Tool definition:

- Name `mctl_get_usage_summary`, title "Model usage summary". Annotations: `WithReadOnlyHintAnnotation(true)`, `WithDestructiveHintAnnotation(false)`, `WithIdempotentHintAnnotation(false)`, matching the `recordedHints` set used for the other admin reads.
- The description states:
  - it relays the durable ledger (`GET /api/v1/usage/summary`) and is admin-only;
  - the default grouping is `devloop_stage`;
  - the three costs are distinct, and `calculated_cost` is a list-price estimate that is neither billed nor invoiced;
  - `total` appears only when `truncated` is false;
  - a 503 means UNKNOWN, never zero;
  - a missing stage bucket means no rows were recorded for that stage. Producer coverage is incomplete (mctl-agents#507).
- String args: `workflow_id`, `run_id`, `execution_id`, `work_item_id`, `repository`, `agent`, `stage`, `provider`, `model`, `outcome`, `since`, `until`. Each one is read with `strictStringArg`, trimmed, and set only when non-empty. The names are identical to the HTTP query parameters, so the mapping is the identity.
- Number args: `issue`, `pr` and `limit`. Each must be an integer of at least 1, and `limit` must also be at most `usage.MaxQueryLimit`. Anything else is a tool error, and nothing is silently dropped. They are formatted with `strconv.FormatInt`. The `issue`/`pr`-requires-`repository` rule is left to the API, the single source, and its 400 is relayed. The tool may pre-check it too, with the same message.
- `group_by`: a string with `mcplib.Enum(...)` over the nine `usage.GroupBy` values plus the aliases `stage` and `model`. The handler normalises the aliases and validates with `usage.ParseGroupBy`. It always sends `group_by` explicitly and defaults to `string(usage.GroupByStage)`, so the HTTP default is never involved.

Handler flow:

1. Build `url.Values` and call `s.apiGetStatus(ctx, "/api/v1/usage/summary?"+q.Encode())`. The request carries the caller's own token, so `requireUsageAdmin` stays the only authorization check.
2. Status handling:
   - 503: `NewToolResultError("usage ledger unavailable: spend is UNKNOWN, not zero: <api message>")`.
   - Any other status of 400 or above: `NewToolResultError("Failed to get usage summary (HTTP %d): %s")`.
   - A transport error: a tool error. There is never an empty success.
3. Decode the body into a local struct that mirrors the API response: `group_by`, `truncated`, `truncated_by`, `limit`, and `buckets` as `[]map[string]json.RawMessage`. Every field the API returns is kept and re-emitted unchanged. The decoder uses `UseNumber`, so cost values keep their decimal text. Mirroring locally, instead of importing `api.summaryUsageResponse`, keeps the MCP package off `internal/api`. `internal/usage` is imported only for the `GroupBy` constants, `ParseGroupBy` and `MaxQueryLimit`.
4. Build the output object `{group_by, buckets, truncated, truncated_by, limit, total?, total_unavailable_reason?, cost_semantics, note?}`:
   - `buckets` are passed through verbatim.
   - When `truncated == false`, `total` is computed with a helper `sumUsageBuckets`:
     - `count` is the sum of the bucket counts.
     - Each token field (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens`, `web_search_requests`) is summed as int64 over the buckets where it is present. It is null when no bucket has it.
     - Each cost field (`provider_reported_cost`, `calculated_cost`, `invoice_reconciled_cost`) is summed separately with `math/big.Rat` over its decimal text, and emitted as a JSON number. It is null when no bucket has it. The three are never added together.
   - When `truncated == true`, `total` is left out and `total_unavailable_reason` reads: "bucket list truncated by record_count at limit N; a sum of the returned buckets would understate usage. Narrow the filter or raise limit."
   - When the bucket list is empty, `total` is `{count: 0}` with all other fields null, and `note` reads: "no ledger records matched this filter; this is not evidence of zero spend for uninstrumented producers".
   - `cost_semantics` is a static map:
     - `provider_reported_cost`: "cost reported by the model provider on the invocation";
     - `calculated_cost`: "list-price estimate computed by mctl-api from the pricing catalog (pricing_version per record); not provider-billed and not invoice spend";
     - `invoice_reconciled_cost`: "spend reconciled against a provider invoice; null until reconciliation exists".
5. Return the result as `NewToolResultText` with the JSON-marshalled output.

For the #663 operator query, `mctl_get_usage_summary(workflow_id="dev-loop-mctlhq-mctl-agents-663")` returns buckets keyed `investigator`, `implementer` and (if recorded) `shepherd`, plus `total`. The assistant can render the table from the issue without any arithmetic.

Supporting changes:

- `internal/mcp/annotations_test.go`: add `"mctl_get_usage_summary": {readOnly: true, destructive: false, idempotent: false}` to `recordedHints`, and add the name to the `want` list in `TestReadOnlyToolsAreTheRecordedSet`. The tool-count test then passes because it is derived from `recordedHints`.
- `docs/portal-allowlist.json`: add an entry with `"enabled": false` and a reason such as: "Admin-only aggregate of the model-usage ledger: token and cost sums per stage/agent/model/repo for DevLoop workflows; exposes internal workflow ids, repo/issue/PR numbers and estimated spend, no prompt or completion text. Not enabled on the shared portal pending an owner decision (mctl-api#651)." The reviewer may flip this (see Open questions). mctl-gitops vendors this file byte-identical, so a follow-up sync there may be needed. The comment in `portal_allowlist_test.go` says the same.
- `docs/model-usage-ledger.md`: add a short "MCP" subsection naming the tool, its default grouping, and the total/truncation rule.

## Alternatives

1. **Do the aggregation in the MCP layer by calling `GET /usage/records` and summing rows.** Dropped. It recomputes what `Store.Summary` already does in SQL. It is capped at 1000 rows, so it needs pagination. And it is a second aggregation path whose semantics could drift from the HTTP summary, which the issue rules out.
2. **Add a `total` row to the HTTP `/api/v1/usage/summary` response (in `Store.Summary` or `GetUsageSummary`).** This would also serve HTTP clients. It is dropped for now because the issue requires the existing `/usage/summary` semantics to stay unchanged, and the store comment deliberately leaves totals out. Summing complete buckets at the MCP edge, guarded by `truncated`, is the minimal change the issue explicitly allows. This can be revisited as a separate API change.
3. **Call `usage.Store.Summary` directly from the MCP server instead of over HTTP.** Dropped. The MCP `Server` has no store handle, and every other tool goes through the API with the caller's token. Going direct would mean re-implementing `requireUsageAdmin`, which breaks the requirement that admin authorization match the HTTP endpoint exactly.
4. **Default `group_by=agent` to match HTTP.** Not chosen, because the issue's main query is per-stage. The tool always sends the value explicitly, so the HTTP default is untouched either way.

## Platform impact

- **Migrations:** none. No schema, store or HTTP change.
- **Backward compatibility:** the change is additive. MCP clients gain one tool. `/api/v1/usage/summary` is byte-identical, and the existing `handlers_usage_test.go` tests stay unmodified and keep passing.
- **Resource impact:** one bounded aggregate query per call (`LIMIT <= 1001`) on an indexed table, the same cost as the existing HTTP read. There is no new rate-limit group. Like the other usage reads, it sits in the authenticated group.
- **Security:** the API enforces admin-only access through the caller's token. The ledger record type has no field that can hold model content, so the output carries no prompt or completion text. The tool is read-only. The portal default of `enabled: false` keeps it off the shared surface until an owner decides.
- **Risks and mitigations:**
  - *Float rounding in the total:* costs are decoded as `json.Number` and summed with `big.Rat`. Float addition is never used.
  - *Total over a clipped list:* the total is left out whenever `truncated` is true, and the API's truncation metadata is relayed verbatim.
  - *Estimate read as a bill:* the static `cost_semantics` block and the tool description label `calculated_cost` as a list-price estimate.
  - *Unconfigured ledger read as zero:* a 503 becomes an explicit "UNKNOWN, not zero" tool error.
  - *Partial producer coverage read as a full issue cost:* the description and the empty-result note say the ledger reports only instrumented producers.
