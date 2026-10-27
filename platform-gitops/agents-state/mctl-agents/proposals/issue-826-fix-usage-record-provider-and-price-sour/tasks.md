# Tasks: issue-826-fix-usage-record-provider-and-price-sour

- [ ] 1. Add provenance to `orchestrator/usage_ledger.py`:
  - the constants `PRICE_SOURCES`, `PRICE_SOURCE_DEFAULT` and `_ANTHROPIC_HOSTS`;
  - the `ModelProvenance` dataclass;
  - `provenance_for_env`, the `attribute_model` context manager and the `_PROVENANCE` contextvar;
  - a module docstring update.

  DoD: `provenance_for_env` returns:
  - the default for an unset or Anthropic base URL;
  - the validated declaration when one is given;
  - `unknown`/`unknown` plus one warning for an undeclared non-Anthropic host.

  A declaration with `mctl_catalog`, an out-of-vocabulary price source, or a malformed provider id raises
  `ValueError`.
- [ ] 2. Wire provenance into `UsageRecorder` (depends on 1):
  - add the `provenance` constructor argument;
  - add `session_env` to `from_env`, and resolve scoped, then session env, then `os.environ`;
  - in `_plan`, set `provider` and `price_source` for third-party sessions;
  - add the `_FORBIDDEN_COST_FIELDS` filter;
  - add `session_env=None` to `tracing.agent_run`, and pass `getattr(options, "env", None)` at
    `run_issue_investigator.py:2537` and `run_implementer.py:2710`.

  DoD:
  - Default records are byte-identical to today's.
  - Third-party records carry the declared or detected `provider` and `price_source`, and ignore
    `ModelUsage.provider`.
  - No record carries a cost field.
  - `cache_write_tokens` is set from `cacheCreationInputTokens` for every provider, and `input_tokens` is
    unchanged in meaning.
- [ ] 3. Collector parity in `orchestrator/run_usage_collector.py` (depends on 1): add `price_source` to
  `_ALLOWED_FIELDS` and `_STRING_FIELDS`. In `sanitise`, drop values outside `usage_ledger.PRICE_SOURCES` with
  a warning.
  DoD: a valid value is forwarded, and an invalid one is dropped without failing the batch.
- [ ] 4. Tracing provider attribute in `orchestrator/tracing.py` (depends on 2): `AgentRunObserver` receives
  the resolved provenance. Chat and root spans use its provider for `gen_ai.provider.name`, and keep
  `PROVIDER` (`anthropic`) by default.
  DoD: span tests show `hetzner` under a declared Hetzner provenance, `unknown` under an undeclared override,
  and `anthropic` otherwise.
- [ ] 5. Add "Amendment 2026-10-27 (mctl-agents#826)" to
  `docs/adr/012-model-usage-cost-attribution-contract.md` (depends on 2). It covers:
  - the `price_source` vocabulary;
  - the declared provider;
  - fail-closed `unknown`;
  - the total input count `input_tokens + cache_read_tokens + cache_write_tokens`, citing the author's
    decision on hir-95c5323867a3b06b;
  - the mctl-api pricing contract;
  - invariants 13 to 15.

  Link follow-up 3 of `docs/spikes/791-hetzner-inference.md` to it.
  DoD: the ADR text matches the code and the tests.
- [ ] 6. File the mctl-api dependency issue: accept and persist `price_source`, and skip catalog pricing when
  it is not `mctl_catalog`. Reference the issue from the ADR amendment.
  DoD: the issue URL is in the amendment, and the lane-enablement work (#824 adoption) lists it as a
  prerequisite.
- [ ] 7. (Optional) `tools/hetzner_inference_spike.py`: record `cache_creation_input_tokens` and
  `cache_read_input_tokens`, and name the CLI figure `cli_cost_estimate_usd` for new runs. Do not rewrite the
  committed artifacts.
  DoD: `report` still renders the committed #791 artifacts unchanged.

## Tests

- [ ] T1. `tests/test_usage_ledger.py`: a recorder under
  `attribute_model(ModelProvenance("hetzner", "provider_free", True))` observes the bucket
  `{"inputTokens": 12, "cacheCreationInputTokens": 58000, "outputTokens": 300, "costUSD": 0.9,
  "provider": "firstParty"}`. It sends `provider="hetzner"`, `price_source="provider_free"`,
  `input_tokens=12` and `cache_write_tokens=58000`, and no cost field of any name.
- [ ] T2. A default session (no `ANTHROPIC_BASE_URL`) produces exactly today's record: no `price_source`, and
  `provider` from the CLI. All existing tests in `tests/test_usage_ledger.py` pass unchanged.
- [ ] T3. With `ANTHROPIC_BASE_URL=https://inference.hetzner.com/api` in `os.environ` and no declaration, the
  record has `provider="unknown"` and `price_source="unknown"`, and exactly one warning is logged.
- [ ] T4. A declaration with `price_source="mctl_catalog"`, a value outside the vocabulary, or a malformed
  provider id raises `ValueError`.
- [ ] T5. A third-party bucket with no `cacheCreationInputTokens` leaves `cache_write_tokens` absent, not 0.
- [ ] T6. `tests/test_usage_collector_records.py`: `price_source` is forwarded when valid and dropped with a
  warning when invalid. The rest of the batch is still sent.
- [ ] T7. `tests/test_tracing_agents.py`: `gen_ai.provider.name` follows the provenance.
- [ ] T8. Scoped provenance does not leak: after the `with attribute_model(...)` block, a new recorder
  resolves the default.
- [ ] T9. Build a recorder through
  `tracing.agent_run(..., session_env={"ANTHROPIC_BASE_URL": "https://inference.hetzner.com/api"})` with a
  clean `os.environ` and no `attribute_model`. It records `unknown`/`unknown`. With a `session_env` that holds
  no base URL, the record is today's.
- [ ] T10. Cumulative deltas still work for third-party buckets: two turns reporting
  `cacheCreationInputTokens` 26199, then 34487, send `cache_write_tokens` 26199, then 8288.

## Rollback

Revert the mctl-agents PR:
- Default (Anthropic) records never changed, so existing lanes and stored rows are unaffected.
- No deployed lane declares third-party provenance or overrides the base URL (verified above), so no
  third-party rows are lost.
- If a lane has been enabled meanwhile, disable it first (remove its provider block or env), so that it does
  not write unattributed usage after the revert.
- Rows already stored with `price_source` stay valid, and mctl-api's nullable column needs no rollback.
