# Expose the model-usage / DevLoop cost summary over MCP (mctl_get_usage_summary)

## Context

The durable model-usage ledger (ADR-012, mctlhq/mctl-api#266) already exists in
`internal/usage` and has an admin-only HTTP read surface: `GET /api/v1/usage/records`
and `GET /api/v1/usage/summary` (`internal/api/handlers_usage.go`). The MCP
server (`internal/mcp`) has no tool over it. So when an operator asks "how much
did this DevLoop cost?", the assistant reads archived Argo logs, finds the
terminal `ResultMessage.total_cost_usd` / `model_usage`, and adds the numbers up
by hand. That is what happened for `dev-loop-mctlhq-mctl-agents-663`. The ledger
exists so that this question takes one query, not a search through logs.

This proposal adds one read-only, admin-only MCP tool, `mctl_get_usage_summary`.
It relays the existing `/api/v1/usage/summary` endpoint with the caller's own
token. It returns the API's buckets unchanged, adds a grand total only when the
bucket list is complete, and keeps the three ADR-012 cost classes apart. It adds
no pricing logic and no second store, and it does not change any HTTP behaviour.

## User stories

- AS a platform operator I WANT to ask for one DevLoop's usage by `workflow_id`, grouped by DevLoop stage, SO THAT I can report investigator / implementer / shepherd spend and a total without reading Argo logs.
- AS a platform operator I WANT to group usage by agent, model or provider, SO THAT I can see which agent or model accounts for the spend.
- AS a platform operator I WANT to filter by repository / issue / PR and a time window, SO THAT I can answer "what did repo X or issue Y use this week".
- AS a FinOps reviewer I WANT calculated (list-price) cost always labelled as an estimate and kept apart from provider-reported and invoice-reconciled cost, SO THAT nobody reads an estimate as billed spend.

## Acceptance criteria (EARS)

- THE SYSTEM SHALL register an MCP tool named `mctl_get_usage_summary` with `readOnlyHint=true` and `destructiveHint=false`, declared explicitly in `internal/mcp/annotations_test.go` `recordedHints`.
- WHEN `mctl_get_usage_summary` is called THE SYSTEM SHALL answer by calling `GET /api/v1/usage/summary` on mctl-api with the caller's own bearer token, and SHALL NOT read Argo logs, workflow archives or any other source.
- WHEN the caller supplies any of `workflow_id`, `run_id`, `execution_id`, `work_item_id`, `repository`, `issue`, `pr`, `agent`, `stage`, `provider`, `model`, `outcome`, `since`, `until`, `limit` THE SYSTEM SHALL forward each one under the HTTP query parameter of the same name, without changing its meaning.
- WHEN `group_by` is omitted THE SYSTEM SHALL send `group_by=devloop_stage` explicitly to the API, so the default for the HTTP endpoint stays `agent`.
- WHEN `group_by` is `stage` THE SYSTEM SHALL treat it as `devloop_stage`. WHEN `group_by` is any other value outside the closed `usage.GroupBy` set THE SYSTEM SHALL return a tool error without calling the API.
- WHEN `workflow_id=<dev-loop-...>` is given with the default grouping THE SYSTEM SHALL return one bucket per `devloop_stage` (for example `investigator`, `implementer`, `shepherd`), each carrying count, the token / cache / reasoning / web-search sums, and the three cost fields, exactly as the API returned them.
- WHEN the API answer has `truncated=false` THE SYSTEM SHALL add a `total` object with `status="complete"`. Its count, token sums and cost sums SHALL be computed only by adding up the returned buckets.
- IF the API answer has `truncated=true` THEN THE SYSTEM SHALL return `total.status="withheld"` with a reason that names `truncated_by`, and SHALL NOT return any total figure.
- WHILE computing a total, THE SYSTEM SHALL leave a dimension null when that dimension is null in every bucket (absent is not zero), and SHALL add costs with exact decimal arithmetic rather than float64 addition.
- WHILE building a response, THE SYSTEM SHALL keep `provider_reported_cost`, `calculated_cost` and `invoice_reconciled_cost` as separate fields in every bucket and in the total, and SHALL never add them into one number.
- THE SYSTEM SHALL label `calculated_cost` in the response (`cost_semantics`) and in the tool description as a list-price estimate from the pricing catalog, not provider-billed or invoice spend.
- THE SYSTEM SHALL pass through `truncated`, `truncated_by` and `limit` from the API unchanged, and SHALL echo the effective `group_by` and filters it sent.
- IF the API answers 503 (ledger not configured) or any other non-2xx status, or the request fails, THEN THE SYSTEM SHALL return a tool error that says spend is unknown, and SHALL NOT return an empty or zero summary.
- IF the caller is not an admin THEN THE SYSTEM SHALL relay the API's 401/403 as a tool error. Authorization stays solely in `requireUsageAdmin`.
- IF a filter argument is present with the wrong JSON type, or `issue` / `pr` / `limit` is not a positive integer, or `limit` exceeds `usage.MaxQueryLimit`, THEN THE SYSTEM SHALL return a tool error and SHALL NOT silently drop the filter.
- IF `issue` or `pr` is given without `repository` THEN THE SYSTEM SHALL return a tool error, matching the HTTP rule.
- WHEN the filter matches no records THE SYSTEM SHALL return an empty bucket list with `total.status="complete"` and `count=0`, and the response SHALL state that the ledger covers only instrumented producers.
- THE SYSTEM SHALL list `mctl_get_usage_summary` in `docs/portal-allowlist.json` with an explicit `enabled` decision and a reason.
- THE SYSTEM SHALL leave the request parsing, defaults, authorization and response shape of `GET /api/v1/usage/summary` unchanged.

## Out of scope

- New pricing logic, re-pricing, or any second cost store.
- Parsing `ResultMessage` or `model_usage` out of Argo logs.
- Hard budget enforcement or alerts.
- Provider invoice reconciliation (`invoice_reconciled_cost` stays as recorded).
- Claiming a complete "issue cost" for model calls never emitted into the ledger (ad-hoc local benchmarks, producers not yet covered by mctlhq/mctl-agents#507).
- An MCP tool for `GET /api/v1/usage/records`. This proposal covers the summary only.
- A server-side grand total in the HTTP response.
- UI and dashboard work.

## Open questions

- Portal allowlist: this proposal records `enabled: false` on the shared portal. Per-repository and per-agent spend is commercially sensitive (the reason the HTTP reads are admin-only), and enabling it is an owner decision, the same way `mctl_get_commerce_budget` stayed off while `mctl_get_lifecycle_ownership` was enabled by a dated owner decision. If the owner wants it on, flip the entry and add the provenance sentence.
- Default `group_by`: the issue allows either. This proposal uses `devloop_stage` as the MCP default, because the main use is the DevLoop query, and always sends it explicitly so the HTTP default (`agent`) does not change. The `stage` alias is a convenience. It may be dropped if reviewers prefer the closed column names only.
- Not checked: whether the production ledger already holds rows for `dev-loop-mctlhq-mctl-agents-663`, and whether those rows carry `devloop_stage`. No read-only tool in this run can query the ledger. If the producers in mctl-agents emitted those rows without `devloop_stage`, the stage breakdown will show them under the `""` key until producer coverage improves (mctlhq/mctl-agents#507).
- Rows without a value for the grouped dimension (for example `devloop_stage=''`) come back as a bucket with key `""` and are included in the total, because they are real spend in the filter. The tool reports them under that key without relabelling. Reviewers may prefer a display label such as `(unset)`.
