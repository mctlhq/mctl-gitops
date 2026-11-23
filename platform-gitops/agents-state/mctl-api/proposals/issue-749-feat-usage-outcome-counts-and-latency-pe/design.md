# Design: issue-749-feat-usage-outcome-counts-and-latency-pe

## Current state
- `internal/usage/types.go`: `Record` carries `Outcome string` (closed set:
  `OutcomeSuccess`, `OutcomeError`, `OutcomeInterrupted`, or empty, enforced
  in `Record.Validate`), `APIErrorStatus string` and `DurationAPIMs *int64`
  (nil = not reported). The package doc states the rule this change must keep:
  "Absent is not zero."
- `internal/usage/store.go`, `usageSchema`: `outcome TEXT NOT NULL DEFAULT ''`
  and `duration_api_ms BIGINT` (nullable) on `model_usage_records`. An empty
  `outcome` means the producer sent none.
- `internal/usage/store.go`, `Store.Summary`: one `GROUP BY <groupColumns[by]>`
  query that selects `COUNT(*)`, six `SUM(token)` and three `SUM(cost)`. It
  orders by `COUNT(*) DESC, key ASC` and uses `LIMIT limit+1` to detect
  truncation. The result is scanned into `Bucket` (nullable token/cost pointers,
  `omitempty`). `groupColumns` is a closed map, so no request data reaches the
  SQL. `GroupByOutcome` already exists as a dimension, but only on its own axis:
  it cannot give a success rate per model or per stage.
- `internal/api/handlers_usage.go`, `GetUsageSummary` /
  `summaryUsageResponse`: embeds `*usage.SummaryResult`, so any new `Bucket`
  field reaches the wire with no handler change.
- `internal/mcp/usage.go`, `toolGetUsageSummary` / `buildUsageSummary` /
  `sumUsageBuckets`: re-emits each bucket unchanged and computes `total` (when
  not truncated) by summing `count`, `usageTokenFields` (int64) and
  `usageCostFields` (big.Rat). `total_coverage` covers fields reported by only
  some buckets. Unknown bucket keys pass through but are not totalled.
- Tests: `internal/usage/store_test.go` (Postgres-backed, skipped without
  `TEST_DATABASE_URL`; CI runs `postgres:16`, see
  `.github/workflows/validate.yml`), `internal/api/handlers_usage_test.go`,
  `internal/mcp/usage_test.go` (stubbed backend JSON).
- Docs: `docs/model-usage-ledger.md`, section
  "`GET /api/v1/usage/summary?group_by=agent`" and the "MCP" section.

Deployed state checked:
- `mctl_list_services(team=admins)`: mctl-api is not a catalogue service in
  any tenant listed there (only mctl-agents-worker*, mctl-design, mctl-docs,
  mctl-support, mctl-web, umami). It is a platform component, so there is no
  `services/<tenant>/mctl-api/values.yaml`. The `$MCTL_GITOPS_ROOT/services/admins/`
  listing confirmed this. This change needs no deployment config.
- `mctl_get_usage_summary(group_by=outcome|canonical_model, since=2026-10-01)`:
  refused with HTTP 403 `agent_scope_denied`. Live ledger contents
  (outcome/duration coverage, number of models) could not be observed. This
  is a gap, not an absence.

## Proposed solution
1. **Store query** (`internal/usage/store.go`, `Store.Summary`). Extend the
   SELECT with these aggregates, computed over the same WHERE and GROUP BY:
   ```sql
   COUNT(*) FILTER (WHERE outcome = 'success'),
   COUNT(*) FILTER (WHERE outcome = 'error'),
   COUNT(*) FILTER (WHERE outcome = 'interrupted'),
   COUNT(*) FILTER (WHERE outcome NOT IN ('success','error','interrupted')),
   COUNT(duration_api_ms),
   percentile_disc(0.5)  WITHIN GROUP (ORDER BY duration_api_ms),
   percentile_disc(0.95) WITHIN GROUP (ORDER BY duration_api_ms)
   ```
   The literals are built from the `Outcome*` constants with `fmt.Sprintf`.
   They are fixed constants, never request data, so the "no request data as
   SQL" property holds. The "unreported" count uses `NOT IN` rather than
   `= ''`, so the four counts always add up to `COUNT(*)` even if a value
   outside the vocabulary were ever written directly to the database.
   `percentile_disc` ignores NULLs and returns NULL when no row in the group
   has a value, which gives "unknown, not zero" for free. It returns an
   observed BIGINT (no interpolation), so the type is `*int64`. The query
   keeps the same `ORDER BY` and `LIMIT`, so truncation semantics are
   unchanged.
2. **Bucket type** (`internal/usage/store.go`, `Bucket`). Add:
   - `OutcomeSuccessCount`, `OutcomeErrorCount`, `OutcomeInterruptedCount`,
     `OutcomeUnreportedCount int64`, JSON `outcome_*_count`, no `omitempty`
     (always present; 0 is measured).
   - `DurationAPIMsReportedCount int64` (`duration_api_ms_reported_count`,
     no `omitempty`): the sample size of the percentiles.
   - `DurationAPIMsP50`, `DurationAPIMsP95 *int64` (`duration_api_ms_p50`,
     `duration_api_ms_p95`, `omitempty`): absent means no row reported a
     duration, the same convention as the token and cost pointers.
   Scan them in `Summary`'s `rows.Scan`. A doc comment explains why counts are
   plain ints (COUNT is always known) and percentiles are pointers.
3. **HTTP**: no handler change. `summaryUsageResponse` embeds the result.
4. **MCP** (`internal/mcp/usage.go`):
   - Add `usageCountFields = ["outcome_success_count", "outcome_error_count",
     "outcome_interrupted_count", "outcome_unreported_count",
     "duration_api_ms_reported_count"]`. `sumUsageBuckets` sums them like the
     token fields: int64, null when no bucket reports them (an older API),
     with `total_coverage` when only some buckets report them.
   - Do not total `duration_api_ms_p50/p95`. Add a computed top-level
     `percentile_semantics` string ("duration_api_ms_p50/p95 are per bucket,
     computed over duration_api_ms_reported_count rows; they cannot be
     combined across buckets and are not in total"). Add it to the
     computed-key list so the API cannot override it.
   - Extend the tool description: buckets carry outcome counts (unreported is
     a row with no outcome, not a success) and p50/p95 of `duration_api_ms`
     (null = no row reported it, never 0).
5. **Docs** (`docs/model-usage-ledger.md`): document the new bucket fields,
   the unreported/absent rules, the non-aggregability of percentiles, and the
   multi-model `duration_api_ms` grain caveat.

Why this way: one query pass, no schema change. It follows the existing
nullable-aggregate convention, and the HTTP wire shape follows the type
automatically. Flat fields fit the existing flat bucket shape and the
`sumUsageBuckets` field-list design.

## Alternatives
- **Compute in Go from `List` records.** Dropped: `List` is capped at
  `MaxQueryLimit` rows, so percentiles would silently cover only a page.
  Postgres already aggregates exactly over the full filtered set.
- **`percentile_cont` (interpolated, double precision).** Dropped: it returns
  a non-observed fractional millisecond value, and the double type is
  inconsistent with the BIGINT column. `percentile_disc` is reproducible and
  exact for integer data.
- **Nested `outcomes: {success, error, ...}` map, or per-`api_error_status`
  counts.** Dropped for now: a nested map would need a separate summing path
  in `sumUsageBuckets`, and `api_error_status` has an open vocabulary (an
  unbounded key set per bucket). The 5xx breakdown belongs with the
  fallback profile the issue defers.
- **Add a second `group_by` (e.g. model x outcome).** Dropped: it multiplies
  bucket cardinality against the same `limit`, and it still would not give
  latency.

## Platform impact
- Migrations: none. Only existing columns are read.
- Backward compatibility: additive JSON fields only. Existing fields, ordering
  and truncation are unchanged. Old clients ignore the new keys. The MCP
  totalling treats a field missing from an older API response as null, not 0.
- Resource impact: ordered-set aggregates sort `duration_api_ms` per group. The
  query already scans every matching row for SUM, and the result is still
  bounded by `limit`. On an unfiltered high-cardinality group_by the extra sort
  is O(n log n) over the filtered rows. That is acceptable at current ledger
  size; there is no index change.
- Risks and mitigations:
  - A reader takes "unreported" as success. Mitigation: the field name says
    unreported, the docs and MCP description say so, and a test pins it.
  - A per-model p95 is inflated by run-level `duration_api_ms` copied onto
    multi-model rows. Mitigation: a documented caveat and an open question to
    mctl-agents.
  - Someone averages bucket percentiles. Mitigation: `total` omits them, and
    `percentile_semantics` says why.
