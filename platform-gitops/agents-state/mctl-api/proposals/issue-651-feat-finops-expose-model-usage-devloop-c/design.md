# Design: issue-651-feat-finops-expose-model-usage-devloop-c

## Current state

**Ledger and store** (`internal/usage`):
- `internal/usage/types.go` `Record` carries correlation (`TemporalWorkflowID`, `TemporalRunID`, `ExecutionID`, `WorkItemID`, `Agent`, `DevLoopStage`, `TargetRepo`, `IssueNumber`, `PRNumber`), nullable usage counters (`*int64`) and three separate cost fields (`ProviderReportedCost`, `CalculatedCost` + `PricingVersion`, `InvoiceReconciledCost`). The constants `CostProviderReported`, `CostCalculated` and `CostInvoiceReconciled` name the classes.
- `internal/usage/store.go`: the `model_usage_records` table stores cost as `NUMERIC` and tokens as nullable `BIGINT`. `agent`, `devloop_stage` and `target_repo` are `TEXT NOT NULL DEFAULT ''`. `Store.Summary(ctx, Filter, GroupBy)` runs `SELECT <col>, COUNT(*), SUM(...)... GROUP BY <col> ORDER BY COUNT(*) DESC, key ASC LIMIT limit+1` and returns `SummaryResult{Buckets []*Bucket, Truncated, TruncatedBy:"record_count", Limit}`. `Bucket` keeps tokens as `*int64` and costs as `*float64`, so SUM over all-NULL stays null. `GroupBy` is a closed set (`agent`, `devloop_stage`, `canonical_model`, `provider`, `target_repo`, `temporal_workflow_id`, `work_item_id`, `execution_id`, `outcome`), checked by `ParseGroupBy`. `DefaultQueryLimit=200` and `MaxQueryLimit=1000` are exported.
- Each `GroupBy` value is a single column (or the `COALESCE(canonical_model, model_key)` expression), so every row falls into exactly one bucket. The bucket sums of a complete, untruncated summary therefore add up to the total over the filter, with no double counting.

**HTTP surface** (`internal/api/handlers_usage.go`, routes in `internal/api/router.go` near `r.Get("/usage/summary", h.GetUsageSummary)`):
- `requireUsageAdmin` answers 503 `usage ledger not configured` when `opts.Usage == nil`, 401 without a user, and 403 `usage ledger is admin-only` for non-admins.
- `usageFilterFromQuery` maps the query parameters `workflow_id`, `run_id`, `execution_id`, `work_item_id`, `repository`, `agent`, `stage`, `provider`, `model`, `outcome`, `issue`, `pr`, `since`, `until` (RFC3339) and `limit` onto `usage.Filter`. It rejects unparseable values, `issue`/`pr` without `repository`, and `limit > usage.MaxQueryLimit`.
- `GetUsageSummary` defaults `group_by` to `agent`, returns 400 `unknown group_by`, and writes `summaryUsageResponse{GroupBy, *usage.SummaryResult}`. There is no grand total, on purpose (comment: "never summed into one number"). `docs/model-usage-ledger.md` documents this contract.

**MCP surface** (`internal/mcp`):
- Tools are registered in `NewMCPServer` in `internal/mcp/server.go` (lifecycle tools around `srv.AddTool(s.toolGetLifecycleOwnership())`, commerce reads under "Tenant-scoped commerce reads (mctl-api#569)"). No usage tool exists.
- Tools relay REST with the caller's token: `effectiveToken`, `apiGet`, and `apiGetStatus` in `server.go` (returns the status so a caller can tell 503 from other errors), and `workItemCall` in `internal/mcp/workitems.go`. `internal/mcp/commerce.go` is the closest model: read-only tools with `WithReadOnlyHintAnnotation(true)` / `WithDestructiveHintAnnotation(false)`, `strictStringArg` (refuses a non-string filter instead of widening the query), and integer `limit` validation over `float64` arguments.
- `internal/mcp/annotations_test.go`: `recordedHints` must list every tool with its hints. `server_test.go` checks `len(ListTools()) == len(recordedHints)`. `TestReadOnlyToolsAreTheRecordedSet` spells out the read-only set.
- `internal/mcp/portal_allowlist_test.go` with `docs/portal-allowlist.json`: every tool needs an explicit `enabled` and a reason of at least 40 characters. `mctl_get_commerce_budget` is `enabled: false` pending an owner decision. `mctl_get_lifecycle_ownership` is enabled by a dated owner decision.
- Test pattern: `internal/mcp/lifecycle_test.go` builds `NewServer(apiURL, "test-token")` against an `httptest` server and calls the handler directly.

**Deployed state checked:**
- `$MCTL_GITOPS_ROOT` (the `platform-gitops/` checkout, containing `bootstrap/`, `agents-state/`, `argocd/`, `infra-components/`, ...): mctl-api is not a tenant service under `services/`. The tenants there are `admins/`, `karabu/` and `labs/`, with services such as `mctl-agents-worker` and `mctl-web`. mctl-api is deployed as a platform bootstrap app instead (next item).
- `/workdir/mctl-gitops/platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`: ArgoCD Application `admins-mctl-api`, project `platform`, destination namespace `mctl-api`. It sets `AUDIT_DB_URL` (shared CNPG `shared-pg-rw.platform-db.svc`, db `mctl-api`) and no separate `USAGE_DB_URL`, so by `cmd/api/main.go` (USAGE_DB_URL falls back to AUDIT_DB_URL) the usage store should be configured in production. It mounts `usagePricingConfigMap: mctl-api-usage-pricing` for `USAGE_PRICING_CATALOG`.
- `mctl_get_service_status(team=admins, service=mctl-api)`: ArgoCD app `admins-mctl-api` is Healthy / Synced. `service` was null (not a catalogue service), and no revision was reported.
- Not observed: whether the ledger currently holds rows for `dev-loop-mctlhq-mctl-agents-663`. No read-only tool here queries the ledger, which is the gap this issue fills. See Open questions in requirements.md.

## Proposed solution

Add one MCP tool in a new file, `internal/mcp/usage.go`: `func (s *Server) toolGetUsageSummary() (mcplib.Tool, server.ToolHandlerFunc)`. Register it in `NewMCPServer` under a comment `// Model usage ledger read (mctl-api#651).`.

### Tool definition
- Name `mctl_get_usage_summary`. Title annotation "Model usage summary". `WithReadOnlyHintAnnotation(true)`, `WithDestructiveHintAnnotation(false)`. Idempotent stays false, matching the other ledger reads in `recordedHints`.
- Description: what it answers (the DevLoop / agent / model / repo questions); that it reads the ADR-012 ledger through `/api/v1/usage/summary`; the three cost classes and that `calculated_cost` is a list-price estimate, not billed or invoice spend; that `total` exists only when the bucket list is complete; that a failure means spend is unknown, never zero; that the ledger covers only instrumented producers; admin-only.
- Arguments:
  - String: `workflow_id`, `run_id`, `execution_id`, `work_item_id`, `repository`, `agent`, `stage`, `provider`, `model`, `outcome`, `since`, `until` (RFC3339).
  - String `group_by`, with `mcplib.Enum` over the `usage.GroupBy` values plus `stage`. Default `devloop_stage`.
  - Number: `issue`, `pr`, `limit` (1..`usage.MaxQueryLimit`).

### Handler
1. Read every string filter with `strictStringArg` (wrong type gives a tool error), trim it, and set it on `url.Values` under the same key `usageFilterFromQuery` reads. Read `issue`, `pr` and `limit` as positive integers. The `limit` ceiling is `usage.MaxQueryLimit`, imported so the two cannot drift, the same reason the HTTP layer imports it. Reject `issue`/`pr` without `repository` locally, with the same message as the API.
2. Resolve `group_by`: empty becomes `devloop_stage`, and `stage` becomes `devloop_stage`. Otherwise `usage.ParseGroupBy`; unknown values give a tool error. Always send it explicitly. The HTTP default (`agent`) is never relied on, so it is never changed.
3. `body, status, err := s.apiGetStatus(ctx, "/api/v1/usage/summary?"+q.Encode())`.
   - On transport error: tool error "usage ledger read failed: spend is UNKNOWN, not zero: ...".
   - On status 503: tool error that names "ledger not configured or unavailable: spend is UNKNOWN, not zero".
   - On any other status >= 400: tool error `Failed to read usage summary (HTTP n): <body>`. This relays 400/401/403 from `requireUsageAdmin` / `usageFilterFromQuery` verbatim.
4. On 200, decode twice from the same bytes:
   - Into a pass-through struct: `GroupBy string`, `Buckets []json.RawMessage`, `Truncated bool`, `TruncatedBy string`, `Limit int`. Buckets are returned byte-for-byte as the API produced them, so a new `usage.Bucket` field reaches the client without an MCP change.
   - With `json.Decoder.UseNumber()` into a local `usageBucketSums` (`Count int64`, token fields `*int64`, cost fields `*json.Number`) for totalling only.
5. Build the total:
   - If `Truncated`: `total = {status:"withheld", reason:"bucket list truncated by <truncated_by> at limit <n>: buckets are ordered by record count, so the clipped tail may hold significant spend; narrow the filter or raise limit"}` with no figures.
   - Otherwise `status:"complete"`. `count` is the sum of counts. Each token dimension is summed as int64 and is null only if null in every bucket. Each cost dimension is summed with `math/big.Rat` over each `json.Number`'s decimal text, null only if null in every bucket, and emitted as a `json.Number` decimal string (trailing zeros trimmed). This keeps the ledger's NUMERIC guarantee (`docs/model-usage-ledger.md`, "Money is NUMERIC") instead of reintroducing float64 rounding in the MCP layer.
   - The three costs are never added together.
6. Return `mcplib.NewToolResultText` of a JSON envelope:

```json
{
  "source": "mctl-api /api/v1/usage/summary (ADR-012 model usage ledger)",
  "group_by": "devloop_stage",
  "filters": {"workflow_id": "dev-loop-mctlhq-mctl-agents-663"},
  "buckets": [ {"key":"implementer", "count":1, "calculated_cost":4.12, "...": "..."},
               {"key":"investigator", "count":1, "calculated_cost":2.87} ],
  "truncated": false, "truncated_by": "", "limit": 200,
  "total": {"status":"complete", "count":2, "input_tokens":..., "provider_reported_cost":null,
            "calculated_cost":"6.99", "invoice_reconciled_cost":null},
  "cost_semantics": {
    "provider_reported_cost": "Cost as reported by the model provider at call time; null when the provider reports none (e.g. subscription runs).",
    "calculated_cost": "List-price ESTIMATE derived from the pricing catalog (pricing_version per record). Not provider-billed and not invoice spend.",
    "invoice_reconciled_cost": "Cost reconciled against a provider invoice; null until reconciliation exists."
  },
  "coverage": "Only model invocations emitted into the usage ledger by instrumented producers are counted. A key of \"\" means records with no value for the grouped dimension. An empty result means no ledger rows matched, not that no model was called."
}
```

   In the total, cost values are emitted as JSON numbers produced from the exact decimal, written as `json.Number` so the encoder writes them unquoted. The quotes above are only illustrative.

### Authorization
No MCP-side role check. The caller's token goes to the API, and `requireUsageAdmin` stays the only gate. This gives the same 503/401/403 semantics as HTTP and avoids two admin checks drifting apart. The usage-writer principal is already blocked by `usageWriterGate` on every route except POST records.

### Registration, hints, allowlist and docs
- `internal/mcp/server.go`: `srv.AddTool(s.toolGetUsageSummary())`.
- `internal/mcp/annotations_test.go`: add `"mctl_get_usage_summary": {readOnly: true, destructive: false, idempotent: false}` to `recordedHints`, and add the name to the `want` list in `TestReadOnlyToolsAreTheRecordedSet` in sorted position. `server_test.go`'s count follows `recordedHints` automatically.
- `docs/portal-allowlist.json`: add an entry with `enabled: false` and a reason, for example: "Read-only aggregate of the model-usage ledger: token counts and provider-reported, calculated (list-price estimate) and invoice-reconciled cost per stage/agent/model/repo. Per-repository and per-agent spend is commercially sensitive; the API keeps it admin-only. Not enabled on the shared portal: that is a separate owner decision (mctl-api#651)."
- `docs/model-usage-ledger.md`: add a short "MCP: mctl_get_usage_summary" section (default grouping, total rule, failure semantics). `CHANGELOG.md`: add an entry.

## Alternatives

1. **Call `usage.Store.Summary` directly from the MCP server.** Dropped. The MCP `Server` is an HTTP client of mctl-api (`apiURL`, `effectiveToken`) and holds no store handles. Wiring the store in would duplicate `requireUsageAdmin` and the filter parsing in `usageFilterFromQuery`, creating a second place where admin checks and filter rules could drift. Relaying HTTP gives the identical semantics the issue requires.
2. **Add a server-side grand total (a second `SELECT ... WHERE` without `GROUP BY`) to `/api/v1/usage/summary`.** This would give a total even when buckets are truncated, and summed in NUMERIC. Dropped for this issue: it changes the HTTP response, and the issue requires existing summary semantics to stay unchanged. It is also not needed for the DevLoop use case, where a single workflow has a handful of stage buckets, far below `DefaultQueryLimit`. It remains a reasonable follow-up.
3. **Return only the raw API response and let the client sum it.** Dropped. Leaving the sum to the model invites exactly the mistakes the issue lists: totalling a truncated list, adding the three cost classes together, or treating nulls as zero. A total that is complete-or-withheld, computed exactly, is safer. The issue explicitly allows it.
4. **Default `group_by` to `agent`, like HTTP.** Dropped in favour of `devloop_stage`, because the named operator question is "by stage". Sending the parameter explicitly keeps the HTTP default untouched.

## Platform impact

- **Migrations:** none. No schema, store or HTTP change.
- **Backward compatibility:** additive, one new MCP tool. `/api/v1/usage/summary` is untouched. MCP clients see one more tool. The tool count in `server_test.go` follows `recordedHints`.
- **Portal:** `docs/portal-allowlist.json` gains an `enabled: false` entry. The allowlist dispatch workflow publishes it to mctl-gitops, which vendors it byte-identical. There is no visibility change on the shared portal until an owner flips it.
- **Resource impact:** one bounded Postgres aggregate per call (at most `MaxQueryLimit + 1` buckets), the same as an operator calling HTTP. It is not on the 20/min write group, consistent with the existing reads.
- **Risks and mitigations:**
  - *An estimate is read as billed spend.* Mitigation: `cost_semantics` in every response and in the tool description, and the three classes are never added together.
  - *A truncated total understates spend.* Mitigation: the total is withheld whenever `truncated=true`, and the reason names `truncated_by`.
  - *An unconfigured or unreachable ledger reads as zero.* Mitigation: 503 and transport errors are tool errors saying spend is UNKNOWN. An empty 200 says "no ledger rows matched" and repeats the coverage caveat.
  - *Float rounding in the total.* Mitigation: exact `big.Rat` decimal addition over `json.Number`.
  - *A filter is dropped silently on a type mismatch.* Mitigation: `strictStringArg` and integer validation produce errors.
  - *Partial producer coverage (mctl-agents#507).* Called out in `coverage`. Not solvable here.
