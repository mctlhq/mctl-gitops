# Expose the model-usage / DevLoop cost summary over MCP (mctl_get_usage_summary)

## Context

mctl-api already holds the durable model-usage ledger from ADR-012 / mctl-api#266
(`internal/usage`) and serves it over HTTP at `GET /api/v1/usage/records` and
`GET /api/v1/usage/summary` (`internal/api/handlers_usage.go`). Both are admin-only,
answer 503 when the ledger is not configured, keep `provider_reported_cost`,
`calculated_cost` and `invoice_reconciled_cost` apart, and report `truncated` /
`truncated_by` / `limit`. No MCP tool reaches them. An operator who asks "how much
did `dev-loop-mctlhq-mctl-agents-663` cost?" therefore gets an answer built from
archived Argo logs (`ResultMessage.total_cost_usd`, `model_usage`) and added up by
hand. The ledger exists so that this is not needed.

This proposal adds one read-only, admin-gated MCP tool, `mctl_get_usage_summary`. It
is a thin client of the existing `/api/v1/usage/summary` route and adds one thing: a
per-cost-class total. That total is computed only by summing the returned buckets, and
only when the bucket list is complete. It adds no pricing logic, no second store and
no log parsing.

## User stories

- AS a platform operator I WANT to ask an MCP client how much one DevLoop
  (`workflow_id=dev-loop-...`) used, broken down by stage, SO THAT I can answer cost
  questions without reading Argo logs.
- AS a platform operator I WANT to group usage by agent, model, provider, repository,
  workflow, work item, execution or outcome SO THAT I can see where the spend went.
- AS a platform operator I WANT to filter by repository / issue / PR and a time window
  SO THAT I can see what one piece of work used.
- AS a FinOps reviewer I WANT estimated (calculated) cost always labelled apart from
  provider-reported and invoice-reconciled cost SO THAT no one reads an estimate as an
  invoice.

## Acceptance criteria (EARS)

- WHEN the MCP server starts THE SYSTEM SHALL register a tool named
  `mctl_get_usage_summary` with `readOnlyHint=true`, `destructiveHint=false` and an
  explicit `idempotentHint` recorded in `internal/mcp/annotations_test.go`.
- WHEN `mctl_get_usage_summary` is called THE SYSTEM SHALL issue exactly one
  `GET /api/v1/usage/summary` request with the caller's own bearer token, and SHALL NOT
  read Argo logs, Loki or any other source.
- WHEN the caller passes any of `workflow_id`, `run_id`, `execution_id`,
  `work_item_id`, `repository`, `issue`, `pr`, `agent`, `stage`, `provider`, `model`,
  `outcome`, `since`, `until`, `group_by`, `limit` THE SYSTEM SHALL forward it under
  the same query-parameter name the HTTP handler reads in `usageFilterFromQuery`.
- WHEN `group_by` is omitted THE SYSTEM SHALL send `group_by=devloop_stage`, and the
  response SHALL state the `group_by` that was applied.
- WHEN `group_by=stage` is given THE SYSTEM SHALL treat it as `devloop_stage`. Any
  other value SHALL go to the API unchanged, so the API's closed set (`ParseGroupBy`)
  stays the only authority.
- WHEN `workflow_id=<dev-loop-id>` and `group_by=devloop_stage` are given THE SYSTEM
  SHALL return one bucket per distinct `devloop_stage` (for example `investigator`,
  `implementer`, `shepherd`, plus an empty-key bucket for unattributed rows) with
  token, cache, reasoning, web-search and the three cost fields.
- WHEN the API reports `truncated=false` THE SYSTEM SHALL add a `total` object that
  holds `count`, each token dimension and each of the three cost classes, each one the
  sum of that field over the returned buckets. A field that is null in every bucket
  SHALL stay null, never become 0.
- IF the API reports `truncated=true` THEN THE SYSTEM SHALL set `total` to null, set
  `total_status` to `"withheld_truncated"`, and pass through `truncated`,
  `truncated_by` and `limit`.
- WHILE a total is present THE SYSTEM SHALL keep `provider_reported_cost`,
  `calculated_cost` and `invoice_reconciled_cost` as separate fields, and SHALL NOT
  produce any field that combines them.
- WHILE a response carries `calculated_cost` THE SYSTEM SHALL describe it, in the tool
  description and in the response's `cost_semantics` note, as a list-price estimate
  that is neither provider-billed nor invoice spend.
- WHILE a total is present THE SYSTEM SHALL list, per field, the bucket keys whose
  value was null (`total.missing_in_buckets`), so that a partial measurement does not
  read as complete.
- IF the ledger is not configured (API 503) THEN THE SYSTEM SHALL return an MCP tool
  error that keeps the HTTP status and body, and SHALL NOT return an empty or zero
  summary.
- IF the caller is not an admin (API 401/403) THEN THE SYSTEM SHALL return an MCP tool
  error. Authorization SHALL stay in the API's `requireUsageAdmin`, so the tool cannot
  be more permissive than the HTTP route.
- IF `issue` or `pr` is given without `repository`, or `limit` is not an integer in
  1..1000, or a filter argument is present but is not a string, THEN THE SYSTEM SHALL
  refuse the call before any request is sent.
- WHILE this tool exists THE SYSTEM SHALL leave the behaviour and response shape of
  `GET /api/v1/usage/summary` and `GET /api/v1/usage/records` unchanged.
- WHEN the tool is added THE SYSTEM SHALL record an explicit entry for it in
  `docs/portal-allowlist.json` with a reason, as `internal/mcp/portal_allowlist_test.go`
  requires.

## Out of scope

- New pricing logic, re-pricing, or a second cost store.
- Parsing `ResultMessage` or anything else from Argo or Loki logs.
- Budget enforcement or alerting.
- Provider invoice reconciliation (`invoice_reconciled_cost` stays as stored).
- Claims of complete "issue cost" for model calls that were never sent to the ledger
  (mctlhq/mctl-agents#507 covers producer coverage).
- An MCP tool over `GET /api/v1/usage/records` (row listing).
- Changes to `usage.Store`, `usage.Bucket`, `usage.SummaryResult` or the HTTP handlers.
- UI / dashboard work.

## Open questions

- Default `group_by`: the HTTP route defaults to `agent`. This proposal makes the MCP
  tool default to `devloop_stage`, the main operator question in the issue, and states
  the applied value in the response. A reviewer may prefer to keep the HTTP default.
- Partial coverage inside a bucket: `SUM()` ignores NULLs, so a bucket in which only
  some rows have `calculated_cost` shows a non-null sum with no sign that rows are
  missing. The `Bucket` type does not expose a per-field non-null count. The tool can
  flag only buckets where the field is null throughout. A per-field coverage count
  would be an additive change to `usage.Store.Summary` and is left as follow-up.
- Portal decision: this proposal records `enabled: false` (admin-only and commercially
  sensitive per the comment in `handlers_usage.go`). mctl-gitops vendors
  `docs/portal-allowlist.json` byte-identical, so an owner decision to enable it
  belongs to the owner.
- Producer coverage: whether the investigator / implementer / shepherd producers for
  `mctlhq/mctl-agents#663` actually set `temporal_workflow_id` and `devloop_stage` on
  their records was not checked against the live ledger. This run had no read path to
  it.
- Float summation: costs are Postgres `NUMERIC` but decode as Go `float64`, so a
  client-side sum can show float artefacts. The design rounds each summed cost to 9
  decimal places. The exact precision is a judgement call.
