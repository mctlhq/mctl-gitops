# Tasks: issue-680-fix-mcp-usage-summary-follow-ups-from-67

- [ ] 1. In `internal/mcp/usage.go`, rename the local `max` to `upper` in the numeric-arg loop of `toolGetUsageSummary`.
  - DoD: no identifier shadows a builtin; `go vet` and `golangci-lint` are clean.
- [ ] 2. Lowercase `group_by` before the alias switch: `strings.ToLower(strings.TrimSpace(rawGB))`.
  - DoD: `Stage`, `MODEL` and `DevLoop_Stage` are sent as `devloop_stage` / `canonical_model` / `devloop_stage`.
- [ ] 3. Add `usageTruncationReason(truncatedBy, limit json.RawMessage) string` and use it in `buildUsageSummary`.
  - The axis is the decoded string, falling back to "an unknown axis".
  - The "at limit N" clause is left out when `limit` is absent, null or empty.
  - Change the tool description so it no longer hardcodes "clipped by record count".
  - DoD: the reason never contains `record_count` unless the API sent it, and never contains `at limit ;`.
- [ ] 4. Extend `sumUsageBuckets` to return per-field coverage for token and cost fields where `0 < reporting < len(buckets)`. (depends on nothing)
  - Emit it as `total_coverage` (omitempty), with the values `{"buckets_reporting": n, "of": m}`.
  - When it is non-empty, add the partial-coverage sentence to `note`.
  - Document `total_coverage` in the tool description.
  - DoD: `total.<field>` values are unchanged; mixed input yields a `total_coverage` entry.
- [ ] 5. Rewrite `buildUsageSummary` as a passthrough over `map[string]json.RawMessage`. (depends on 3, 4)
  - Re-emit every top-level API key unchanged.
  - Overwrite the computed keys (`buckets` normalisation, `truncated`, `total`, `total_unavailable_reason`, `total_coverage`, `cost_semantics`, `note`).
  - Drop a null `truncated_by`.
  - Remove `usageSummaryOut`, or keep it only as documentation of the computed keys.
  - DoD: all existing tests in `internal/mcp/usage_test.go` pass unchanged.
- [ ] 6. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run` and `go test ./internal/mcp/... ./internal/usage/...`. (depends on 1-5)
  - DoD: all green; the MCP tool count in `server_test.go` is unchanged.

## Tests
All tests go in `internal/mcp/usage_test.go`. Each one must fail with its fix reverted. Check this locally by reverting the corresponding hunk.

- [ ] T1. `TestUsageSummaryTotalsMixedCoverage` (item 2).
  - Fixture: `group_by=devloop_stage`, with two buckets. Only `investigator` carries `provider_reported_cost`. Both carry `calculated_cost`.
  - Assert that `total.provider_reported_cost` equals the investigator value.
  - Assert `total_coverage.provider_reported_cost == {"buckets_reporting":1,"of":2}`.
  - Assert that `calculated_cost` is absent from `total_coverage`.
  - Assert that `note` mentions `total_coverage`.
- [ ] T2. `TestUsageSummaryAliasCaseInsensitive` (item 3).
  - `group_by` values `Stage`, `MODEL` and `DevLoop_Stage` give backend queries `devloop_stage`, `canonical_model` and `devloop_stage`.
  - No error result.
- [ ] T3. `TestUsageSummaryUnknownTopLevelKeyReemitted` (item 4).
  - The backend reply includes `"future_caveat":{"x":1}`.
  - The output contains `future_caveat` with an equal value.
  - A backend `note` or `total` key is overridden by the computed value.
- [ ] T4. `TestUsageSummaryReemitsAllSummaryResultKeys` (item 4 drift guard).
  - Marshal a fully populated `usage.SummaryResult` (with `TruncatedBy` set) plus `group_by` as the reply.
  - Assert that every top-level key of the reply is present in the output.
- [ ] T5. `TestUsageSummaryTruncationReason` (item 1).
  - With `truncated_by:"spend"`, `limit:5`: the reason contains `by spend at limit 5` and not `record_count`.
  - With `truncated_by` absent and `limit` absent: the reason contains `an unknown axis` and no `at limit`.

## Rollback
The change is limited to `internal/mcp/usage.go` and its test file, with no
migration and no config. To roll back, revert the PR and release a patch
version. The previous whitelist behaviour comes back, and no data or state
needs cleanup.
