# Expose the model-usage / DevLoop cost summary over MCP (mctl_get_usage_summary)

## Context

The durable model-usage ledger (ADR-012, mctl-api#266) already lives in
`internal/usage` and is readable over HTTP at `GET /api/v1/usage/records` and
`GET /api/v1/usage/summary` (`internal/api/handlers_usage.go`). Operators who
work through MCP (ChatGPT / Claude via the Cloudflare portal) have no tool for
it, so answering "how much did `dev-loop-mctlhq-mctl-agents-663` cost?" today
means reading archived Argo logs and summing `ResultMessage.total_cost_usd` by
hand, which is exactly the log archaeology the ledger was built to remove.

This proposal adds one read-only, admin-only MCP tool, `mctl_get_usage_summary`,
that relays to the existing `/api/v1/usage/summary` route with the caller's own
token, defaults to grouping by DevLoop stage, and adds a grand total computed
only from complete (non-truncated) bucket lists. No new pricing, no new store,
no change to the HTTP endpoint's semantics.

## User stories

- AS a platform admin I WANT to ask an MCP client for one DevLoop's usage by `workflow_id`, broken down by stage, SO THAT I can report investigator / implementer / shepherd cost without reading Argo logs.
- AS a platform admin I WANT to group usage by agent, model, provider, repository, outcome, workflow, work item or execution SO THAT I can see where model spend went.
- AS a platform admin I WANT provider-reported, calculated (list-price estimate) and invoice-reconciled cost kept separate SO THAT an estimate is never mistaken for billed spend.
- AS a platform admin I WANT an unconfigured ledger or a truncated summary to be reported explicitly SO THAT I never read "unknown" or "partial" as "zero" or "complete".

## Acceptance criteria (EARS)

- WHEN the MCP server starts THE SYSTEM SHALL register a tool named `mctl_get_usage_summary` annotated readOnlyHint=true, destructiveHint=false, with an explicit idempotentHint, recorded in `recordedHints` in `internal/mcp/annotations_test.go`.
- WHEN `mctl_get_usage_summary` is called THE SYSTEM SHALL issue exactly one `GET /api/v1/usage/summary` request to the mctl API carrying the caller's own bearer token, and SHALL NOT read Argo logs, Loki or any other source.
- WHEN the caller supplies any of `workflow_id`, `run_id`, `execution_id`, `work_item_id`, `repository`, `issue`, `pr`, `agent`, `stage`, `provider`, `model`, `outcome`, `since`, `until`, `limit` THE SYSTEM SHALL forward each one under the identical HTTP query parameter name used by `usageFilterFromQuery`.
- WHEN `group_by` is omitted THE SYSTEM SHALL request `group_by=devloop_stage`.
- WHEN `group_by` is `stage` THE SYSTEM SHALL treat it as `devloop_stage`; for any other value THE SYSTEM SHALL forward it unchanged so the API's closed `usage.ParseGroupBy` set remains the single source of valid dimensions.
- WHEN the API answers 2xx THE SYSTEM SHALL return every field the API returned (`group_by`, `buckets` with all token, web-search and cost fields, `truncated`, `truncated_by`, `limit`) unchanged.
- WHEN the API answers 2xx AND `truncated` is false THE SYSTEM SHALL add a `total` object whose `count` and each token/web-search/cost field is the sum of that field over the returned buckets, computed separately per field.
- IF every returned bucket omits a given field THEN THE SYSTEM SHALL omit (leave null) that field in `total` rather than reporting 0.
- IF `truncated` is true THEN THE SYSTEM SHALL NOT compute a total, SHALL set `total` to null, and SHALL set `total_unavailable_reason` explaining that the bucket list is truncated (by `truncated_by`) and that a narrower filter or larger `limit` is needed.
- WHILE building `total` THE SYSTEM SHALL keep `provider_reported_cost`, `calculated_cost` and `invoice_reconciled_cost` as three separate fields and SHALL NOT add them together or relabel any of them.
- WHEN returning a result THE SYSTEM SHALL include a `cost_semantics` note stating that `calculated_cost` is a list-price estimate (not provider-billed or invoice spend), that `provider_reported_cost` and `invoice_reconciled_cost` are separate classifications, that each cost sum covers only the records that carried that cost, and that a bucket with key "" holds records with no value for the grouped dimension.
- IF the API answers 503 (ledger not configured) THEN THE SYSTEM SHALL return an MCP tool error naming the HTTP status and body, and SHALL NOT return an empty or zero result.
- IF the API answers 401 or 403 THEN THE SYSTEM SHALL return an MCP tool error; authorization SHALL remain the API's `requireUsageAdmin` check (admin-only), unchanged.
- IF `issue` or `pr` is not a positive integer, or `limit` is not an integer in 1..`usage.MaxQueryLimit`, or any string argument is supplied as a non-string THEN THE SYSTEM SHALL return a tool error without calling the API.
- IF `issue` or `pr` is supplied without `repository` THEN THE SYSTEM SHALL return a tool error without calling the API (mirroring `usageFilterFromQuery`).
- WHILE this change is deployed THE SYSTEM SHALL keep `GET /api/v1/usage/summary` behaviour identical, including its default `group_by=agent`.
- WHEN the tool is added THE SYSTEM SHALL carry an explicit entry for `mctl_get_usage_summary` in `docs/portal-allowlist.json` with a reason, so `TestPortalAllowlist_CoversEveryRegisteredTool` passes.

## Out of scope

- New pricing logic, a second cost store, or recomputing cost in the MCP layer.
- Parsing `ResultMessage` / `model_usage` from Argo or Loki logs.
- Budget enforcement and provider invoice reconciliation.
- Changing the HTTP summary response or its default `group_by`.
- An MCP tool over `GET /api/v1/usage/records` (row listing); can follow separately.
- Claiming complete issue cost for model calls never emitted into the ledger (mctl-agents#507 producer coverage).
- UI / dashboard work.

## Open questions

- Portal exposure: this proposal records `enabled: true` in `docs/portal-allowlist.json` with a reason relying on the API's admin check (the same pattern as `mctl_get_lifecycle_ownership`), because the motivating operator path is a portal client. Per-repository spend is described in `handlers_usage.go` as commercially sensitive; the owner must confirm enabling it, or flip it to `enabled: false`. The entry does not invent an "owner decision" date.
- Cost coverage within a bucket: SQL `SUM()` ignores NULL, so a bucket's `calculated_cost` may cover only some of its `count` records (e.g. records ingested before a pricing catalog was loaded). The store does not expose per-cost record counts today. This proposal documents the caveat in `cost_semantics`; adding `COUNT(calculated_cost)`-style coverage fields to `usage.Bucket` would be an additive HTTP change and is left to a follow-up.
- The MCP default `group_by=devloop_stage` deliberately differs from the HTTP default (`agent`), per the issue's DevLoop use case. Reviewers should confirm that divergence is acceptable.
- Deployed configuration of mctl-api (whether `USAGE_DB_URL` / `AUDIT_DB_URL` and `USAGE_PRICING_CATALOG` are set in production) could not be observed from this run; if the ledger is unconfigured in production the tool will correctly return a 503-derived error, but will not be useful until it is configured.
