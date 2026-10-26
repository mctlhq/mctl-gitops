# Tasks: issue-826-fix-usage-record-provider-and-price-sour

- [ ] 1. Add the provenance concept to `orchestrator/usage_ledger.py`: the constants `PRICE_SOURCES`,
  `PRICE_SOURCE_DEFAULT` and `_THIRD_PARTY_HOSTS`, the `ModelProvenance` dataclass, `provenance_for_env`, the
  `attribute_model` context manager and the `_PROVENANCE` contextvar. Update the module docstring.
  DoD: `provenance_for_env` returns the default for an unset or Anthropic base URL, the validated declaration
  when one is given, and `unknown`/`unknown` plus one warning for an undeclared non-Anthropic host. A
  third-party declaration with `mctl_catalog` is rejected.
- [ ] 2. Wire provenance into `UsageRecorder` (depends on 1): add a `provenance` constructor arg, resolve it in
  `from_env` (scoped value, else `os.environ`), and in `_plan` set `provider` and `price_source` for third-party
  sessions. Add the `_FORBIDDEN_COST_FIELDS` guard.
  Add the optional `session_env` to `UsageRecorder.from_env` and to `tracing.agent_run(..., session_env=None)`,
  and pass `options.env` from the investigator and implementer call sites.
  DoD: default records are unchanged byte for byte. Third-party records carry the declared `provider` and
  `price_source` and ignore `ModelUsage.provider`. No record ever carries a cost field.
- [ ] 3. Collector parity in `orchestrator/run_usage_collector.py` (depends on 1): add `price_source` to
  `_ALLOWED_FIELDS` and `_STRING_FIELDS`, and drop values outside `usage_ledger.PRICE_SOURCES` with a warning.
  DoD: a valid `price_source` is forwarded, an invalid one is dropped without failing the batch.
- [ ] 4. Tracing provider attribute in `orchestrator/tracing.py` (depends on 1): chat and root spans use the
  resolved provider for `gen_ai.provider.name`, and keep `anthropic` by default.
  DoD: span tests show `hetzner` under a declared Hetzner provenance and `anthropic` otherwise.
- [ ] 5. Add "Amendment 2026-10-26 (mctl-agents#826)" to
  `docs/adr/012-model-usage-cost-attribution-contract.md` (depends on 2): the `price_source` vocabulary,
  declared provider, fail-closed unknown, the total input count formula, the mctl-api pricing contract, and
  invariants 13 to 15.
  DoD: the ADR text matches the code and tests. `docs/spikes/791-hetzner-inference.md` follow-up 3 links to it.
- [ ] 6. File the mctl-api dependency issue (accept and persist `price_source`; skip catalog pricing when it is
  not `mctl_catalog`) and reference it from the ADR amendment.
  DoD: the issue URL is in the ADR amendment, and the lane-enablement work (spike follow-up 1) lists it as a
  prerequisite.
- [ ] 7. (Optional) `tools/hetzner_inference_spike.py`: record `cache_creation_input_tokens` and
  `cache_read_input_tokens`, and name the CLI cost `cli_cost_estimate_usd` for new runs. Do not rewrite the
  committed artifacts.
  DoD: `report` still renders the committed #791 artifacts unchanged.

## Tests

- [ ] T1. `tests/test_usage_ledger.py`: a recorder under `attribute_model(ModelProvenance("hetzner",
  "provider_free", True))` observing a bucket `{"inputTokens": 12, "cacheCreationInputTokens": 58000,
  "outputTokens": 300, "costUSD": 0.9, "provider": "firstParty"}` sends `provider="hetzner"`,
  `price_source="provider_free"`, `input_tokens=12` and `cache_write_tokens=58000`, and sends no cost field of
  any name.
- [ ] T2. The default session (no `ANTHROPIC_BASE_URL`) produces exactly today's record: no `price_source`, and
  `provider` from the CLI. The existing tests pass unchanged.
- [ ] T3. `ANTHROPIC_BASE_URL=https://inference.hetzner.com/api` in the env with no declaration records
  `provider="unknown"` and `price_source="unknown"`, and warns once.
- [ ] T4. A declared third-party provenance with `price_source="mctl_catalog"`, or a value outside the
  vocabulary, is refused at `provenance_for_env`.
- [ ] T5. A third-party bucket with no `cacheCreationInputTokens` leaves `cache_write_tokens` absent, not 0.
- [ ] T6. `tests/test_usage_collector*` (the existing collector test module): `price_source` is forwarded when
  valid and dropped with a warning when invalid. The rest of the batch is still sent.
- [ ] T7. `tests/test_tracing_agents.py`: `gen_ai.provider.name` follows the provenance.
- [ ] T9. A recorder built through `tracing.agent_run(..., session_env={"ANTHROPIC_BASE_URL":
  "https://inference.hetzner.com/api"})`, with `os.environ` holding no base URL and no `attribute_model`, records
  `provider="unknown"` and `price_source="unknown"`. With `session_env` holding no base URL, the record is
  today's.
- [ ] T8. The scoped provenance does not leak: after the `with attribute_model(...)` block, a new recorder
  resolves the default.

## Rollback

Revert the mctl-agents PR. Default (Anthropic) records never changed, so the rollback has no effect on
existing lanes or stored rows. No lane is configured to declare third-party provenance yet, so no third-party
rows are lost. If a lane was already enabled, disable it first (remove its provider block or env) so that it
does not write unattributed usage after the revert. Rows already stored with `price_source` stay valid, and
mctl-api's nullable column needs no rollback.
