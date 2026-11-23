# Tasks: issue-749-feat-usage-outcome-counts-and-latency-pe

- [ ] 1. Add the `Bucket` fields in `internal/usage/store.go`: `OutcomeSuccessCount`, `OutcomeErrorCount`, `OutcomeInterruptedCount`, `OutcomeUnreportedCount`, `DurationAPIMsReportedCount` (int64, no omitempty), and `DurationAPIMsP50`, `DurationAPIMsP95` (*int64, omitempty), with doc comments on why counts are plain and percentiles are nullable — DoD: compiles, JSON tags match requirements.md.
- [ ] 2. (depends on 1) Extend the `Store.Summary` SQL with the four `COUNT(*) FILTER (WHERE outcome ...)` aggregates (built from the `Outcome*` constants; unreported = `NOT IN` the three), `COUNT(duration_api_ms)`, and `percentile_disc(0.5|0.95) WITHIN GROUP (ORDER BY duration_api_ms)`, and scan them. Keep ORDER BY, LIMIT and truncation unchanged — DoD: `go vet`, `golangci-lint` clean; the existing store tests pass.
- [ ] 3. (depends on 2) In `internal/mcp/usage.go`, add `usageCountFields` and sum them in `sumUsageBuckets` (int64, null if no bucket reports them, with total_coverage). Exclude the percentiles from `total`, add a computed `percentile_semantics` key (protected from API override), and update the `mctl_get_usage_summary` description — DoD: existing `internal/mcp/usage_test.go` tests pass; tool count in `server_test.go` unchanged.
- [ ] 4. (depends on 2) Update `docs/model-usage-ledger.md` (summary and MCP sections): the new fields, unreported vs success, null percentile vs 0, non-aggregable percentiles, and the multi-model `duration_api_ms` grain caveat — DoD: the docs match the implementation.

## Tests
- [ ] T1. `internal/usage/store_test.go` (Postgres): ingest rows in one workflow with outcomes success x2, error x1, interrupted x1, empty x1, then `Summary(GroupByModel)`: the four counts are 2/1/1/1 and sum to `Count`.
- [ ] T2. Store: a bucket where every row has nil `DurationAPIMs` returns `DurationAPIMsP50 == nil`, `DurationAPIMsP95 == nil`, `DurationAPIMsReportedCount == 0`.
- [ ] T3. Store: durations {100, 200, 300, 400, nil} give `DurationAPIMsReportedCount == 4`, p50 == 200 and p95 == 400 (percentile_disc, NULL ignored, not treated as 0).
- [ ] T4. Store: two buckets (two models) get independent counts and percentiles; the `outcome` filter narrows the counts consistently with `count`.
- [ ] T5. `internal/api/handlers_usage_test.go`: the summary JSON contains `outcome_unreported_count: 0` explicitly (not omitted) and omits `duration_api_ms_p50` when no duration was reported.
- [ ] T6. `internal/mcp/usage_test.go`: `total` sums the outcome counts and `duration_api_ms_reported_count`; `total` has no percentile keys; `percentile_semantics` is present and cannot be overridden by an API key of the same name; a response from an older API without the new fields gives null totals for them, not 0.
- [ ] T7. MCP: a truncated response still has no `total` and keeps the bucket percentile fields untouched.

## Rollback
The change is additive and read-only (no schema change, no data written).
Revert the PR and redeploy the previous mctl-api image. Clients that started
reading the new fields lose them, but no stored data is affected.
