# Expose the model-usage summary as a read-only admin MCP tool (mctl_get_usage_summary)

## Context

mctl-api already has a durable model-usage and cost ledger (ADR-012, mctl-api#266):
`internal/usage` (`Store.Summary`, `Filter`, `GroupBy`, `Bucket`, `SummaryResult`) and
the admin-only HTTP reads `GET /api/v1/usage/records` and `GET /api/v1/usage/summary`
(`internal/api/handlers_usage.go`). There is no MCP tool over it. When an operator
asks "how much did `dev-loop-mctlhq-mctl-agents-663` cost?", the assistant today has
to read archived Argo logs and add up `ResultMessage.total_cost_usd` by hand, which is
exactly the log archaeology the ledger was built to remove.

This proposal adds one read-only, admin-only MCP tool, `mctl_get_usage_summary`, that
relays `GET /api/v1/usage/summary` and adds a grand total. The total is computed only
by summing the returned buckets, and only when the result is not truncated. The tool
keeps ADR-012's cost semantics: provider-reported, calculated (a list-price estimate)
and invoice-reconciled cost stay three separate numbers, absent values stay absent
instead of becoming zero, and an unavailable ledger is an explicit error, never zero
spend. It adds no pricing logic, no second store and no log parsing.

## User stories

- AS a platform operator I WANT to ask for one DevLoop's usage by `workflow_id`, grouped by stage, SO THAT I get investigator / implementer / shepherd lines and a total without reading Argo logs.
- AS a platform operator I WANT to group usage by agent, model, provider, repository, outcome or execution SO THAT I can see which agent or model accounted for the spend.
- AS a platform operator I WANT to filter by repository + issue/PR and a time window SO THAT I can answer "what did issue/PR X use this week".
- AS a FinOps reviewer I WANT calculated cost always labelled as a list-price estimate and kept apart from provider-reported and invoice-reconciled cost SO THAT nobody reads an estimate as a bill.

## Acceptance criteria (EARS)

- WHEN an MCP client lists tools THE SYSTEM SHALL register `mctl_get_usage_summary` with `readOnlyHint=true`, `destructiveHint=false`, `idempotentHint=false` (the same hint set as the other admin reads), and a description that says it is admin-only.
- WHEN `mctl_get_usage_summary` is called THE SYSTEM SHALL answer by calling `GET /api/v1/usage/summary` with the caller's own token, and SHALL NOT read Argo logs, workflow archives or any other source.
- WHEN the caller passes any of `workflow_id`, `run_id`, `execution_id`, `work_item_id`, `repository`, `issue`, `pr`, `agent`, `stage`, `provider`, `model`, `outcome`, `since`, `until`, `limit` THE SYSTEM SHALL forward each one as the query parameter of the same name that `usageFilterFromQuery` reads.
- WHEN `group_by` is omitted THE SYSTEM SHALL send `group_by=devloop_stage` explicitly. The HTTP endpoint's own default (`agent`) stays unchanged.
- WHEN `group_by` is given THE SYSTEM SHALL accept only the closed set `agent`, `devloop_stage`, `canonical_model`, `provider`, `target_repo`, `temporal_workflow_id`, `work_item_id`, `execution_id`, `outcome`, plus the aliases `stage` -> `devloop_stage` and `model` -> `canonical_model`, and SHALL refuse any other value with a tool error before calling the API.
- WHEN `workflow_id=<dev-loop-...>` and `group_by=devloop_stage` are given THE SYSTEM SHALL return one bucket per stage, with record count, token / cache / reasoning / web-search sums and the three cost sums, exactly as `usage.Store.Summary` produced them.
- WHEN the API response has `truncated=false` THE SYSTEM SHALL add a `total` object holding the sums of `count`, every token dimension and each of the three cost fields separately, computed from the returned buckets only.
- WHILE computing `total` THE SYSTEM SHALL leave a dimension or cost field null when it is null in every bucket, and SHALL sum the costs in exact decimal arithmetic, never by adding one cost field into another.
- IF the API response has `truncated=true` THEN THE SYSTEM SHALL leave `total` out, set `total_unavailable_reason` to say the bucket list was clipped by record count, and keep `truncated`, `truncated_by` and `limit` exactly as the API returned them.
- WHEN the summary matches no records THE SYSTEM SHALL return an empty bucket list and a total whose `count` is 0 and whose costs are null, plus a note that this means the ledger holds no records for the filter, not that zero was spent.
- WHILE returning any summary THE SYSTEM SHALL include a `cost_semantics` block that labels `calculated_cost` as a list-price estimate that is neither provider-billed nor invoice spend, `provider_reported_cost` as cost reported by the provider, and `invoice_reconciled_cost` as invoice-reconciled spend.
- IF the API answers 503 (ledger not configured or not reachable) THEN THE SYSTEM SHALL return a tool error saying usage is UNKNOWN, not zero.
- IF the API answers 401 or 403 THEN THE SYSTEM SHALL return a tool error with the API's message, so authorization stays exactly the same as `requireUsageAdmin`.
- IF the API answers 400 (for example issue or pr without repository, a bad RFC3339 time, a limit over `usage.MaxQueryLimit`) THEN THE SYSTEM SHALL relay that error and SHALL NOT retry with a wider filter.
- IF `issue`, `pr` or `limit` is not a positive integer, or `limit` is greater than `usage.MaxQueryLimit` (1000), or a string filter has a non-string value THEN THE SYSTEM SHALL refuse the call with a tool error and SHALL NOT drop that filter.
- WHEN this change ships THE SYSTEM SHALL keep the request parsing, default `group_by`, auth and response shape of `GET /api/v1/usage/summary` byte-identical.
- WHEN this change ships THE SYSTEM SHALL add an explicit entry for `mctl_get_usage_summary` to `docs/portal-allowlist.json`, with a reason.

## Out of scope

- New pricing logic, recomputing `calculated_cost`, or a second cost store.
- Parsing `ResultMessage` / `total_cost_usd` from Argo logs.
- Hard budget enforcement or alerting.
- Provider invoice reconciliation.
- An MCP tool over `GET /api/v1/usage/records` (the per-row list).
- Changes to `internal/usage` or `internal/api/handlers_usage.go`.
- Claiming a complete "issue cost" for model calls that were never written to the ledger (uninstrumented producers, mctl-agents#507).
- UI or dashboard work.

## Open questions

- Portal allowlist: the proposal adds the tool with `enabled: false`, like the commerce reads that are waiting on an owner decision. The issue asks for "an explicit decision", and enabling it on the shared portal is an owner call. The reviewer should confirm `false`, or flip it to `true` with an owner-decision provenance sentence.
- Default `group_by`: the proposal uses `devloop_stage` in the MCP tool (the issue's main use case) and leaves the HTTP default as `agent`. If the owners would rather the tool match the HTTP default, change only the default constant in the tool.
- Producer coverage: shepherd and some other stages may not write ledger rows yet (mctl-agents#507). The tool reports only what the ledger holds. A missing stage bucket means "no rows recorded", and the description says so.
- The deployed state of mctl-api (whether `USAGE_DB_URL` / `AUDIT_DB_URL` is set in production) could not be checked in this run. See design.md.
