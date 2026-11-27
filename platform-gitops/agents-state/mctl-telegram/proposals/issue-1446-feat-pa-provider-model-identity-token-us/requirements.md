# PA provider model identity, token usage and cost accounting telemetry

## Revision 2026-11-27

This revision applies the review amendment register (https://github.com/mctlhq/mctl-telegram/issues/1446#issuecomment-7229399420) and its correction (https://github.com/mctlhq/mctl-telegram/issues/1446#issuecomment-7229485928). Implementation HOLD stays in force; this revision is not an approval and needs a fresh review and digest.

- Telemetry is isolated from settlement: the usage write runs after the `FinishPAJob` commit as a separately bounded best-effort write, so a telemetry storage or transport failure cannot roll back the reply or change settlement, budget, authorization, fencing or delivery.
- Cost is split into estimated, verified billed, existing settled and unknown. Subscription-backed shadow estimates are labelled as estimates, never as billed spend. Failed or interrupted provider attempts keep billing `unknown`.
- Model match classes are `exact`, `verified_alias` (trusted configuration only), `mismatch` and `unknown`. Configured and returned identifiers are bounded and sanitized before logs and metrics.
- The worker sends extended usage only after explicit capability negotiation; an old or unknown server gets the legacy payload. Accepted answer-size and body-overflow semantics are unchanged; telemetry is bounded separately.
- Verification is split into "required before merge" and "required before pilot GO" tiers (tasks.md). Gates referenced: ADR 0011 and mctlhq/mctl-telegram#1319 (mctlhq/mctl-telegram#1317 is closed and met).

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
  absent), and a match class of `exact`, `verified_alias`, `mismatch` or `unknown`.
- THE SYSTEM SHALL classify a returned model as `verified_alias` only when the pair is listed in
  trusted deployment configuration (`AGENT_MODEL_ALIASES`), never from the provider response
  alone; any other differing string is `mismatch`.
- WHILE a configured or returned model identifier is written to a record, log line or metric
  label THE SYSTEM SHALL bound it in length, restrict it to a fixed charset and map anything
  else to `invalid`.
- WHEN the provider's `usage` object supplies `prompt_tokens`, `completion_tokens`,
  `prompt_tokens_details.cached_tokens` or `completion_tokens_details.reasoning_tokens` THE
  SYSTEM SHALL record each supplied field, and IF a field is absent THEN THE SYSTEM SHALL record
  it as not supplied (null), never as zero. Input, output, cached and reasoning fields SHALL be
  null or present independently of each other; a supplied zero SHALL stay zero.
- IF the provider omits `usage` or reports zero tokens in both directions THEN THE SYSTEM SHALL
  mark that call's usage and cost as `unknown` (preserving today's `UsageReported=false` rule).
- WHEN a provider attempt fails (429, 5xx, timeout, transport error) or is interrupted THE
  SYSTEM SHALL record the attempt with its error class, usage `not_returned` and billing
  `unknown`, unless verified provider evidence states otherwise. It SHALL NOT add the attempt to
  the run's token totals, and the run's cost completeness SHALL then be `partial` or `unknown`,
  never `complete`.
- WHEN a run ends (reply, abandon, cost limit, tool cap, timeout or provider error) THE SYSTEM
  SHALL produce one run usage summary containing the model call count, provider attempt count,
  per-call records, token totals over supplied fields, the estimated cost, the cost basis and
  the price version.
- THE SYSTEM SHALL keep four cost notions separate and never merge them: the estimated cost
  (basis `estimated_list`, tokens x configured list price, or `subscription_shadow`, the same
  estimate under flat-fee pricing), the verified billed cost (basis `verified_billed`, only from
  verified provider evidence), the existing settled ledger cost (`pa_usage.cost_usd`, unchanged)
  and `unknown`.
- THE SYSTEM SHALL NOT present a `subscription_shadow` estimate as actual billed spend in any
  record, log line, metric or document.
- WHEN costs are aggregated per run or in metrics THE SYSTEM SHALL label the aggregate's
  completeness as `complete`, `partial` or `unknown`.
- THE SYSTEM SHALL label every estimated cost with the configured price version and source; IF
  no version is configured THEN THE SYSTEM SHALL use the literal version `unversioned`.
- WHEN the server receives a run usage summary THE SYSTEM SHALL persist it against the existing
  `pa_usage` row of that `(job_id, attempt)` and its per-call records keyed by
  `(job_id, attempt, seq)`, so that a repeated report of the same run is idempotent and a
  conflicting repeat is ignored and counted.
- WHEN a run usage summary is persisted THE SYSTEM SHALL write it after the `FinishPAJob` /
  abandon settlement transaction has committed, in a separate, time-bounded best-effort write
  keyed by the `(job_id, attempt)` of the verified pa-job token. IF that write fails or times
  out THEN THE SYSTEM SHALL count the missing telemetry and SHALL NOT roll back, delay beyond the
  bound, or alter the reply, its settlement or its delivery.
- IF a usage summary names a `(job_id, attempt)` with no settled `pa_usage` row, or arrives for a
  fenced or superseded attempt, THEN THE SYSTEM SHALL record nothing and count the refusal; it
  SHALL NOT create a ledger row.
- WHEN the server persists a run summary THE SYSTEM SHALL check that the sum of known per-call
  costs equals the reported `cost_usd` (within 1e-9) and record `usage_consistent`; IF they
  disagree THEN THE SYSTEM SHALL log a warning keyed by job id and attempt and SHALL settle
  exactly as it does today.
- WHILE telemetry is recorded, and also when its persistence or transport fails, THE SYSTEM
  SHALL compute the reservation, `jobs.Settle`, the worker's cost-limit check
  (`errPACostLimit`), the tool cap, the turn admission, authorization and the fencing checks,
  and deliver the reply, exactly as before; telemetry fields SHALL NOT be read by any of them.
- IF the usage summary is malformed or exceeds its own bound THEN THE SYSTEM SHALL drop the
  summary, count the drop, and still accept the reply and its `cost_usd` as today.
- WHEN a worker reports a reply or abandon THE SYSTEM SHALL include the `usage` field only if
  the claim response advertised a usage-telemetry capability version that the worker supports.
  IF the server advertised none or an unknown version THEN THE SYSTEM SHALL send the legacy
  payload unchanged.
- WHILE a reply carries `usage` THE SYSTEM SHALL accept, refuse or overflow the answer and its
  `cost_usd` exactly as the same reply without `usage` would be under today's `maxReplyBody`
  rule, and SHALL bound and validate the `usage` field separately.
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
  worker's cost-limit rule, the reply body-overflow behaviour or any
  authorization/consent/fencing rule.
- Provider calls, implementation, migration execution, deployment or a pilot GO (gates: ADR 0011
  and mctlhq/mctl-telegram#1319).
- Pricing cached or reasoning tokens differently from today's two-rate estimate (they are
  recorded, not separately priced, in this proposal).
- Dashboards and alert rules beyond a documented example query (follow-up under #1324,
  coordinated with mctlhq/mctl-telegram#1445 and mctlhq/mctl-gitops#3004 before the pilot GO).
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
  list-price `cost_usd` for settlement so budgets are unchanged, and telemetry labels the
  estimate `subscription_shadow`, which is not billed spend.
- Verified billed amounts: the OpenAI-compatible responses observed here carry no billed
  amount. `verified_billed` is defined but only populated if a provider field or billing
  evidence is identified and verified later; until then it never appears.
- Alias configuration: proposed as `AGENT_MODEL_ALIASES` (comma-separated
  `configured=returned` pairs) set in deployment values; which aliases the current provider
  route needs is unknown until a pre-pilot check.
- Whether per-call records should be retained as long as `pa_usage` rows or pruned earlier;
  proposed: same lifetime and same purge as `pa_usage`.
- Provider label: proposed as a bounded label derived from a new optional `AGENT_PROVIDER_LABEL`
  env var, clamped server-side to a small bounded set (`unknown` when unset).
- Runtime evidence cited in the issue (`main-0ef3857`) differs from the image tag observed now
  (`main-c74249b`); this does not change the design.
