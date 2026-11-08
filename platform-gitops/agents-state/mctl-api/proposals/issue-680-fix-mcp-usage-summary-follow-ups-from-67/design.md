# Design: issue-680-fix-mcp-usage-summary-follow-ups-from-67

## Current state
All four findings are in `internal/mcp/usage.go` (290 lines). Its tests are in
`internal/mcp/usage_test.go`.

- **Handler** (`toolGetUsageSummary`, L68-163):
  - Numeric args are validated at L108-125 with a local `max` (L114). That name
    shadows the Go 1.21+ builtin.
  - `group_by` aliases are resolved by `switch v { case "stage": ...; case "model": ... }`
    (L132-137). The value then goes to `usage.ParseGroupBy`
    (`internal/usage/store.go:573`), which lowercases and trims. So
    `DEVLOOP_STAGE` is accepted but `Stage` falls through and is rejected.
  - The tool schema also declares `mcplib.Enum(usageGroupByValues()...)`
    (lowercase). The handler is lenient for canonical values, and a fix makes it
    lenient for aliases too.
- **Output** (`usageSummaryOut`, L167-177; `buildUsageSummary`, L179-218):
  - The function decodes a fixed anonymous struct (`group_by`, `buckets`,
    `truncated`, `truncated_by`, `limit`) with `UseNumber`, then marshals a
    fixed output struct. Any other top-level key is dropped.
  - When truncated, L206 builds the reason as
    `"bucket list truncated by record_count at limit %s; ..."`. It uses
    `string(in.Limit)` raw and ignores `in.TruncatedBy`.
- **Totals** (`sumUsageBuckets`, L227-290): for every token field
  (`usageTokenFields`) and cost field (`usageCostFields`):
  - it sums the non-null bucket values;
  - it returns `null` only when no bucket reports the field;
  - it does not record how many buckets reported the field.
- **API side**:
  - `internal/api/handlers_usage.go:133` defines
    `summaryUsageResponse{GroupBy; *usage.SummaryResult}`.
  - `internal/usage/store.go:616` defines `SummaryResult{Buckets, Truncated, TruncatedBy, Limit}`.
  - `Store.Summary` sets `TruncatedBy = "record_count"` (L670), so today the
    hardcoded text happens to be correct.
  - `internal/api` imports `internal/mcp`, so an mcp test cannot import
    `internal/api` (import cycle). It can import `internal/usage`.
- **Tests**: `usage_test.go` covers:
  - all-present and all-absent totals (`TestUsageSummaryTotalsStages`, `TestUsageSummaryKeepsCostsApart`);
  - truncation (`TestUsageSummaryTruncatedHasNoTotal`, which does not check the reason text);
  - lowercase aliases only (`TestUsageSummaryArgValidation`).

  No test covers mixed coverage, alias case, or unknown keys.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/` (`ls`) lists only the tenants `admins`, `karabu`,
  `labs` and `namax66`. No `*/mctl-api/values.yaml` exists, so mctl-api's
  deployed config was **not observed** from this checkout.
- No mctl MCP tool was called. The change is pure in-process response shaping
  and depends on no deployed config, env var or replica setting.

## Proposed solution
All changes are in `internal/mcp/usage.go` and `internal/mcp/usage_test.go`.

1. **Truncation reason (item 1).** Add `usageTruncationReason(truncatedBy, limit json.RawMessage) string`.
   - Decode `truncatedBy` as a JSON string. Use it if it is a non-empty string;
     otherwise use `"an unknown axis"`.
   - Include `" at limit " + string(limit)` only when `limit` is present, not
     `null` and not empty.
   - Result:
     `"bucket list truncated by <axis>[ at limit N]; a sum of the returned buckets would understate usage. Narrow the filter or raise limit."`
   - Update the tool description sentence "a truncated list is clipped by record
     count" so it does not hardcode the axis either. For example: "is clipped
     (see truncated_by)".

2. **Coverage hint (item 2).**
   - `sumUsageBuckets` also returns `map[string]usageCoverage`, where
     `type usageCoverage struct{ BucketsReporting int `json:"buckets_reporting"`; Of int `json:"of"` }`.
   - Count the reporting buckets per token and cost field.
   - Record an entry only when `0 < reporting < len(buckets)`.
   - Emit the map as `total_coverage` (omitempty).
   - When it is non-empty, add to `note`: `"total_coverage lists fields reported by only some buckets; their total sums the reporting buckets only"`.
   - Update the tool description with one sentence about `total_coverage`.
   - `total.<field>` keeps its value, because it already matches ledger `SUM()`.

3. **Case-insensitive aliases (item 3).**
   - Lowercase before the alias switch: `v = strings.ToLower(strings.TrimSpace(rawGB))`, then `switch v`.
   - `ParseGroupBy` still lowercases, so canonical values are unaffected.

4. **No silent drops (item 4).** Replace the fixed output struct with a passthrough.
   - Decode the body into `map[string]json.RawMessage`, using `UseNumber`
     semantics. Raw messages keep numbers verbatim.
   - Decode the known fields from it as today: `buckets`, `truncated`,
     `truncated_by`, `limit`.
   - Copy every top-level key into the output map unchanged.
   - Set or overwrite the computed keys:
     - `buckets` (normalised to `[]` when absent or null);
     - `truncated` (still emitted as a bool, as today);
     - `total`;
     - `total_unavailable_reason`;
     - `total_coverage`;
     - `cost_semantics`;
     - `note`.
   - Delete `truncated_by` when it is null, as today.
   - `json.Marshal` of a map sorts keys, which is deterministic. Key order is
     not part of the tool contract.
   - Keep `usageSummaryOut` only if it stays useful as documentation. Otherwise
     remove it and add a comment that lists the computed keys.
   - Add a drift-guard test:
     - It marshals a fully populated `usage.SummaryResult`, plus a `group_by`
       key to mirror `summaryUsageResponse`, as the backend reply.
     - It asserts that every top-level key of that reply appears in the tool
       output.
     - It also feeds a fixture with an unknown key `future_caveat` and asserts
       that the key comes back byte-equal.

5. **Nit.** Rename `max` to `upper` at L114/L116/L118.

## Alternatives
- **Keep the whitelist and only add a test that fails on unknown keys.**
  - This meets the issue's wording, but it turns every API addition into a
    red test and a manual MCP edit.
  - Passthrough is the safer default for a surface whose whole point is "API
    fields re-emitted as received".
  - Dropped, but the reflection-style guard test is still added.
- **Report coverage for every field, including fully covered ones.**
  - This gives a stable shape, but it adds about 9 entries to every response,
    mostly noise.
  - Dropped in favour of partial-only. This is recorded as an open question.
- **Null out a partially covered total instead of annotating it.**
  - This hides a correct number that matches ledger `SUM()`, and it breaks
    readers who use the total today.
  - Dropped.
- **Fix aliases by adding the uppercase forms to the enum.** This does not
  scale to mixed case. Dropped.

## Platform impact
- No migrations, no API change, no new tool, and the MCP tool count is unchanged.
- **Backward compatibility:**
  - The output is a superset: new optional `total_coverage`, passthrough of any
    future keys, and possibly a longer `note`.
  - The `total_unavailable_reason` text changes only when `truncated_by` or
    `limit` are missing. With the current store (`record_count`, limit always
    set), the text is unchanged.
  - Output JSON key order changes (map marshal is alphabetical). No consumer
    should depend on key order.
- **Resource impact:** negligible (one extra map decode per call).
- **Risks:**
  - *An API key could collide with a computed key.* Mitigation: computed keys
    always win, and a test asserts it (for example, a backend `note` or `total`
    is overwritten by the computed one).
  - *A passthrough key could carry something the MCP surface should not show.*
    Mitigation: the endpoint is admin-only (`requireUsageAdmin`) and the same
    caller can read the REST body directly. Passthrough exposes nothing new.
