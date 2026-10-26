# Design: issue-826-fix-usage-record-provider-and-price-sour

## Current state

- `orchestrator/usage_ledger.py`, `UsageRecorder._plan`: one record per `model_usage` bucket per result, as a
  delta against the last recorded cumulative counters. The `_COUNTERS` mapping already maps
  `cacheCreationInputTokens` to `cache_write_tokens` and `cacheReadInputTokens` to `cache_read_tokens`, next to
  `inputTokens` to `input_tokens`. `provider` is copied verbatim from `usage.get("provider")`, the CLI's
  `ModelUsage.provider`. `costUSD` is never read, and the record has no cost field
  (`tests/test_usage_ledger.py::test_a_record_carries_no_cost_no_id_and_no_text`).
- `UsageRecorder` is built by `tracing.agent_run` (`orchestrator/tracing.py` ~L1177,
  `usage_ledger.UsageRecorder.from_env(self._agent, ...)`). `from_env` merges pod env correlation
  (`_CORRELATION_ENV`) with the `_SCOPED` contextvar that runners set through `usage_ledger.correlate(...)`
  (`run_issue_investigator.py` ~L3859, `run_implementer.py` ~L3102/~L4985, `run_shepherd.py` ~L4100).
- `docs/adr/012-model-usage-cost-attribution-contract.md`: `provider_reported_cost` is always null. SDK
  `costUSD` / `total_cost_usd` count as calculated, never provider-reported. The producer sends no cost, and
  mctl-api prices token counts at ingest (`calculated_cost` + `pricing_version`). Absent and zero are different
  facts.
- `orchestrator/run_usage_collector.py` `_ALLOWED_FIELDS` / `_STRING_FIELDS`: the second producer forwards
  only listed fields and has deliberately no cost fields. A new field must be added there or it is stripped.
- `orchestrator/tracing.py`: `PROVIDER = "anthropic"` is hard-coded into `gen_ai.provider.name` on chat spans
  (~L1057, ~L1194). `_usage_counts` reads `ResultMessage.usage`, where `input_tokens` excludes cache creation.
  The cache-creation count is exported separately as `gen_ai.usage.cache_creation.input_tokens`.
- `tools/hetzner_inference_spike.py`: `hetzner_session_env` points sessions at Hetzner through
  `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` and blanks the usage writer token, so the spike wrote no
  ledger rows. Its records took `input_tokens` from `ResultMessage.usage` and `cost_usd_current` from
  `total_cost_usd`. Those are the two misreadings follow-up 3 of the spike doc describes.
- `config/model-policy.yaml` / `config/model_policy.py`: a profile names a model only. No provider, endpoint or
  credential exists yet (spike follow-up 1).

Consequence: the ledger already does not forward the CLI cost, and it already records cache-creation tokens as
`cache_write_tokens`. The defect is attribution. A Hetzner session through the CLI would yield a record whose
`provider` is whatever the CLI reports for its transport. Nothing marks it as third-party, so mctl-api could
apply its Anthropic catalog to it and produce a non-zero `calculated_cost` for free usage.

Deployed state checked:
- `mctl_list_services(team=admins)`: `mctl-agents-worker`, `-worker-exec` and `-worker-implement` all run
  `ghcr.io/mctlhq/mctl-agents:1.104.0`, Synced. No experimental lane service exists.
- `grep ANTHROPIC_BASE_URL|inference.hetzner` over `$MCTL_GITOPS_ROOT/services` and `tenants`: no match. No
  deployed config points any session at a third-party endpoint today.
- The mctl-api ingest validation (`internal/usage/types.go`, cited in `usage_ledger.py`) is not in this clone.
  Its handling of a new `price_source` field and of unknown `canonical_model` values was not observed (see
  Open questions in requirements.md).

## Proposed solution

### 1. A provenance concept in `orchestrator/usage_ledger.py`

- Add the constants `PRICE_SOURCES = frozenset({"mctl_catalog", "provider_free", "unknown"})` and
  `PRICE_SOURCE_DEFAULT = "mctl_catalog"`. Add a known-endpoint table
  `_THIRD_PARTY_HOSTS = {"inference.hetzner.com": "hetzner"}`.
- Add a frozen dataclass `ModelProvenance(provider: str | None, price_source: str, third_party: bool)`.
- Add `provenance_for_env(env: Mapping[str, str], *, declared: ModelProvenance | None = None)`:
  - If `declared` is given (the lane's provider block, follow-up 1, will supply it), validate it:
    `price_source` must be in `PRICE_SOURCES`, and a third-party provenance must not claim `mctl_catalog`.
    Return it.
  - Else, if `ANTHROPIC_BASE_URL` is unset, empty, or its host is `api.anthropic.com`, return
    `ModelProvenance(None, "mctl_catalog", False)`. `provider=None` means "use the CLI's value", which is
    today's behaviour.
  - Else (an override with no declaration) return `ModelProvenance("unknown", "unknown", True)` and warn once.
    This fails closed: an undeclared endpoint is never attributed to Anthropic or priced from its catalog. The
    host table is only used to make the warning readable. A declaration is still required to record `hetzner`.
- Add a context manager `attribute_model(provenance)`, which sets a second contextvar `_PROVENANCE` in the same
  style as `correlate`. A lane wraps its `anyio.run` in it, using the `env` it put into `ClaudeAgentOptions`.
  The provenance comes from the session env, not from the runner's process env, because the base URL may exist
  only in the options env.
- `UsageRecorder.__init__` gains `provenance: ModelProvenance | None`. `from_env` resolves it in this order:
  the scoped `_PROVENANCE`, else `provenance_for_env(os.environ)`. That way a process-wide override is also
  caught.
- `_plan`:
  - Third-party provenance: `record["provider"] = provenance.provider` and
    `record["price_source"] = provenance.price_source`. The CLI's `ModelUsage.provider` is ignored, and
    `canonical_model` is still recorded as reported.
  - Default provenance: the record is unchanged. `provider` comes from the CLI, and `price_source` is omitted;
    its absence means `mctl_catalog`. Omitting it keeps every Anthropic batch byte-identical, so the rollout
    needs no ordering with mctl-api for the existing lanes.
- Add an explicit guard `_FORBIDDEN_COST_FIELDS = ("calculated_cost", "provider_reported_cost",
  "pricing_version", "invoice_reconciled_cost", "costUSD", "total_cost_usd")`, asserted absent from every
  planned record. A violation drops the field and logs a warning. Today it cannot fire. It pins the "no
  CLI-estimated cost as billed cost" acceptance criterion so it cannot regress.
- Cache-creation: no mapping change is needed, because `cacheCreationInputTokens` is already mapped to
  `cache_write_tokens` for every provider. The design documents the total input count as
  `input_tokens + cache_read_tokens + cache_write_tokens` (ADR amendment). A test with spike-shaped numbers
  (`inputTokens` 12, `cacheCreationInputTokens` 58000) pins the behaviour for a third-party bucket.
- `_checked_correlation` is not the place for this. Provenance is validated in `provenance_for_env`, the single
  gate, mirroring how `devloop_stage` has one gate.

### 2. Collector parity (`orchestrator/run_usage_collector.py`)

Add `price_source` to `_ALLOWED_FIELDS` and `_STRING_FIELDS`, and drop it with a warning when it is not in
`usage_ledger.PRICE_SOURCES`. The vocabulary is imported, not copied, like `TARGET_REPO_RE`.

### 3. Tracing (`orchestrator/tracing.py`)

The `AgentRunObserver` takes the resolved provider. It sets `gen_ai.provider.name` to the provenance provider
for third-party sessions, and keeps `anthropic` by default. No token counter changes:
`gen_ai.usage.cache_creation.input_tokens` is already exported next to `gen_ai.usage.input_tokens`.

### 4. ADR-012 amendment

Add "Amendment 2026-10-26: provider and price source (mctl-agents#826)" to
`docs/adr/012-model-usage-cost-attribution-contract.md`. It covers:
- the `price_source` field and vocabulary;
- that third-party `provider` is declared by the lane, never taken from the CLI;
- that a non-Anthropic base URL without a declaration records `unknown`/`unknown`;
- that the total input count is `input_tokens + cache_read_tokens + cache_write_tokens`;
- the server contract: mctl-api must not apply its price table when `price_source != mctl_catalog`. For
  `provider_free` it stores `calculated_cost = 0` with a `pricing_version` naming the free tier, or null; that
  choice is mctl-api's. For `unknown` it stores null.

Add testable invariants 13 to 15 to match.

### 5. Spike harness (optional, low cost)

`tools/hetzner_inference_spike.py` records `cache_creation_input_tokens` and `cache_read_input_tokens` next to
`input_tokens`, and renames `cost_usd_current` to `cli_cost_estimate_usd` for new runs. The committed #791
artifacts are not rewritten.

### Server dependency

mctl-api must accept and persist `price_source` and honour it in pricing. Until it does, no lane may declare
third-party provenance. The producer is safe either way: a rejected batch is the existing "HTTP error, nothing
stored, logged" path (`_deliver`), so no wrongly-priced row can be stored. A follow-up issue on
`mctlhq/mctl-api` is part of task 6.

## Alternatives

1. **Rewrite `input_tokens` to include cache creation for third-party rows.** This follows the issue's wording
   literally. It was dropped because mctl-api prices `cache_write_tokens` separately, so an inclusive
   `input_tokens` would double-bill and break comparability with Anthropic rows of the same column. It is kept
   as the alternative in the clarification question.
2. **Have the producer send `calculated_cost = 0` for Hetzner.** Dropped because ADR-012 assigns pricing to
   mctl-api's versioned catalog, and the producer must never send cost fields (the collector forbids them
   too). A producer-side zero would also hide the difference between "free" and "unknown".
3. **Infer the provider from `ANTHROPIC_BASE_URL` only, with no declaration.** It is simpler, but it lets any
   host-table entry silently decide pricing, and the base URL may live only in the options env. It is kept
   only as the fail-closed detector that yields `unknown`.
4. **Skip recording third-party usage entirely.** Safe for cost, but it loses the token evidence the lane
   needs to be evaluated, and it would hide experimental usage from the operator.

## Platform impact

- **Migrations:** none in mctl-agents. Existing ledger rows are not touched. mctl-api needs a nullable
  `price_source` column, which is a separate repo.
- **Backward compatibility:** Anthropic records are byte-identical (`price_source` omitted, `provider`
  unchanged). Third-party records exist only once a lane declares provenance, and that lane does not exist
  yet.
- **Resources:** negligible, one contextvar read per recorder.
- **Risks and mitigations:**
  - An undeclared override is mis-priced: fail closed to `unknown`/`unknown`.
  - mctl-api rejects the new field: the batch is not stored, a warning is logged, and nothing wrong reaches the
    ledger. The lane must stay disabled until mctl-api supports the field.
  - The vocabulary drifts between the producer and the collector: the collector imports the constant.
  - The CLI's `model_usage` lacks `cacheCreationInputTokens` for Hetzner: the field stays absent, never 0. The
    first lane run must confirm it (open question).
