# Spike #917: Does verified Claude Ultra remove the session bottleneck for sustained DevLoop throughput, and how should subscription quota vs usage-credit spend be modeled?

## Context

DevLoop's agent stages (issue-investigator, implementer, shepherd, incident
responder, service agents, mentor) authenticate to Claude through a single
subscription OAuth token (`CLAUDE_CODE_OAUTH_TOKEN`, resolved by
`orchestrator/auth.py:detect_auth`, which prefers OAuth over an API key). When
the account's quota is exhausted, the SDK ends the run with a 429 and
`orchestrator/rate_limit.py` classifies it, carrying the SDK's
`rate_limit_type` (`five_hour`, `seven_day`, ...), `resets_at` and
`overage_disabled_reason` into a `RateLimitObservation`. Anthropic documents
that a **verified** Ultra account has no five-hour session limit but keeps a
weekly limit across all models plus a separate weekly limit for Fable, and
that optional usage credits can continue work after included limits at
consumption pricing. The issue asks whether that change materially increases
sustained DevLoop throughput before a weekly limit binds, and how MCTL should
represent included subscription quota versus usage-credit spend.

This matters because capacity planning for DevLoop waves (`mctl_start_epic_wave`
starts several investigators at once) assumes a quota shape that may no longer
hold, and because ADR-012 (`docs/adr/012-model-usage-cost-attribution-contract.md`)
already defines that the SDK's `costUSD` / `total_cost_usd` is a
`calculated_cost` list-price estimate, never `provider_reported_cost`. A new
billing bucket (usage credits) must not blur that distinction. The deliverable
is a spike report with exactly one recommendation from
`NO_MATERIAL_CAPACITY_CHANGE | UPDATE_SUBSCRIPTION_CAPACITY_MODEL |
UPDATE_CAPACITY_AND_USAGE_CREDIT_MODEL`, plus the minimum read-only tooling
needed to produce its evidence. No runtime behaviour of DevLoop changes.

## User stories

- AS a platform operator I WANT a measured subscription-limit model for the
  DevLoop OAuth account SO THAT I can size epic waves without guessing from
  vendor headline ratios.
- AS a FinOps reviewer I WANT included subscription consumption, list-price
  estimates and actual usage-credit spend kept in distinct buckets SO THAT no
  estimate is ever read as a provider invoice.
- AS a DevLoop maintainer I WANT to know which weekly limit (all-models or
  Fable) binds for the current model mix SO THAT model-policy changes are
  judged against the real constraint.
- AS a reviewer of this spike I WANT exactly one recommendation backed by
  normalized before/after evidence SO THAT follow-up work is filed only for
  proven gaps.

## Acceptance criteria (EARS)

- WHEN the spike report `docs/spikes/917-claude-ultra-capacity.md` is
  published THE SYSTEM SHALL state exactly one outcome from
  `NO_MATERIAL_CAPACITY_CHANGE`, `UPDATE_SUBSCRIPTION_CAPACITY_MODEL`,
  `UPDATE_CAPACITY_AND_USAGE_CREDIT_MODEL`, or `STATUS: PENDING_EVIDENCE`
  until the owner records that outcome.
- WHEN the report describes the tested account THE SYSTEM SHALL record the
  plan tier, whether the account is verified (or "not observed"), the
  credential path (`CLAUDE_CODE_OAUTH_TOKEN` vs `ANTHROPIC_API_KEY` vs CLI
  session, per `orchestrator/auth.py`), and the account label from
  `orchestrator/rate_limit.py:account_label`, and never any token value.
- WHEN the capacity analysis script is run over a measurement window THE
  SYSTEM SHALL report, per window, completed DevLoops and agent stages per
  hour and per day, count and wall-clock time lost to 429 rejections grouped
  by `rate_limit_type`, and the model/effort mix per stage.
- WHEN a rate-limit rejection is observed THE SYSTEM SHALL attribute it to
  the `rate_limit_type` the SDK reported, and IF the type is absent THEN THE
  SYSTEM SHALL report it as `unknown`, never as `five_hour` or `seven_day`.
- WHILE comparing pre-change and verified-Ultra windows THE SYSTEM SHALL
  normalize throughput by workload (agent stage, model, task complexity
  proxy such as turns and output tokens) and SHALL NOT compare raw run counts
  across windows with different stage mixes.
- WHILE reporting cost THE SYSTEM SHALL present SDK `costUSD` /
  `total_cost_usd` only as `calculated_cost` (list-price estimate, with its
  `pricing_version`), SHALL keep `provider_reported_cost` null for included
  subscription usage, and SHALL label usage-credit spend as a separate bucket
  sourced only from the provider's own billing surface.
- IF usage credits are not enabled on the tested account THEN THE SYSTEM
  SHALL record the usage-credit path as "unmeasured" and SHALL NOT enable
  credits to complete the spike.
- IF usage credits are enabled THEN THE SYSTEM SHALL cross the included-quota
  boundary only inside a bounded test with a pre-agreed spend cap, and SHALL
  record included-plan consumption and usage-credit spend separately.
- WHEN the report estimates the weekly bottleneck THE SYSTEM SHALL name which
  limit binds first for the measured model mix (all-models weekly vs Fable
  weekly), or state that the binding limit could not be observed.
- WHEN warning or refusal behaviour near a weekly limit is observed THE
  SYSTEM SHALL record the SDK `RateLimitEvent` status (`allowed`,
  `allowed_warning`, `rejected`), its `rate_limit_type` and `resets_at`, and
  the run's wrap-up behaviour (clean stop, partial commit, retry).
- WHILE the spike runs THE SYSTEM SHALL NOT change DevLoop runtime behaviour,
  credentials, approval gates, model policy or authority, and SHALL NOT draw
  any shared-account or tenant-pooling conclusion.
- IF a measurement source (usage ledger, workflow logs, provider usage page)
  is unavailable THEN THE SYSTEM SHALL record it as "not observed" with the
  reason, never as zero or absent.

## Out of scope

- Treating Ultra as an API billing replacement or moving production to
  `ANTHROPIC_API_KEY`.
- General Anthropic plan benchmarking beyond the DevLoop workload.
- Enabling usage-credit spend just to complete the spike.
- Any change to `orchestrator/auth.py`, `orchestrator/rate_limit.py` runtime
  behaviour, `config/model-policy.yaml`, retry/backoff logic or the
  secondary-token rotation.
- Implementing the capacity-model or usage-credit-ledger changes the outcome
  may recommend; those are follow-up issues filed only for proven gaps.
- Tenant-level or shared-account capacity conclusions.

## Open questions

- Whether the account behind `platform/mctl-agents#claude-code-oauth-token`
  is on Ultra and verified is not observable from the repo, gitops or the
  read-only mctl tools. The report must record it from the account owner;
  until then the outcome stays `PENDING_EVIDENCE`.
- Whether usage credits are enabled on that account is not observable here.
  Default assumption: not enabled, so the usage-credit path is "unmeasured".
- Whether the SDK pinned at `claude-agent-sdk==0.2.136` reports a distinct
  `rate_limit_type` for the Fable weekly limit (as opposed to a generic
  `seven_day`) is unknown; if it does not, the binding weekly limit can only
  be inferred from the provider's usage page, and the report must say so.
- Weekly remaining percentage is not exposed in the SDK stream today
  (`RateLimitObservation` has no utilization field); whether
  `RateLimitEvent.rate_limit_info` carries a utilization value on this SDK
  version must be checked during the experiment.
- Pre-change baseline depth depends on what `.status.yaml` `rate_limited`
  entries, the usage ledger (`mctl_get_usage_summary`) and archived Argo logs
  still retain; retention may cap the "before" window.
- Which model mix DevLoop actually uses: `config/model-policy.yaml` only
  defines Haiku and Sonnet profiles, while the investigator and implementer
  take their model from env (`ISSUE_INVESTIGATOR_MODEL`, defaulting to
  `SERVICE_AGENT_MODEL`). Whether any stage runs Fable in production must be
  read from usage-ledger `canonical_model` buckets, not assumed.
