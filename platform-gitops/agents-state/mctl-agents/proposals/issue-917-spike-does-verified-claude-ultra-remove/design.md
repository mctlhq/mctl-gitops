# Design: issue-917-spike-does-verified-claude-ultra-remove

## Current state

**Credential path.** `orchestrator/auth.py:detect_auth` selects the Claude
credential from env: `CLAUDE_CODE_OAUTH_TOKEN` (or `_SECONDARY`) wins over
`ANTHROPIC_API_KEY`, falling back to a local `claude` CLI session. Its
docstring still says production uses `ANTHROPIC_API_KEY`, but the deployed
worker uses the OAuth token (see Deployed state below), and ADR-012 records
the 2026-09-11 decision that DevLoop runs on the subscription OAuth token.
`rotate_to_secondary_auth` swaps in a secondary token on a 429.

**Quota-limit evidence.** `orchestrator/rate_limit.py` is the shared
classifier: `is_rate_limit_result` detects a terminal `ResultMessage` with
`api_error_status == 429`; `observe_rate_limit_event` extracts
`RateLimitEvent.rate_limit_info`; `build_observation` produces a
credential-free `RateLimitObservation(account, rate_limit_type, resets_at,
resets_at_epoch, overage_disabled_reason, detail)`. `rate_limit_type` already
distinguishes `five_hour` from `seven_day`; `overage_disabled_reason` (e.g.
`out_of_credits`) is the only usage-credit signal captured today. The
implementer (`orchestrator/run_implementer.py`, around lines 2675-2700 and
3294) writes this observation into `.status.yaml` `rate_limited`. The
investigator (`orchestrator/run_issue_investigator.py:2322`, `:4405`) still
keeps its own inline 429 check and returns `rate_limited=True,
outcome_reason="rate-limit-exhausted"` without the observation payload
(follow-up mctl-agents#455). Non-rejected events (`allowed`,
`allowed_warning`) are observed but discarded: nothing records how close a run
came to a limit.

**Usage and cost.** ADR-012
(`docs/adr/012-model-usage-cost-attribution-contract.md`) defines the record
grain (run, model) and three cost concepts: `provider_reported_cost` (always
null today), `calculated_cost` (SDK `costUSD` / `total_cost_usd` under a
`pricing_version`), `invoice_reconciled_cost` (defined, unused). It states the
billable dimension under a subscription is quota-window consumption, so token
counts are the load-bearing numbers. `orchestrator/usage_ledger.py` emits
records to `POST /api/v1/usage/records` with `provider` and `price_source`
provenance; `orchestrator/run_usage_collector.py` imports reviewer-stage
artifacts (`docs/operations/usage-collector.md`). There is no field or bucket
for usage-credit spend, and no notion of "included quota consumed".

**Model mix.** `config/model-policy.yaml` defines `cheap`
(`claude-haiku-5-5`) and `balanced` (`claude-sonnet-5-5`) profiles for
service agents, mentor, shepherd normalization and scout. The investigator and
implementer take their model from env (`INVESTIGATOR_MODEL =
os.getenv("ISSUE_INVESTIGATOR_MODEL", SERVICE_AGENT_MODEL)` at
`orchestrator/run_issue_investigator.py:126`). Whether any stage runs Fable is
therefore a deployed-env fact, not a repo fact.

**Spike convention.** Prior spikes live as `docs/spikes/<n>-<slug>.md` with a
`STATUS:` line and an owner decision (e.g.
`docs/spikes/854-agent-observability-gaps.md`), with raw artefacts in
`docs/spikes/<n>/` (e.g. `docs/spikes/825/records-candidate.jsonl`,
`run-manifest-candidate.json`).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: the
  Temporal control worker mounts `CLAUDE_CODE_OAUTH_TOKEN` from Vault
  `platform/mctl-agents`, property `claude-code-oauth-token`, commented as "a
  long-lived Pro/Max OAuth token, rotated by hand". No `ANTHROPIC_API_KEY`
  and no `CLAUDE_OAUTH_ACCOUNT` label were found there. The comment also says
  the Argo CronWorkflow pods read the same key via `mctl-agents-secrets`.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker-exec/values.yaml`:
  carries no Claude credential (explicitly MCTL_TOKEN only).
- `$MCTL_GITOPS_ROOT/services/labs/agent-worker-preview/values.yaml` and
  `services/labs/claude-remote/values.yaml` also reference Claude OAuth;
  not read in detail, recorded as other consumers that may share the same
  account (unknown).
- `mctl_get_usage_summary(group_by=canonical_model, since=2026-10-01)`:
  refused, HTTP 403 `agent_scope_denied` (outside this run's investigate
  scope). The actual model mix and per-stage token totals were NOT observed.
- Plan tier, verification status and usage-credit enablement of the account
  behind that Vault key: not observable from any source available to this run.

## Proposed solution

A documentation-and-evidence spike with one small read-only analysis tool. No
DevLoop runtime change.

### 1. Measurement protocol (in the report)

`docs/spikes/917-claude-ultra-capacity.md` opens with `STATUS:
PENDING_EVIDENCE` and fixes the protocol before any data is gathered:

- **Account facts**: plan tier, verified yes/no/not-observed, usage credits
  enabled yes/no/not-observed, credential path from `detect_auth`, account
  label from `account_label()`, and every other known consumer of the same
  OAuth token (control worker, Argo CronWorkflows, labs previews, reviewer
  workflow). Shared consumers matter: they draw on the same weekly quota and
  must be counted, not ignored.
- **Before window**: reconstructed from existing evidence only: `.status.yaml`
  `rate_limited` entries under `platform-gitops/agents-state/*/proposals/*/`,
  investigator `outcome_reason=rate-limit-exhausted` results, archived Argo
  workflow logs (`mctl_get_workflow_logs`), and usage-ledger buckets
  (`mctl_get_usage_summary` grouped by `devloop_stage`, `canonical_model`,
  `outcome`). Its key question is retrospective: how many rejections were
  `five_hour` vs `seven_day` vs unknown, and how much wall-clock they cost.
- **After window**: live runs on the verified Ultra account using
  representative current workloads (investigator, implementer, shepherd
  ticks), back-to-back, long enough to cross at least one would-have-been
  five-hour boundary and, if feasible within the week, reach a weekly
  warning. Each run records stage, model, effort, turns, input/output/cache
  tokens, duration, outcome, retries, and every `RateLimitEvent`
  (`allowed`, `allowed_warning`, `rejected`).
- **Usage-credit boundary**: only if credits are already enabled, a single
  bounded test with an owner-agreed spend cap; otherwise recorded as
  "unmeasured". Credit spend is taken from Anthropic's billing surface, never
  computed from SDK `costUSD`.
- **Normalization**: throughput is reported per stage and per model as
  completed stages per hour/day and as output tokens per hour, so windows
  with different mixes remain comparable. Headline vendor ratios are quoted
  but never used as evidence.

### 2. Read-only analysis script

`tools/spike_917_capacity.py` (pure stdlib, run with `python -I`): reads a
JSONL file of per-run records (exported usage-ledger rows plus rate-limit
observations, schema documented in the report) and a run manifest, and prints:
stages/hour and /day per stage and model; count and summed lost wall-clock of
429 rejections per `rate_limit_type` (missing type reported as `unknown`);
weekly consumption curve where the provider's remaining-percentage was
recorded by hand; and the marginal throughput between the first would-be
`five_hour` boundary and the first weekly warning. It never computes or
outputs a provider-billed figure: cost columns are labelled
`calculated_cost (list-price estimate, pricing_version=...)`. Raw inputs live
in `docs/spikes/917/` with token values and identities excluded.

The script is an evidence tool, not a runtime component: nothing imports it,
and it lives beside the spike so it can be deleted with it.

### 3. FinOps mapping (in the report)

A table that maps each accounting bucket to its ADR-012 field and source:

| Bucket | Meaning | ADR-012 field | Source |
|---|---|---|---|
| Included subscription quota | capacity entitlement, all-models weekly and Fable weekly, consumed as tokens | token counts; no cost field | SDK `usage` / `model_usage`, provider usage page for remaining % |
| List-price estimate | what the tokens would cost at API list price | `calculated_cost` + `pricing_version` | SDK `costUSD` |
| Usage-credit spend | actual consumption-priced charge after included limits | not representable today | provider billing surface only |
| Monthly API credits / Console billing | separate account type, not used by DevLoop | `provider_reported_cost` if ever used | Console billing |

### 4. Decision rule for the single outcome

- `NO_MATERIAL_CAPACITY_CHANGE`: before-window rejections were predominantly
  `seven_day` (or none), or the after window shows the weekly limit binding
  before the removed five-hour window would have, so sustained throughput is
  unchanged.
- `UPDATE_SUBSCRIPTION_CAPACITY_MODEL`: `five_hour` rejections measurably
  bounded throughput before and are gone after, with marginal throughput
  gained before a weekly limit binds; usage credits unused or unmeasured.
  Follow-ups would be, for example, recording `allowed_warning` events and
  utilization, a per-limit capacity note for wave sizing, and moving the
  investigator onto the shared observation (mctl-agents#455).
- `UPDATE_CAPACITY_AND_USAGE_CREDIT_MODEL`: as above, and usage credits were
  actually exercised in the bounded test, proving ADR-012 needs a distinct
  usage-credit bucket (an ADR-012 amendment follow-up).

The report also names which weekly limit binds first for the measured mix and
lists the unknowns. Follow-ups are filed only for gaps the evidence proves.

## Alternatives

1. **Instrument DevLoop first (record every `RateLimitEvent`, add a
   utilization field) and then measure.** Dropped for the spike: it is
   implementation before the decision, which the issue's non-goals forbid,
   and it is one of the follow-ups the outcome may justify. The spike
   captures events with a local harness on the test runs instead.
2. **Conclude from Anthropic's published plan ratios.** Dropped: the issue
   forbids inferring capacity from vendor headline ratios, and the binding
   limit depends on the actual model mix and on other consumers sharing the
   same OAuth token.
3. **Switch the measurement to an API key with Console billing to get exact
   spend.** Dropped: it measures a different billing mode, would not answer
   the subscription-capacity question, and the issue rules out treating
   Ultra as an API billing replacement.

## Platform impact

- **Migrations / compatibility**: none. Adds `docs/spikes/917-*.md`,
  `docs/spikes/917/` artefacts, and a standalone `tools/` script with tests.
  No orchestrator module, CWFT, model policy or credential changes.
- **Resource impact**: the live after-window consumes subscription quota on
  the shared DevLoop account. Mitigation: run during a low-demand window,
  cap the experiment (stop at the first weekly `allowed_warning` or a
  pre-set fraction of the week), and announce it so normal DevLoop work is
  not starved by the measurement.
- **Spend risk**: crossing into usage credits could incur real charges.
  Mitigation: never enable credits for the spike; if already enabled, only a
  single bounded test with an owner-set cap.
- **Accounting risk**: presenting `calculated_cost` as a bill. Mitigation:
  the script and report label every cost as a list-price estimate with its
  `pricing_version`; tests assert no provider-billed label is emitted.
- **Data hygiene**: artefacts exclude token values, prompts and completions,
  consistent with ADR-012 and `RateLimitObservation`'s credential-free rule.
- **Scope risk**: generalising to tenants or shared accounts. Mitigation: the
  report states explicitly that the result is for one subscription-backed
  account and grants no pooling or authority conclusion.
