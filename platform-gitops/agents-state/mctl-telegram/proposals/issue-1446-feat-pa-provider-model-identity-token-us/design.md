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
decision reads it, and a failure to record it changes no existing outcome. The telemetry fields
are separate, nullable observational fields; `ChatUsage` as budget input, `Prices.Cost` and
`UsageReported` keep their current semantics.

### 1. Provider response parsing (worker)
- Extend `ChatUsage` with optional detail fields decoded as pointers so "absent" survives:
  `PromptTokensDetails *struct{ CachedTokens *int }` and
  `CompletionTokensDetails *struct{ ReasoningTokens *int }`. `Prices.Cost` and the
  `UsageReported` rule are unchanged, so budget math is byte-for-byte the same.
- Decode the response `model` (non-streaming body and first stream chunk that carries it) into
  `ChatResult.ResponseModel string`, capped at 128 bytes and restricted to a printable
  `[A-Za-z0-9._:/@-]` charset (anything else becomes `invalid`), since it is provider-supplied.
  The configured `AGENT_MODEL` goes through the same sanitizer before it is written to a record,
  log line or metric label: configuration is trusted for routing, not for log safety.
- Model match: `exact` when the sanitized strings are equal; `verified_alias` only when the
  pair appears in `AGENT_MODEL_ALIASES` (trusted deployment configuration, parsed and sanitized
  at start-up, invalid entries refuse start-up); `mismatch` for any other returned string;
  `unknown` when the provider returned none, or when either side sanitized to `invalid` (a configured `AGENT_MODEL` that sanitizes to `invalid` also refuses start-up, so the two can never match as `exact`). A provider can never
  promote itself to `verified_alias`.

### 2. Per-call and per-run records (worker, new `internal/agentworker/pausage.go`)
- `PACallUsage{Seq, ProviderAttempt, ConfiguredModel, ReturnedModel, ModelMatch
  (exact|verified_alias|mismatch|unknown), Outcome (ok|provider_rate_limit|provider_server|
  provider_request|provider_error|timeout|interrupted), FinishReason (clamped to stop|length|
  tool_calls|content_filter|other|none), InputTokens/OutputTokens/CachedTokens/ReasoningTokens
  *int (each independently nil when not supplied), Usage (reported|unknown|not_returned),
  Billing (estimated|verified|unknown), EstimatedCostUSD *float64}`.
- `PARunUsage{V:1, ModelCalls, ProviderAttempts, Calls []PACallUsage (cap paMaxUsageCalls =
  paModelAttempts x (PAMaxToolCalls+1)), totals per token field with a `complete` flag per field,
  EstimatedCostUSD *float64, EstimateBasis (estimated_list|subscription_shadow|unknown),
  BilledCostUSD *float64 (verified_billed only; nil until verified evidence exists),
  CostCompleteness (complete|partial|unknown), PriceVersion, PriceSource, Truncated bool}`.
  The settled ledger cost is not part of the summary: it stays `pa_usage.cost_usd`, computed by
  `jobs.Settle` as today.
- `chat()` appends one record per provider attempt. A failed or interrupted attempt gets
  `Usage=not_returned`, no tokens, `EstimatedCostUSD=nil` and `Billing=unknown`: the request may
  have reached the provider, and nothing in an OpenAI-compatible error says whether it was
  billed. It is excluded from token totals, and it makes `CostCompleteness` at best `partial`.
  Only verified provider evidence (none is known today) could set it otherwise. `run()` keeps the
  existing `cost`/`costKnown` variables untouched; the aggregator is fed in parallel.
  `EstimatedCostUSD` equals the existing `cost` when `costKnown`, otherwise nil and basis
  `unknown` (partial known calls still listed).
- Pricing provenance from new optional env in `openAIClientFromEnv`: `MODEL_PRICE_VERSION`,
  `MODEL_PRICE_SOURCE` (default `unversioned`/empty), `MODEL_PRICING_MODE=token|subscription`
  (default `token`), `AGENT_PROVIDER_LABEL` (default empty), `AGENT_MODEL_ALIASES` (default
  empty). Subscription mode changes only the `EstimateBasis` label to `subscription_shadow`; the
  settlement `cost_usd` is still the list-price estimate, and the shadow estimate is documented
  as not billed spend.
- One structured log per run (extend `pa worker: job finished`) with `job_id`, `attempt`,
  `model_configured`, `model_returned`, `model_match`, `model_calls`, `provider_attempts`, token
  totals (omitted when not supplied), `cost_usd`, `estimate_basis`, `cost_completeness`,
  `price_version`. Model fields are the sanitized values.

### 3. Transport (additive, explicitly negotiated)
- Capability negotiation: the claim response gains `usage_telemetry: 1` (the summary version the
  server accepts). The worker adds `usage *PARunUsage` (`json:"usage,omitempty"`) to the reply
  body and to the abandon report only when the claim advertised a version it supports. An old
  server (no field) or an unknown version gets the legacy payload, byte-identical to today's.
  Relying on old servers' lenient decoding alone is not enough, because a usage field could push
  a legacy-size answer over the old body limit. A new server treats an absent field as "not
  reported".
- Answer-size semantics are unchanged. Every headroom-aware server replica reads every reply
  and abandon body, whatever its own advertisement switch says, with an outer transport limit of `maxReplyBody + paUsageReadHeadroom`, where
  `paUsageReadHeadroom` is strictly larger than `paUsageMaxBytes` plus the JSON wrapper overhead
  (`,"usage":` and whitespace), so that a maximal accepted answer plus a maximal valid `usage`
  always fits, and an oversized `usage` can still be read far enough to be identified, skipped and
  counted as `oversized` rather than truncating the request. The server decodes `usage` as a
  separate raw field, measures it on its own against `paUsageMaxBytes`, and then applies today's
  `maxReplyBody` rule to the remaining reply payload exactly as if the `usage` field were absent:
  an answer accepted today is accepted, an answer that overflows today overflows the same way,
  and its `cost_usd` is handled as today. An oversized or malformed `usage` is dropped and
  counted, never affecting the reply. A body above the outer limit is handled by today's overflow
  rule; the headroom only ever adds room, it never lowers the limit an answer sees today.
- On the abandon path, `usage` is accepted even though `cost_usd` is refused with `fail_reason`
  (existing rule kept); it is recorded only.

### 4. Persistence (server, `internal/db/pa_jobs.go`)
- Additive nullable columns on `pa_usage`: `model_configured`, `model_returned`, `model_match`,
  `provider_label`, `model_calls`, `provider_attempts`, `input_tokens`, `output_tokens`,
  `cached_tokens`, `reasoning_tokens`, `estimated_cost_usd`, `estimate_basis`,
  `billed_cost_usd`, `cost_completeness`, `price_version`, `price_source`, `usage_consistent`,
  `usage_reported_at_ms`. Absent stays NULL. The existing `cost_usd` (settled) and
  `reported_cost_usd` columns keep their meaning and are never written by telemetry.
- New table `pa_usage_calls(job_id, attempt, seq, provider_attempt, outcome, finish_reason,
  model_returned, model_match, usage, billing, input_tokens, output_tokens, cached_tokens,
  reasoning_tokens, estimated_cost_usd, UNIQUE(job_id, attempt, seq))`. No principal column, no text.
- Isolation from settlement: new `RecordPAUsage(ctx, ref, summary)` runs after the existing
  `FinishPAJob` / abandon transaction has committed, in its own short transaction under its own
  timeout (`paUsageWriteTimeout`), touching only the new columns/table. The reply response is
  determined by the settlement commit alone; a storage error, timeout or panic in
  `RecordPAUsage` is recovered, counted (`write_failed`) and logged with `job_id` and `attempt`
  only, and cannot roll back or alter the reply, its settlement or its outbox row.
- Fencing and attempt identity: `ref` comes from the verified pa-job token (principal, job,
  attempt, digest), never from the summary. The write is conditional on a settled `pa_usage` row
  for that `(job_id, attempt)`; for a fenced or superseded attempt, or a missing row, it writes
  nothing and counts `refused`. It never creates a ledger row and never bypasses authorization.
- Idempotency: if `usage_reported_at_ms` is already set, an identical summary is a no-op and a
  different one is ignored and counted (`conflict`). It never modifies `status`, `cost_usd`,
  `reported_cost_usd` or `reserved_usd`.
- Known gaps, documented in `docs/agent-worker.md`: a crash between the settlement commit and
  the telemetry write leaves a settled row without telemetry. Such rows are visible by query
  (settled, `usage_reported_at_ms` NULL), but are indistinguishable from runs of legacy workers
  or non-negotiated servers, so the doc reports them as "telemetry missing", not as zero usage.
  Metrics are emitted after the telemetry commit, so a crash between the two loses the metric
  increment while the row exists: metrics are a lower bound, the DB is the reference.
- Reconciliation: `usage_consistent = (estimated_cost_usd == cost_usd reported within 1e-9)
  AND (sum of call costs == estimated_cost_usd)`; inconsistency logs
  `pa usage inconsistent` with `job_id`, `attempt` only. Settled ledger cost remains
  `jobs.Settle` output; the difference between `reported_cost_usd`, `estimated_cost_usd` and
  `cost_usd` (settled, incl. floor and full-reservation-on-unknown) is documented as
  "reported vs. accounted" rather than reconciled away.
- Account deletion: the principal purge deletes `pa_usage_calls` and `pa_usage` in one
  transaction that first locks the principal's `pa_usage` rows (`SELECT ... FOR UPDATE` on
  Postgres; SQLite serialises writers). `RecordPAUsage` writes `pa_usage` and its
  `pa_usage_calls` rows in one transaction that takes the same row lock and re-checks the locked settled `pa_usage` row for that `(job_id, attempt)` (the same row the fencing check uses), so a summary racing the purge either commits before it (and
  is purged) or finds the row gone and writes nothing; no orphan `pa_usage_calls` can remain.

### 5. Metrics (server, `internal/metrics/pa.go`)
Emitted once per first persisted summary (so duplicates do not double count):
- `mctl_pa_model_calls_total{provider, model, outcome}`
- `mctl_pa_model_tokens_total{kind=input|output|cached|reasoning, model}` (only supplied fields)
- `mctl_pa_cost_usd_total{model, basis}` (`basis ∈ {estimated_list, subscription_shadow,
  verified_billed}`), a per-call counter: it adds only calls whose cost is known, so it carries
  no completeness label; run-level completeness is on the histogram and in `pa_usage`) and `mctl_pa_run_cost_usd{basis, completeness}` histogram; the settled
  ledger cost has no new metric
- `mctl_pa_model_match_total{match}` (`exact|verified_alias|mismatch|unknown`),
  `mctl_pa_usage_missing_total{field}`,
  `mctl_pa_usage_reports_total{result=recorded|duplicate|conflict|malformed|oversized|absent|
  not_negotiated|refused|write_failed}`
`model` uses `Registry.UsageModel(m, true)` (PA reports always come with the pool job token, the
managed path); `provider` is clamped by a new `UsageProvider` with the same bounded-slot logic.
Closed label sets are exported like `PAFailureReasons` with a test keeping them equal to the
`pa` constants. Example PromQL for cost per run and token aggregates goes into
`docs/agent-worker.md`.

### 6. Documentation
`docs/agent-worker.md` gains a "PA usage telemetry" section: fields, missing-data semantics (null,
never zero, per field), the four cost notions and completeness, price provenance env vars,
capability negotiation, reconciliation, known crash gaps and metric/DB consistency limits, and
the guarantee that budget controls do not read telemetry. New field names are checked against `internal/audit/redact.go`.

## Alternatives
- Write telemetry inside the `FinishPAJob` settlement transaction (the previous draft). Dropped:
  a telemetry storage error would roll back the settlement and the reply, which makes an
  observational feature able to fail a user-visible run.
- A separate post-reply `usage` route. Considered: it isolates the reply body completely, but the
  run-loop routes check `StillRunning`, so a post-terminal route would need a new
  telemetry-only authorization scope (to be confirmed in code). The negotiated field with a separately applied size rule
  gives the same isolation without a new scope.
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
- Compatibility: a new worker against an old or unknown server sees no capability and sends the
  legacy payload; an old worker against a new server records `absent`. Server rollout is two-step:
  every server replica must be headroom-aware before any of them advertises `usage_telemetry: 1`
  (advertisement is behind its own default-off switch, enabled only after the rollout finished),
  because a claim and its reply can reach different replicas; rollback turns advertisement off
  first, then downgrades. Under that order answer-size and body-overflow behaviour are the same
  in every combination.
- Scope of `oversized`: the worker never sends a `usage` above `paUsageMaxBytes` (it drops the
  field and counts locally), so a conforming worker cannot exceed the outer limit. On the server,
  `oversized` covers a `usage` between `paUsageMaxBytes` and the headroom; a body above
  `maxReplyBody + paUsageReadHeadroom` comes only from a non-conforming client and meets today's
  transport cap, which is deliberate (the outer limit stays a DoS bound).
- Resource impact: at most ~40 small rows per run in `pa_usage_calls`; a handful of new series
  bounded by 16 models x small provider and outcome sets.
- Risks and mitigations:
  - Leakage: provider `model` string is sanitized and bounded; no text/arguments/ids enter
    records; a redaction test inspects metrics output and log attributes.
  - Budget regression: tests assert identical `reported_cost_usd`, `cost_usd`, window sums and
    worker outcomes with and without the summary, and with a malformed summary.
  - Reply overflow: today's `maxReplyBody` rule is applied to the reply as if `usage` were
    absent, and `usage` has its own bound, pinned by tests.
  - Telemetry failure reaching settlement: post-commit, separately bounded write with
    fault-injection tests.
  - Shadow estimates read as spend: the `subscription_shadow` basis and completeness labels.
  - Cardinality: `UsageModel`/`UsageProvider` bounded slots, closed sets elsewhere.
- Rollout: none in this proposal (HOLD). Deployment and enabling on preview need a separate GO.

## Verification tiers

tasks.md splits the tests into two tiers. The rule: anything that protects settlement, budget,
fencing and reply isolation from telemetry failure, security and privacy (redaction, bounded
identifiers, purge), the null-versus-zero contract, or backward compatibility is required
before merge, because a merged worker or server can reach a mixed rollout at once. Checks that
need process-crash orchestration, streaming fault timing, provider-specific evidence or
operational artefacts are required before the pilot GO, because no budget decision reads
telemetry until then.

- Before merge: settlement, budget, fencing and reply unchanged under telemetry storage error,
  timeout and malformed or oversized usage (unchanged status, cost and `paWindowSums`);
  redaction and bounding of configured and returned model identifiers; missing versus zero token
  fields; principal purge; capability negotiation, mixed old/new server and worker, legacy
  payload to old or unknown servers, and unchanged answer-size semantics; idempotency and
  conflicts; basic exact/mismatch/unknown and trusted-config alias classification.
- Before pilot GO: the crash-between-commit fault matrix in depth; partial streamed usage;
  accounting of potentially billed failed attempts; alias verification against the provider
  routes actually used; dashboards coordinated with mctlhq/mctl-telegram#1445 and
  mctlhq/mctl-gitops#3004.
