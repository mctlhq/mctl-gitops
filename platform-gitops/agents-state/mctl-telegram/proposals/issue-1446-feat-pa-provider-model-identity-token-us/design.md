# Design: issue-1446-feat-pa-provider-model-identity-token-us

## Current state

Worker side (`internal/agentworker`):
- `openaiclient.go`: `ChatUsage` holds only `PromptTokens` and `CompletionTokens`. `chat()` and
  the stream path (`openaistream.go`, usage chunk via `stream_options.include_usage`) set
  `ChatResult.UsageReported` only when either count is positive, so a missing or all-zero usage
  means unknown spend. The response's top-level `model` field is not decoded; `ChatResult` has no
  model. `prompt_tokens_details` / `completion_tokens_details` are ignored. `ProviderError`
  carries only status and `Retry-After` (bodies never retained).
- `prices.go`: `Prices{InputUSDPerMTok, OutputUSDPerMTok}.Cost(u)` is a two-rate list-price
  estimate. Prices come from required env `MODEL_INPUT_USD_PER_MTOK` /
  `MODEL_OUTPUT_USD_PER_MTOK` (`cmd/agent-worker/pa_mode.go`, `openAIClientFromEnv`); there is no
  version or source.
- `parunner.go` `run()`: sums `w.Prices.Cost(res.Usage)` per model call into `cost`; any call
  without usage sets `costKnown=false`, which ends the run before another tool round
  (`errPACostLimit`) and makes the reply carry `cost_usd: null` (settled at full reservation).
  `chat()` makes up to `paModelAttempts = 4` provider attempts, each behind its own `/turn`
  admission, retrying 429/5xx; a failed attempt adds no cost. The only per-run log is
  `pa worker: job finished` with `job_id`, `attempt`, `outcome` (and `reason` on failure).
- `reply()` sends `{text, cost_usd}`; failures go through the abandon report with `fail_reason`.

Server side:
- `internal/pa/runloop.go`: `replyRequest{Text, CostUSD *float64, FailReason}` decoded with
  lenient `json.Unmarshal` (unknown fields ignored), bounded by `maxReplyBody`; overflow drops the
  cost. A cost above `PerJobUSD` is logged. `FinishPAJob` is called with `CostUSD` (-1 = unknown).
- `internal/db/pa_jobs.go`: `pa_usage(job_id, attempt, principal, reserved_usd, cost_usd,
  reported_cost_usd, status reserved|held|settled)` with `UNIQUE(job_id, attempt)`. Settlement is
  `jobs.Settle(reported, reserved, max(turns, toolCalls+1), MinTurnUSD)` (cap
  `SettleFactor = 4` x reservation, floor per turn). `paWindowSums` drives the day/month windows.
- `internal/pa/timing.go` + `internal/metrics/pa.go`: `mctl_pa_run_phase_seconds{phase}`,
  `mctl_pa_job_failures_total{reason}` and webhook/outbox counters. No PA token, cost or model
  metric exists.
- Shared communication-agent accounting (#580/#583, #1091): `internal/agentapi/events.go`
  `countUsage` feeds `mctl_agent_usage_cost_usd_total{runner,model}` and
  `mctl_agent_usage_tokens_total{direction,model}`, with the model label bounded by
  `Registry.UsageModel` (`MaxUsageModelLabels = 16`, `unknown`/`other`, tested in
  `internal/metrics/usage_model_test.go`). It covers agent jobs (`report_agent_job_cost`), not PA.
- ADR 0011 (`docs/adr/0011-personal-assistant.md`) lists telemetry as part of stage 3 (private
  pilot) and depends on the #1092 ledger; redaction is enforced by `internal/audit/redact.go`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/agent-worker-pa-preview/values.yaml`: image tag
  `main-c74249b`, `AGENT_RUNNER=openai`, `AGENT_PA_STREAMING=true`,
  `AGENT_MODEL=zai-org/GLM-5.3-Flash`, base URL a Cloudflare AI Gateway `custom-nebius` route,
  `AGENT_OPENAI_MAX_OUTPUT_TOKENS=16384`, `MODEL_INPUT_USD_PER_MTOK=0.15`,
  `MODEL_OUTPUT_USD_PER_MTOK=0.50` (described there as shadow prices). No price version exists.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`: tag `main-c74249b`,
  `PA_ENABLED=true`, `PA_STREAMING_ENABLED=true`, `PA_EXTERNAL_TOOLS_ENABLED=true`,
  `PA_WRITES_ENABLED=false`.
- `mctl_get_service_status(labs, agent-worker-pa-preview)`: Argo CD Synced/Healthy, image
  `main-c74249b`. The issue's evidence cites `main-0ef3857`; the tag has moved since.
- Loki logs were not re-queried; the issue's single sample (job 13, ~14s wall clock) is taken as
  given and is not an SLO.

## Proposed solution

Observational only: every new value is recorded alongside the existing flow; no existing
decision reads it.

### 1. Provider response parsing (worker)
- Extend `ChatUsage` with optional detail fields decoded as pointers so "absent" survives:
  `PromptTokensDetails *struct{ CachedTokens *int }` and
  `CompletionTokensDetails *struct{ ReasoningTokens *int }`. `Prices.Cost` and the
  `UsageReported` rule are unchanged, so budget math is byte-for-byte the same.
- Decode the response `model` (non-streaming body and first stream chunk that carries it) into
  `ChatResult.ResponseModel string`, capped at 128 bytes and restricted to a printable
  `[A-Za-z0-9._:/@-]` charset (anything else becomes `invalid`), since it is provider-supplied.

### 2. Per-call and per-run records (worker, new `internal/agentworker/pausage.go`)
- `PACallUsage{Seq, ProviderAttempt, ConfiguredModel, ReturnedModel, ModelMatch
  (exact|alias|unknown), Outcome (ok|provider_rate_limit|provider_server|provider_request|
  provider_error|timeout), FinishReason (clamped to stop|length|tool_calls|content_filter|other|
  none), InputTokens/OutputTokens/CachedTokens/ReasoningTokens *int, Usage
  (reported|unknown|not_returned), CostUSD *float64}`.
- `PARunUsage{V:1, ModelCalls, ProviderAttempts, Calls []PACallUsage (cap paMaxUsageCalls =
  paModelAttempts x (PAMaxToolCalls+1)), totals per token field with a `complete` flag per field,
  EstimatedCostUSD *float64, CostBasis, PriceVersion, PriceSource, Truncated bool}`.
- `chat()` appends one record per provider attempt (failed attempts: `Usage=not_returned`,
  no tokens, `CostUSD=nil`, excluded from totals because 429/5xx are not billed by the provider
  semantics the current code already assumes). `run()` keeps the existing `cost`/`costKnown`
  variables untouched; the aggregator is fed in parallel. `EstimatedCostUSD` equals the existing
  `cost` when `costKnown`, otherwise nil and basis `unknown` (partial known calls still listed).
- Pricing provenance from new optional env in `openAIClientFromEnv`: `MODEL_PRICE_VERSION`,
  `MODEL_PRICE_SOURCE` (default `unversioned`/empty), `MODEL_PRICING_MODE=token|subscription`
  (default `token`), `AGENT_PROVIDER_LABEL` (default empty). Subscription mode changes only the
  `CostBasis` label; the settlement `cost_usd` is still the list-price estimate.
- One structured log per run (extend `pa worker: job finished`) with `job_id`, `attempt`,
  `model_configured`, `model_returned`, `model_match`, `model_calls`, `provider_attempts`, token
  totals (omitted when not supplied), `cost_usd`, `cost_basis`, `price_version`.

### 3. Transport (additive, backward compatible)
- Add `usage *PARunUsage` (`json:"usage,omitempty"`) to the reply body and to the abandon report.
  Old servers ignore it (lenient `json.Unmarshal` in `handleReply`); new servers treat an absent
  field as "not reported". The summary has fixed fields and a bounded call list (worst case
  well under 16 KiB); `maxReplyBody` is raised by that bound so a maximal answer plus summary
  cannot hit the overflow path that drops `cost_usd`. A test pins this.
- On the abandon path, `usage` is accepted even though `cost_usd` is refused with `fail_reason`
  (existing rule kept); it is recorded only.

### 4. Persistence (server, `internal/db/pa_jobs.go`)
- Additive nullable columns on `pa_usage`: `model_configured`, `model_returned`, `model_match`,
  `provider_label`, `model_calls`, `provider_attempts`, `input_tokens`, `output_tokens`,
  `cached_tokens`, `reasoning_tokens`, `estimated_cost_usd`, `cost_basis`, `price_version`,
  `price_source`, `usage_consistent`, `usage_reported_at_ms`. Absent stays NULL.
- New table `pa_usage_calls(job_id, attempt, seq, provider_attempt, outcome, finish_reason,
  model_returned, model_match, usage, input_tokens, output_tokens, cached_tokens,
  reasoning_tokens, cost_usd, UNIQUE(job_id, attempt, seq))`. No principal column, no text.
- New `RecordPAUsage(ctx, tx, ref, summary)` called inside the existing `FinishPAJob` /
  abandon transaction after the settle update, touching only the new columns/table. Idempotency:
  if `usage_reported_at_ms` is already set, an identical summary is a no-op and a different one
  is ignored and counted (`conflict`). It never modifies `status`, `cost_usd`,
  `reported_cost_usd` or `reserved_usd`.
- Reconciliation: `usage_consistent = (estimated_cost_usd == cost_usd reported within 1e-9)
  AND (sum of call costs == estimated_cost_usd)`; inconsistency logs
  `pa usage inconsistent` with `job_id`, `attempt` only. Settled ledger cost remains
  `jobs.Settle` output; the difference between `reported_cost_usd`, `estimated_cost_usd` and
  `cost_usd` (settled, incl. floor and full-reservation-on-unknown) is documented as
  "reported vs. accounted" rather than reconciled away.
- Account deletion: the existing principal purge of `pa_usage` deletes `pa_usage_calls` by
  `(job_id, attempt)` join first.

### 5. Metrics (server, `internal/metrics/pa.go`)
Emitted once per first persisted summary (so duplicates do not double count):
- `mctl_pa_model_calls_total{provider, model, outcome}`
- `mctl_pa_model_tokens_total{kind=input|output|cached|reasoning, model}` (only supplied fields)
- `mctl_pa_cost_usd_total{model, basis}` and `mctl_pa_run_cost_usd{basis}` histogram
- `mctl_pa_model_match_total{match}`, `mctl_pa_usage_missing_total{field}`,
  `mctl_pa_usage_reports_total{result=recorded|duplicate|conflict|malformed|absent}`
`model` uses `Registry.UsageModel(m, true)` (PA reports always come with the pool job token, the
managed path); `provider` is clamped by a new `UsageProvider` with the same bounded-slot logic.
Closed label sets are exported like `PAFailureReasons` with a test keeping them equal to the
`pa` constants. Example PromQL for cost per run and token aggregates goes into
`docs/agent-worker.md`.

### 6. Documentation
`docs/agent-worker.md` gains a "PA usage telemetry" section: fields, missing-data semantics (null,
never zero), cost bases, price provenance env vars, reconciliation and the guarantee that budget
controls do not read telemetry. New field names are checked against `internal/audit/redact.go`.

## Alternatives
- Reuse `report_agent_job_cost` / `mctl_agent_usage_*` for PA. Dropped: that path settles the
  agent-job ledger (`internal/db/agent_usage.go`) with its own credential rules; feeding PA into
  it would mix two ledgers and risk double counting against ADR 0008 budgets.
- Per-call reporting from the worker at each `/turn`. Dropped: adds a write per model call on the
  admission path that budget and fencing depend on, and partial runs would need extra
  reconciliation; a single end-of-run summary keyed by the existing `(job_id, attempt)` is
  naturally idempotent.
- Worker-side Prometheus metrics only. Dropped: the PA worker is pooled and short-lived per job,
  scrape gaps would lose runs, and run totals could not be joined with the `pa_usage` ledger.
- Price cached/reasoning tokens with new rates now. Dropped: would change `cost_usd` and thus
  settlement and the cost-limit check, which the issue forbids for telemetry.

## Platform impact
- Migrations: additive nullable columns and one new table via the existing `CREATE ... IF NOT
  EXISTS` / `ALTER TABLE ADD COLUMN` pattern in `internal/db`, SQLite and Postgres. No backfill;
  existing rows read as "not reported".
- Compatibility: new worker + old server ignores `usage`; old worker + new server records
  `absent`. Mixed rollout is safe in either order.
- Resource impact: at most ~40 small rows per run in `pa_usage_calls`; a handful of new series
  bounded by 16 models x small provider and outcome sets.
- Risks and mitigations:
  - Leakage: provider `model` string is sanitized and bounded; no text/arguments/ids enter
    records; a redaction test inspects metrics output and log attributes.
  - Budget regression: tests assert identical `reported_cost_usd`, `cost_usd`, window sums and
    worker outcomes with and without the summary, and with a malformed summary.
  - Reply overflow: body limit raised by the summary's bound, pinned by a test.
  - Cardinality: `UsageModel`/`UsageProvider` bounded slots, closed sets elsewhere.
- Rollout: none in this proposal (HOLD). Deployment and enabling on preview need a separate GO.
