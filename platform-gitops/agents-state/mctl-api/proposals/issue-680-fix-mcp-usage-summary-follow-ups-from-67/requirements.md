# fix(mcp): tie mctl_get_usage_summary output tightly to the API response (#677 review follow-ups)

## Context
Issue #680 collects four P3 findings from the review of #677, which added the
`mctl_get_usage_summary` MCP tool (`internal/mcp/usage.go`) over
`GET /api/v1/usage/summary`. None of them is a runtime defect today. Each one is
a place where the MCP answer drifts from the API response or reads ambiguously:

1. The truncation reason is hardcoded. It names `record_count` instead of the
   decoded `truncated_by`, and a missing `limit` renders as `at limit ;`.
2. When a field is reported by some buckets and not others, `total` sums only
   the reporting buckets and gives no hint that coverage was partial.
3. The `stage` and `model` aliases are matched case-sensitively, but the
   canonical values are not.
4. The top-level output uses a fixed field whitelist, so a new top-level API
   caveat would drop silently. A local variable `max` also shadows the Go builtin.

The tool reports money (spend) to operators and agents. An answer that reads
ambiguously, or silently drops a caveat, can lead to a wrong conclusion about
spend.

## User stories
- AS a platform admin reading a truncated usage summary I WANT the reason to name the actual truncation axis and limit SO THAT I know how the list was clipped.
- AS a platform admin comparing provider-billed and calculated spend I WANT to see when a total covers only some buckets SO THAT I do not read partial coverage as a spend gap.
- AS an MCP client I WANT `group_by` aliases to accept any letter case, as the canonical values already do, SO THAT `Stage` and `stage` behave the same.
- AS a maintainer I WANT a new top-level field in the API response to reach the MCP output, or fail a test, SO THAT no caveat disappears with green CI.

## Acceptance criteria (EARS)
- WHEN the API response has `truncated: true` THE SYSTEM SHALL build `total_unavailable_reason` from the decoded `truncated_by` value, and SHALL NOT hardcode `record_count`.
- IF `truncated` is true AND `truncated_by` is absent, null or empty THEN THE SYSTEM SHALL name the axis as "an unknown axis".
- IF `truncated` is true AND `limit` is absent, null or empty THEN THE SYSTEM SHALL leave out the "at limit N" clause, and the reason SHALL NOT contain `at limit ;` or a dangling `limit`.
- WHEN `total` is computed AND a summed token or cost field is non-null in at least one bucket but not in all of them THE SYSTEM SHALL emit `total_coverage.<field> = {"buckets_reporting": n, "of": m}` for that field.
- WHILE every summed field is reported by all buckets, or by none, THE SYSTEM SHALL leave out `total_coverage`.
- WHILE coverage is partial THE SYSTEM SHALL keep the summed value in `total.<field>` unchanged. It is still the sum over the reporting buckets, which equals `SUM()` over the ledger.
- WHEN `group_by` is given in any letter case (for example `Stage`, `MODEL`, `DevLoop_Stage`) THE SYSTEM SHALL normalise it the same way as its lowercase form and send the canonical value to the API.
- WHEN the API response has a top-level key the tool does not model THE SYSTEM SHALL re-emit that key and its raw value unchanged in the tool output.
- IF an API top-level key has the same name as a field the tool computes (`total`, `total_unavailable_reason`, `total_coverage`, `cost_semantics`, `note`) THEN THE SYSTEM SHALL keep the computed field. This rule SHALL be covered by a test.
- WHEN any of the new tests runs with its fix reverted THE SYSTEM's test suite SHALL fail.

## Out of scope
- Changing the REST endpoint `GET /api/v1/usage/summary`, `usage.SummaryResult` or `usage.Store.Summary`.
- Adding a second truncation axis to the store.
- Changing the arithmetic of `sumUsageBuckets`. Exact decimal cost sums and int64 token sums stay as they are.
- Changing the tool name, its arguments or the MCP tool count.
- Coverage hints for `count`. Every bucket always carries `count`.

## Open questions
- Should the coverage hint also cover token fields, or only cost fields? The
  issue's example is a cost field. This proposal covers both, because the same
  ambiguity applies to tokens (for example `cache_read_tokens` in
  `TestUsageSummaryTotalsStages`). A reviewer can narrow it to costs only.
- Should `total_coverage` be emitted only for partial fields (the choice here,
  to keep output small), or for every field so the output shape is stable?
- Item 4 is resolved by passing unknown keys through, not only by adding a
  test. The issue accepts either "re-emitted or explicitly accounted for".
- The deployed state of mctl-api was not observed. It does not appear under
  `$MCTL_GITOPS_ROOT/services/`. This change is code-only and needs no config
  change.
