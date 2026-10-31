# Tasks: issue-917-spike-does-verified-claude-ultra-remove

- [ ] 1. Create `docs/spikes/917-claude-ultra-capacity.md` with `STATUS:
  PENDING_EVIDENCE`, the allowed outcomes, sources from the issue, the current
  credential path (`orchestrator/auth.py:detect_auth`, OAuth token from Vault
  `platform/mctl-agents` per `services/admins/mctl-agents-worker/values.yaml`),
  the quota-evidence path (`orchestrator/rate_limit.py`), and an account-facts
  table (tier, verified, usage credits enabled, other consumers of the same
  token) with "not observed" placeholders. — DoD: the doc states the
  measurement protocol and decision rule from design.md before any data is
  added, and contains no token values.
- [ ] 2. Add the FinOps mapping section (included subscription quota vs
  `calculated_cost` list-price estimate vs usage-credit spend vs Console/API
  credits), each row tied to its ADR-012 field or marked "not representable
  today". (depends on 1) — DoD: the table exists, cites
  `docs/adr/012-model-usage-cost-attribution-contract.md`, and nowhere calls
  SDK `costUSD` a provider charge.
- [ ] 3. Implement `tools/spike_917_capacity.py` (stdlib only): load a JSONL
  of per-run records and a run manifest from `docs/spikes/917/`; output
  stages/hour and /day by stage and model, 429 count and lost wall-clock by
  `rate_limit_type` (missing type -> `unknown`), weekly-consumption curve from
  hand-recorded remaining percentages, and marginal throughput between the
  first would-be `five_hour` boundary and the first weekly warning. Cost
  columns are labelled as list-price estimates with `pricing_version`. —
  DoD: script runs on a fixture and prints all sections; inputs missing a
  source are reported as "not observed", never zero.
- [ ] 4. Add the record schema and a synthetic fixture under
  `docs/spikes/917/` (`records-schema.md`, `fixture-records.jsonl`,
  `fixture-manifest.json`) mirroring the `docs/spikes/825/` layout. (depends
  on 3) — DoD: fixture includes `five_hour`, `seven_day`, unknown-type and
  `allowed_warning` events plus a Fable and a non-Fable model.
- [ ] 5. Reconstruct the before window from existing evidence only
  (`.status.yaml` `rate_limited` entries, investigator
  `rate-limit-exhausted` outcomes, archived Argo logs, usage-ledger buckets),
  and record in the report what each source covered and what retention cut
  off. (depends on 1) — DoD: a before-window table with per-type rejection
  counts or explicit "not observed" with reason.
- [ ] 6. Owner-run after window: on the verified Ultra account, run
  representative DevLoop stages back-to-back under the capped protocol,
  capture every `RateLimitEvent` and per-run usage into `docs/spikes/917/`,
  record warning/refusal and wrap-up behaviour, and record the usage-credit
  path as "unmeasured" unless credits were already enabled (then one bounded
  test under an owner-set cap). (depends on 3, 4) — DoD: raw artefacts
  committed without secrets; stop condition and actual duration recorded.
- [ ] 7. Run the script over both windows, fill the report's capacity
  evidence, name which weekly limit (all-models or Fable) binds first for the
  measured mix, list unknowns, and set exactly one outcome by the decision
  rule; owner records the decision line. (depends on 2, 5, 6) — DoD: `STATUS:`
  holds exactly one allowed outcome; follow-ups listed only for proven gaps
  (candidates: record `allowed_warning`/utilization, adopt shared observation
  in the investigator per mctl-agents#455, ADR-012 usage-credit bucket).

## Tests

- [ ] T1. `tests/test_spike_917_capacity.py`: on the fixture, per-type 429
  counts and lost wall-clock match hand-computed values; a rejection without
  `rate_limit_type` is counted under `unknown`.
- [ ] T2. Throughput is normalized per stage and model: two fixture windows
  with the same per-stage rate but different stage mix report equal per-stage
  rates.
- [ ] T3. No output line labels any cost as provider-billed or invoice;
  every cost column carries "list-price estimate" and a `pricing_version`.
- [ ] T4. A missing source file or field yields "not observed", not 0.
- [ ] T5. Fable and all-models weekly consumption are reported as separate
  series; the binding-limit line names one of them or "not observed".
- [ ] T6. Grep check in the test: fixture and report contain no
  `sk-ant-` substrings.

## Rollback

The change is documentation plus a standalone script that nothing imports.
Revert the PR (or delete `docs/spikes/917*`, `tools/spike_917_capacity.py`
and its test). If the live after-window is starving DevLoop, stop the
measurement runs; no credential, policy or runtime setting was changed, so
nothing else needs restoring. If usage credits were exercised, the bounded
cap limits exposure; disable credits in the Anthropic account settings if
the owner chooses.
