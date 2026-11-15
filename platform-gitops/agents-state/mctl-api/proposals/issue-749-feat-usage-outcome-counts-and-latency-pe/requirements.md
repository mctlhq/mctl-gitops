# Outcome counts and duration_api_ms percentiles in usage summary buckets

## Context
The model-usage ledger (`internal/usage`) already stores `outcome`,
`api_error_status` and `duration_api_ms` on every row (`usage.Record`,
`internal/usage/types.go`), and the `model_usage_records` table has the
matching columns (`internal/usage/store.go`, `usageSchema`). But
`Store.Summary` (`internal/usage/store.go`) only returns `count`, six token
sums and three cost sums per `Bucket`. So `GET /api/v1/usage/summary` and
`mctl_get_usage_summary` can't say how often a model or stage succeeded or
how long its API calls took.

Future model routing needs per-model, per-task success rate and latency
(follow-up F3 of the mctlhq/.github#184 spike). This proposal adds two things
to each bucket: counts per outcome and `duration_api_ms` p50/p95. Unknown is
kept distinct from zero, the same way the bucket already does for tokens and
cost. A row with no recorded outcome is counted as "unreported", not as a
success or an error. A bucket where no row reported `duration_api_ms` has
null percentiles, not 0.

## User stories
- AS a platform operator I WANT each usage summary bucket to show how many invocations succeeded, errored, were interrupted or had no outcome SO THAT I can see a per-model or per-stage success rate without exporting raw records.
- AS a platform operator I WANT each bucket to show p50 and p95 of `duration_api_ms`, plus how many rows the percentiles came from, SO THAT I can compare latency across models and stages and judge how reliable the figure is.
- AS a future model-routing designer I WANT these figures in the same summary call that already carries tokens and cost SO THAT one read answers cost, success and latency for a task class.

## Acceptance criteria (EARS)
- WHEN `GET /api/v1/usage/summary` is called with any supported `group_by` THE SYSTEM SHALL return, in every bucket, the integer fields `outcome_success_count`, `outcome_error_count`, `outcome_interrupted_count` and `outcome_unreported_count`, each always present (0 is a measured zero).
- WHILE a bucket is returned THE SYSTEM SHALL keep `outcome_success_count + outcome_error_count + outcome_interrupted_count + outcome_unreported_count` equal to the bucket's `count`.
- IF a row's `outcome` column is the empty string THEN THE SYSTEM SHALL count it in `outcome_unreported_count`, never in any of the other three counts.
- WHEN a bucket is returned THE SYSTEM SHALL include `duration_api_ms_reported_count`, the number of rows in the bucket whose `duration_api_ms` is not NULL, always present.
- WHEN at least one row in a bucket has a non-NULL `duration_api_ms` THE SYSTEM SHALL return `duration_api_ms_p50` and `duration_api_ms_p95`, computed over those rows only as discrete percentiles (an observed value, in whole milliseconds).
- IF no row in a bucket has a non-NULL `duration_api_ms` THEN THE SYSTEM SHALL return `duration_api_ms_p50` and `duration_api_ms_p95` as null or absent, never 0.
- WHILE computing percentiles THE SYSTEM SHALL ignore NULL `duration_api_ms` values rather than treating them as 0.
- WHEN the summary filters (`workflow_id`, `run_id`, `model`, `outcome`, `since`, `until`, and the others) are applied THE SYSTEM SHALL compute the new fields over exactly the same rows as `count` and the token/cost sums.
- WHEN `mctl_get_usage_summary` builds its `total` (an untruncated result) THE SYSTEM SHALL sum the four outcome counts and `duration_api_ms_reported_count` across buckets.
- THE SYSTEM SHALL NOT put a duration percentile in `total`, because percentiles cannot be combined from per-bucket percentiles. Instead it SHALL state that bucket percentiles are not aggregable.
- WHILE the result is truncated THE SYSTEM SHALL keep the existing behaviour: no `total`, and `total_unavailable_reason` instead.
- WHEN a summary is requested THE SYSTEM SHALL keep every existing bucket field (`key`, `count`, token and cost fields) unchanged in name, type and semantics, and keep the existing ordering (`COUNT(*) DESC, key ASC`), `truncated`, `truncated_by` and `limit`.

## Out of scope
- Model routing, fallback, or a `modelPolicy.strategy` field (explicitly excluded by the issue; revisit once the ledger shows at least two models per task class).
- A provider-5xx-only fallback profile.
- A per-bucket breakdown by `api_error_status`. Its vocabulary is open, and a fallback profile is the consumer that would define it.
- Latency percentiles other than p50/p95, and other duration columns (there is only `duration_api_ms`).
- A new `group_by` dimension, a new filter, or a schema change / new index on `model_usage_records`.
- Changes to ingest, validation or producers (mctl-agents).

## Open questions
- `duration_api_ms` grain: a run that spans two models produces two records (`usage.Record` doc comment). The SDK's `duration_api_ms` is reported on the ResultMessage, so it may be the whole run's API time, copied onto each per-model row. If so, a per-model p95 overstates each model's latency for multi-model runs. This proposal reports the column as stored and documents the caveat. Whether producers should split it per model is a producer question for mctl-agents.
- Field naming: this proposal uses flat fields (`outcome_*_count`, `duration_api_ms_p50/p95/_reported_count`), consistent with the existing flat bucket shape and the MCP total-summing code. A nested `outcomes` object would also work; flat was chosen.
- Live data could not be observed (the read of `/api/v1/usage/summary` was refused for this agent run). How many rows actually carry `outcome` and `duration_api_ms` today is unknown, so the share of "unreported" is not yet known.
