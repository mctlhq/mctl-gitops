# PA provider model identity, token usage and cost accounting telemetry

## Context
The Personal Assistant (PA) worker (`internal/agentworker/parunner.go`) makes one or more
OpenAI-compatible model calls per run and reports a single `cost_usd` figure on
`POST /api/pa/v1/jobs/reply`. The server settles that figure against a per-attempt
reservation in `pa_usage` (`internal/db/pa_jobs.go`, `jobs.Settle`). Today nothing records which
model actually answered, how many tokens each call used (input, output, cached, reasoning), how
many provider attempts were made, on which price the estimate rests, or whether the figure is
estimated, unknown or subscription-backed. Phase 3 telemetry (#1324, under epic #1312, ADR 0011
pilot stage "telemetry") needs this to judge pilot cost and provider behaviour.

The issue asks for a PA-specific, observational telemetry contract: capture configured vs.
returned model identity, token counts only when supplied, attempts and finish/error status, and
per-call and per-run cost with explicit provenance, reconciled with the existing reservation
ledger without double counting, and without changing authorization, budget or fencing behaviour
and without collecting prompt/response text, credentials or principal identifiers in metrics.
The issue is marked planning only / implementation HOLD: this proposal is a plan; it authorizes
no deployment, live provider call or pilot GO.

## User stories
- AS the platform owner I WANT the cost of each PA run and model call, with its price source
  and basis SO THAT I can judge pilot spend without mistaking unknown spend for zero.
- AS an operator I WANT bounded metrics by provider, model and outcome SO THAT I can see
  provider errors, retries and model aliasing without high-cardinality series.
- AS an operator I WANT the worker and server log lines of one run to share a correlation key
  SO THAT I can follow a run's usage from worker to settlement.
- AS a security reviewer I WANT tests proving that no prompt, response text, credential or
  principal identifier reaches metrics or the new log fields SO THAT telemetry cannot leak
  private Telegram data.
- AS the budget owner I WANT the reservation, settlement and cost-limit behaviour proven
  unchanged SO THAT telemetry cannot weaken budget controls.

## Acceptance criteria (EARS)
- WHEN the provider returns a chat completion THE SYSTEM SHALL record, per model call, the
  configured model (`AGENT_MODEL`), the model string the provider returned (or `unknown` when
  absent), and a match class of `exact`, `alias` or `unknown`.
- WHEN the provider's `usage` object supplies `prompt_tokens`, `completion_tokens`,
  `prompt_tokens_details.cached_tokens` or `completion_tokens_details.reasoning_tokens` THE
  SYSTEM SHALL record each supplied field, and IF a field is absent THEN THE SYSTEM SHALL record
  it as not supplied (null), never as zero.
- IF the provider omits `usage` or reports zero tokens in both directions THEN THE SYSTEM SHALL
  mark that call's usage and cost as `unknown` (preserving today's `UsageReported=false` rule).
- WHEN a provider attempt fails with 429 or 5xx and is retried THE SYSTEM SHALL record the
  attempt with its error class and with usage `not_returned`, and SHALL NOT add it to the run's
  token or cost totals.
- WHEN a run ends (reply, abandon, cost limit, tool cap, timeout or provider error) THE SYSTEM
  SHALL produce one run usage summary containing the model call count, provider attempt count,
  per-call records, token totals over supplied fields, the estimated cost, the cost basis and
  the price version.
- THE SYSTEM SHALL label every cost with exactly one basis: `estimated_list` (tokens x configured
  list price), `measured_billed` (a provider-billed amount, only when one is supplied),
  `subscription` (flat-fee pricing mode) or `unknown`.
- THE SYSTEM SHALL label every estimated cost with the configured price version and source; IF
  no version is configured THEN THE SYSTEM SHALL use the literal version `unversioned`.
- WHEN the server receives a run usage summary THE SYSTEM SHALL persist it against the existing
  `pa_usage` row of that `(job_id, attempt)` and its per-call records keyed by
  `(job_id, attempt, seq)`, so that a repeated report of the same run is idempotent and a
  conflicting repeat is ignored and counted.
- WHEN the server persists a run summary THE SYSTEM SHALL check that the sum of known per-call
  costs equals the reported `cost_usd` (within 1e-9) and record `usage_consistent`; IF they
  disagree THEN THE SYSTEM SHALL log a warning keyed by job id and attempt and SHALL settle
  exactly as it does today.
- WHILE telemetry is recorded THE SYSTEM SHALL compute the reservation, `jobs.Settle`, the
  worker's cost-limit check (`errPACostLimit`), the tool cap, the turn admission and the
  fencing checks exactly as before; telemetry fields SHALL NOT be read by any of them.
- IF the usage summary is malformed or exceeds its bound THEN THE SYSTEM SHALL drop the summary,
  count the drop, and still accept the reply and its `cost_usd` as today.
- THE SYSTEM SHALL expose PA usage metrics whose labels come only from closed sets or from the
  bounded `Registry.UsageModel` / provider sets, and SHALL NOT use job ids, principal ids,
  Telegram ids, message text or prompts as label values.
- THE SYSTEM SHALL emit a worker log line per run and a server log line per settlement carrying
  `job_id`, `attempt`, model identity, token totals, cost, basis and price version, and SHALL NOT
  carry message text, prompts, tool arguments, credentials or principal/Telegram identifiers.
- WHEN account deletion purges a principal's PA data THE SYSTEM SHALL also delete that
  principal's per-call usage records.
- WHEN CI runs THE SYSTEM SHALL execute fake-provider tests only; no test SHALL make a live
  provider call or deployment.

## Out of scope
- A billing system, invoicing, provider billing API integration or new provider integrations.
- Changing budgets, reservation amounts, `jobs.SettleFactor`, `PA_MIN_TURN_COST_USD`, the
  worker's cost-limit rule or any authorization/consent/fencing rule.
- Pricing cached or reasoning tokens differently from today's two-rate estimate (they are
  recorded, not separately priced, in this proposal).
- Dashboards and alert rules beyond a documented example query (follow-up under #1324).
- The non-PA agent job accounting path (`internal/agentapi` `report_agent_job_cost`,
  `mctl_agent_usage_*`), which stays as is.
- Distributed tracing (OpenTelemetry spans); correlation is by `job_id` + `attempt`.
- Enabling anything in deployed environments; that needs a separate owner GO.

## Open questions
- Price provenance: what string should identify a price version (e.g. a date plus provider
  price page URL)? Proposed: two new optional env vars `MODEL_PRICE_VERSION` and
  `MODEL_PRICE_SOURCE`; `unversioned` when unset.
- Subscription-backed usage: no PA deployment is known to be subscription-backed today
  (preview uses per-token Nebius via Cloudflare AI Gateway). Proposed: `MODEL_PRICING_MODE`
  (`token` default, `subscription`); in subscription mode the worker still sends the same
  list-price `cost_usd` for settlement so budgets are unchanged, and telemetry labels it
  `subscription`.
- Measured billed amounts: the OpenAI-compatible responses observed here carry no billed
  amount. `measured_billed` is defined but only populated if a provider field is identified
  later; until then it never appears.
- Whether per-call records should be retained as long as `pa_usage` rows or pruned earlier;
  proposed: same lifetime and same purge as `pa_usage`.
- Provider label: proposed as a bounded label derived from a new optional `AGENT_PROVIDER_LABEL`
  env var, clamped server-side to a small bounded set (`unknown` when unset).
- Runtime evidence cited in the issue (`main-0ef3857`) differs from the image tag observed now
  (`main-c74249b`); this does not change the design.
