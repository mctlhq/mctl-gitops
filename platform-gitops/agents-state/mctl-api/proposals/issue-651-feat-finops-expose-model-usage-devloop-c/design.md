# Design: issue-651-feat-finops-expose-model-usage-devloop-c

## Current state

**Ledger and store** (`internal/usage/`):
- `types.go` defines `usage.Record`. It has nullable token counters (`*int64`) because,
  under ADR-012, absent is not zero. It has three separate cost fields
  (`ProviderReportedCost`, `CalculatedCost` + `PricingVersion`,
  `InvoiceReconciledCost`) and correlation fields: `TemporalWorkflowID`,
  `TemporalRunID`, `ExecutionID`, `Agent`, `DevLoopStage`, `TargetRepo`,
  `IssueNumber`, `PRNumber`, `WorkItemID`.
- In `store.go`, `Store.Summary(ctx, Filter, GroupBy) (*SummaryResult, error)` runs one
  `SELECT <col>, COUNT(*), SUM(...)... GROUP BY <col> ORDER BY COUNT(*) DESC, key ASC
  LIMIT limit+1`. It returns `[]*Bucket` (`key`, `count`, six nullable token sums, three
  nullable cost sums) plus `truncated`, `truncated_by` (`"record_count"`) and `limit`.
  `GroupBy` is a closed set: `agent`, `devloop_stage`, `canonical_model`, `provider`,
  `target_repo`, `temporal_workflow_id`, `work_item_id`, `execution_id`, `outcome`.
  `clampLimit` uses `DefaultQueryLimit = 200` and `MaxQueryLimit = 1000`.
- The correlation columns are `TEXT NOT NULL DEFAULT ''` (for example `devloop_stage`).
  Every record therefore falls in exactly one bucket, and rows without a stage collect
  under key `""`. Summing the buckets of a complete (untruncated) result gives the
  total over the matching records with no double counting. Cost columns are `NUMERIC`
  and decode into `*float64`.

**HTTP surface** (`internal/api/handlers_usage.go`, routes in `internal/api/router.go`
around line 794):
- `GET /api/v1/usage/summary` is handled by `GetUsageSummary`. It calls
  `requireUsageAdmin` (503 `"usage ledger not configured"` when `opts.Usage == nil`,
  401 without a user, 403 `"usage ledger is admin-only"` for non-admins), then
  `usageFilterFromQuery`. Query names: `workflow_id`, `run_id`, `execution_id`,
  `work_item_id`, `repository`, `issue`, `pr`, `agent`, `stage`, `provider`, `model`,
  `outcome`, `since`/`until` (RFC3339), `limit` (1..`usage.MaxQueryLimit`, otherwise
  400). `issue`/`pr` without `repository` is a 400. `group_by` defaults to `agent`, and
  an unknown value is a 400. The response is
  `summaryUsageResponse{GroupBy, *usage.SummaryResult}`.
- The comment on the handler says costs are deliberately never summed into one number
  across classes.
- `usageWriterGate` blocks the usage-writer principal from every read route. The MCP
  tool calls with the operator's own token, so the gate does not affect it.
- Tests: `internal/api/handlers_usage_test.go` (`TestUsageHandlers_NilStoreIs503NotEmpty`,
  `TestUsageHandlers_SummaryAnswersOperatorQuestion`, ...).

**MCP surface** (`internal/mcp/`):
- Tools are registered in `Server.NewMCPServer` in `server.go` (lifecycle block around
  line 290, commerce block around line 312). No usage tool exists.
- Thin read tools follow the pattern in `commerce.go`. The tool sets
  `WithReadOnlyHintAnnotation(true)` and `WithDestructiveHintAnnotation(false)`, uses
  `strictStringArg` (a present non-string filter is refused rather than widening the
  result), checks a bounded integer `limit`, builds `url.Values`, and calls
  `s.workItemCall(ctx, GET, path, nil, what)` in `workitems.go`. That helper forwards
  `s.effectiveToken(ctx)`, returns the body text on <400, and returns
  `"Failed to <what> (HTTP n): body"` as a tool error otherwise.
- Guard tests: `annotations_test.go` (`recordedHints` must match the registered tool
  count; `TestReadOnlyToolsAreTheRecordedSet` lists the read-only names; precedent for
  ledger reads is `idempotent: false`), `portal_allowlist_test.go` (every registered
  tool needs an explicit entry with a reason of at least 40 characters in
  `docs/portal-allowlist.json`; the commerce reads are `enabled: false`).
- Docs: `docs/model-usage-ledger.md` documents the HTTP filters, truncation semantics
  and the three cost classes.

**Deployed state checked:**
- `mctl_get_service_config(team=admins, service=mctl-api)`: error, "service not found:
  admins/mctl-api". mctl-api is not a catalogue service under `admins`.
- `mctl_list_services(team=admins)`: complete=true, 6 services (mctl-agents-worker*,
  mctl-design, mctl-docs, mctl-web). No mctl-api row.
- `$MCTL_GITOPS_ROOT/services/*/mctl-api*`: no such path. A grep of `services/` and
  `tenants/` for `USAGE_DB_URL` found nothing.
- Conclusion: I could not observe where mctl-api is deployed or whether `USAGE_DB_URL`
  is set in production. `cmd/api/main.go` (around line 460) builds the store only when
  `USAGE_DB_URL`/`AUDIT_DB_URL` is set. This change does not depend on that: when the
  store is missing, the API answers 503 and the tool turns that into an explicit error.
  The gap is recorded under Open questions in requirements.md.
- I did not query the live ledger contents for `dev-loop-mctlhq-mctl-agents-663`. No
  read path was available in this run.

## Proposed solution

Add one file, `internal/mcp/usage.go`, with `func (s *Server) toolGetUsageSummary()
(mcplib.Tool, server.ToolHandlerFunc)`, and register it in `NewMCPServer` next to the
lifecycle/agent reads (`srv.AddTool(s.toolGetUsageSummary())`).

**Tool definition**
- Name `mctl_get_usage_summary`. Title "Model usage / cost summary".
  `WithReadOnlyHintAnnotation(true)`, `WithDestructiveHintAnnotation(false)`, and
  `idempotent: false` in `recordedHints`, following the ledger-read precedent: the
  ledger grows, so repeated calls can differ.
- String arguments: `workflow_id`, `run_id`, `execution_id`, `work_item_id`,
  `repository`, `issue`, `pr`, `agent`, `stage`, `provider`, `model`, `outcome`,
  `since`, `until`, `group_by`. Number argument: `limit`.
- The description says:
  - it is admin-only and reads the ledger only (no logs);
  - `calculated_cost` is a list-price estimate tagged by `pricing_version`, not
    provider-billed and not invoice spend;
  - the three cost classes are never added together;
  - a 503 means the ledger is unavailable or unknown, never zero spend;
  - bucket ordering and truncation are by record count;
  - totals are withheld when truncated;
  - only instrumented producers appear in the ledger.

**Argument handling** (all before any network call)
- Read each string filter with `strictStringArg` and trim it. A non-empty value goes to
  `url.Values` under the identical HTTP name.
- Client-side checks mirror `usageFilterFromQuery`, so the caller gets a clear tool
  error instead of a relayed 400:
  - `issue`/`pr` must be positive integers, and need `repository`;
  - `since`/`until` must parse as `time.RFC3339`;
  - `limit` must be an integer in `1..usage.MaxQueryLimit`. Import the constant from
    `internal/usage` so the bound cannot drift, as the handler already does.
- `group_by`: empty becomes `devloop_stage`. The alias `stage` becomes
  `devloop_stage`. Anything else is lowercased and forwarded. Validity stays with the
  API's `ParseGroupBy`; the tool does not keep a second copy of the set.

**Fetch**
- Make one `GET /api/v1/usage/summary?<query>` with the caller's token. I factor a
  small helper out of `workItemCall` that returns `(status int, body []byte, err
  error)`, for example `s.apiGetJSON(ctx, path)`. `workItemCall` is then rebuilt on top
  of it with identical behaviour, and the usage tool can decode the success body.
- Any status >= 400 becomes `mcplib.NewToolResultError("Failed to read usage summary
  (HTTP <n>): <body>")`. This covers 503 (not configured), 401/403 (not admin) and 400
  (bad filter). No empty result is ever synthesised.

**Response** (JSON text). The API body is decoded into a local struct that embeds
`usage.SummaryResult` and `GroupBy`, using the same types as the handler, so fields
cannot drift. The tool then emits:

```json
{
  "group_by": "devloop_stage",
  "query": { "workflow_id": "dev-loop-mctlhq-mctl-agents-663", "...": "..." },
  "buckets": [ { "key": "implementer", "count": 3, "input_tokens": 0, "calculated_cost": 0.0, "...": "..." },
               { "key": "investigator", "...": "..." } ],
  "truncated": false, "truncated_by": "", "limit": 200,
  "total_status": "complete_buckets_summed",
  "total": {
    "count": 4,
    "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0,
    "reasoning_tokens": null, "web_search_requests": 0,
    "provider_reported_cost": null, "calculated_cost": 0.0, "invoice_reconciled_cost": null,
    "missing_in_buckets": { "provider_reported_cost": ["implementer", "investigator"] }
  },
  "cost_semantics": "provider_reported_cost, calculated_cost and invoice_reconciled_cost are separate and never summed together. calculated_cost is a list-price estimate (pricing_version-tagged), not provider-billed or invoice spend.",
  "coverage_note": "Only model calls emitted by instrumented producers are in the ledger; bucket key \"\" collects rows with no value for the grouped dimension."
}
```

- The total is computed by a pure function `sumUsageBuckets([]*usage.Bucket)
  usageTotal`. Per field: if every bucket is nil, the result is nil. Otherwise it is
  the sum of the non-nil values, and the keys of the nil buckets go into
  `missing_in_buckets[field]`.
- Costs are summed as float64 and then rounded to 9 decimal places. This removes float
  artefacts; it is not re-pricing.
- `count` is the sum of `bucket.Count`.
- When `truncated=true`, `total` is `null` and `total_status` is
  `"withheld_truncated"`, with `truncated_by` passed through. When there are zero
  buckets and `truncated=false`, `total_status` is `"no_matching_records"` and
  `total.count` is 0 with all cost fields null. That reads as "the ledger holds no rows
  for this filter", not as "zero spend". Because the store was reachable (HTTP 200),
  the case stays distinct from "unknown".
- No field combines cost classes. No field name contains "billed", "charge", "invoice"
  (except the stored `invoice_reconciled_cost`) or "spend" for the calculated value.

**Authorization**: none in the MCP layer. The tool forwards the caller's token, so
`requireUsageAdmin` decides, exactly as it does for the HTTP route. The tool is
admin-only because the API is.

**Portal allowlist**: add an entry to `docs/portal-allowlist.json` with
`"enabled": false`. Reason: aggregate spend per repository/agent is commercially
sensitive and admin-only; enabling it on the shared portal is a separate owner
decision. This follows the commerce-read precedent. Add the name to
`TestReadOnlyToolsAreTheRecordedSet`.

**Docs**: add a "MCP: `mctl_get_usage_summary`" section to `docs/model-usage-ledger.md`
covering the default group_by, the total rules and the withheld-on-truncation rule. Add
a CHANGELOG entry.

**HTTP unchanged**: no edits to `handlers_usage.go`, `router.go` or `internal/usage`.

## Alternatives

1. **Add a `totals` field to `usage.SummaryResult`, computed in SQL** (`SUM` over the
   full filter, not the clipped buckets). The DB would compute exact NUMERIC totals,
   and a total would exist even when buckets are truncated. Dropped for now: it changes
   the HTTP response shape and store query, against the acceptance criterion that
   `/api/v1/usage/summary` semantics stay unchanged, and adds a second aggregate query
   per call. It is the better long-term answer if truncated totals become needed, so it
   is a good follow-up.
2. **Call `usage.Store` directly from the MCP server.** Dropped: the MCP server is an
   HTTP client of mctl-api (`apiURL`, `effectiveToken`). Giving it a DB handle would
   create a second authorization path and break the "authorization matches the HTTP
   route" criterion.
3. **Leave the sum to the client and only relay the API body**
   (`workItemCall` passthrough). This is the smallest change. Dropped because the
   issue's main use case is a single reported total, and clients summing a truncated
   list by hand is the failure the issue warns about. A total that the server withholds
   on truncation is safer than one left to the client.

## Platform impact

- **Migrations**: none. No schema, store or HTTP change.
- **Backward compatibility**: purely additive. The registered tool count grows by one,
  and `recordedHints`, the read-only list and the portal allowlist are all updated in
  the same change. mctl-gitops vendors `docs/portal-allowlist.json` byte-identical
  through `.github/workflows/portal-allowlist-dispatch.yml`, so the new disabled entry
  reaches gitops automatically. It is disabled, so the portal surface does not change.
- **Resource impact**: one bounded Postgres aggregate per call (at most 1000 + 1 rows),
  the same cost as the existing HTTP route. It is subject to the same rate-limit group.
- **Risks and mitigations**:
  - *A total misread as invoice spend.* Mitigated by keeping three separate totals, the
    `cost_semantics` note, and the tool description wording; the tests check field
    names.
  - *A total over truncated buckets understates spend.* Mitigated: the total is
    withheld on `truncated=true`, and this is tested.
  - *A partially measured bucket hides missing rows.* The tool flags only buckets that
    are null throughout. Within-bucket partial coverage is not visible without a store
    change; this is documented in the description and Open questions.
  - *An unconfigured ledger reads as zero.* Mitigated: a 503 becomes a tool error, and
    this is tested.
  - *Default group_by differs from HTTP (`agent`).* Mitigated: the response always
    states `group_by`.
  - *Float rounding.* Rounding to 1e-9 is far below cent precision and does not change
    any stored figure.
