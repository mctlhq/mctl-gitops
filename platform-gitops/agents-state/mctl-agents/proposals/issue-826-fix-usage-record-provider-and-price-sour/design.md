# Design: issue-826-fix-usage-record-provider-and-price-sour

## Current state

- `orchestrator/usage_ledger.py`, `UsageRecorder._plan`:
  - It builds one record per `model_usage` bucket per result, as a delta against the last recorded cumulative
    counters.
  - `_COUNTERS` maps `inputTokens` to `input_tokens`, `cacheReadInputTokens` to `cache_read_tokens`, and
    `cacheCreationInputTokens` to `cache_write_tokens`. Absent counters stay absent.
  - `provider` is copied verbatim from `usage.get("provider")`, the CLI's `ModelUsage.provider`.
  - `costUSD` and `total_cost_usd` are never read, and the record has no cost field. This is pinned by
    `tests/test_usage_ledger.py::test_a_record_carries_no_cost_no_id_and_no_text`.
  - `_carries_usage` already treats `provider_reported_cost` specially.
- How the recorder is built:
  - `orchestrator/tracing.py` ~L1177 calls `usage_ledger.UsageRecorder.from_env(self._agent, ...)`.
  - `from_env` merges the pod-env correlation (`_CORRELATION_ENV`) with the `_SCOPED` contextvar that runners
    set through `usage_ledger.correlate(...)`.
  - The SDK drivers open `tracing.agent_run` at `run_issue_investigator.py:2537`, `run_implementer.py:2710` and
    `run_shepherd.py:2847`.
- `docs/adr/012-model-usage-cost-attribution-contract.md`:
  - `provider_reported_cost` is always null.
  - The SDK's `costUSD` / `total_cost_usd` count as *calculated*, never as provider-reported.
  - The producer sends no cost. mctl-api prices the token counts at ingest (`calculated_cost` +
    `pricing_version`).
  - Absent and zero are different facts.
- `orchestrator/run_usage_collector.py`: `_ALLOWED_FIELDS`, `_STRING_FIELDS` and `_INT_FIELDS` form the second
  producer's allowlist, and it has deliberately no cost fields. A new field must be added there or it is
  stripped.
- `orchestrator/tracing.py`:
  - `PROVIDER = "anthropic"` (L919) is hard-coded into `gen_ai.provider.name` (L1057 and L1194).
  - Span token counts already export `gen_ai.usage.cache_creation.input_tokens` (L922, L933) separately.
- `tools/hetzner_inference_spike.py`:
  - `hetzner_session_env` points sessions at Hetzner through `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN`
    and blanks the usage writer token, so the spike wrote no ledger rows.
  - Its bench records took `input_tokens` from `ResultMessage.usage` (L615) and `cost_usd_current` from
    `total_cost_usd` (L616). Those are the two misreadings that follow-up 3 describes.
- `config/model-policy.yaml` / `config/model_policy.py`: a profile names only a model. `ProviderSpec` /
  `provider_session_env` (the #824 seam) do not exist on main; `grep` finds no match.

Consequence: the ledger already does not forward the CLI cost, and it already records cache creation as
`cache_write_tokens`. The defect is attribution. A Hetzner session would yield a record whose `provider` is
whatever the CLI reports for its transport, and no field would say the row is third-party or how it is priced.

Deployed state checked:
- `mctl_list_services(team=admins)`: `mctl-agents-worker`, `-worker-exec` and `-worker-implement` all run
  `ghcr.io/mctlhq/mctl-agents:1.105.0` and are Synced. No experimental-lane service exists.
- `grep -rl ANTHROPIC_BASE_URL|HETZNER` over `$MCTL_GITOPS_ROOT`: matches only proposal and inbox documents
  under `agents-state/` (#791, #824 and this issue). No deployed config points a session at a third-party
  endpoint.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/issue-824-*/.status.yaml`: `status: review-stuck`. The
  provider seam is not merged.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-api/proposals/issue-403-*/design.md` (merged): mctl-api's price catalog
  is keyed by `(model, provider, effective_from)`, and a missing card gives a null cost. This is a design
  document, not observed runtime behaviour.
- mctl-api's ingest validation (`internal/usage/types.go`, cited in `usage_ledger.py`) is not in this clone.
  How it handles a new `price_source` field was not observed (see Open questions in requirements.md).

## Proposed solution

### 1. Provenance in `orchestrator/usage_ledger.py`

- Constants:
  - `PRICE_SOURCES = frozenset({"mctl_catalog", "provider_free", "unknown"})`.
  - `PRICE_SOURCE_DEFAULT = "mctl_catalog"`.
  - `_ANTHROPIC_HOSTS = frozenset({"api.anthropic.com"})`.
- A frozen dataclass `ModelProvenance(provider: str | None, price_source: str, third_party: bool)`.
- `provenance_for_env(env, *, declared=None) -> ModelProvenance`. This is the single validation gate:
  - With `declared`: `provider` must match `[a-z0-9-]+`, `price_source` must be in `PRICE_SOURCES`, and a
    third-party provenance may not claim `mctl_catalog`. A violation raises `ValueError` at declaration time,
    so the lane fails before it runs rather than writing mis-attributed rows. Otherwise the declaration is
    returned.
  - Else, if `ANTHROPIC_BASE_URL` is unset, empty, or its host is in `_ANTHROPIC_HOSTS`: return
    `ModelProvenance(None, "mctl_catalog", False)`. `provider=None` means "keep the CLI's value", which is
    today's behaviour.
  - Else: return `ModelProvenance("unknown", "unknown", True)` and warn once with the host name. This fails
    closed: an undeclared endpoint is never attributed to Anthropic or priced from its catalog.
- `attribute_model(provenance)`: a context manager that sets a second contextvar `_PROVENANCE`, in the same
  style as `correlate`. A lane wraps its `anyio.run` in it. When #824 lands, its `ProviderSpec` plus the lane's
  price source become the declaration; that wiring is adoption work.
- Changes to `UsageRecorder`:
  - `__init__` gains `provenance: ModelProvenance | None = None`.
  - `from_env` gains `session_env: Mapping[str, str] | None = None` and resolves provenance in this order:
    1. the scoped `_PROVENANCE`;
    2. `provenance_for_env({**os.environ, **session_env})` when a session env is given;
    3. `provenance_for_env(os.environ)`.
  - `tracing.agent_run(agent, model, *, session_env=None)` threads it through. The investigator
    (`run_issue_investigator.py:2537`) and the implementer (`run_implementer.py:2710`) pass
    `getattr(options, "env", None)`.
  - The shepherd's one-shot `query()` uses no override and keeps the default.
- Changes to `_plan`:
  - With a third-party provenance: `record["provider"] = provenance.provider` and
    `record["price_source"] = provenance.price_source`. `ModelUsage.provider` is ignored, and `canonical_model`
    is still recorded as reported.
  - With the default provenance: the record is unchanged. `price_source` is omitted, so every Anthropic batch
    stays byte-identical and the existing lanes need no rollout ordering with mctl-api.
- `_FORBIDDEN_COST_FIELDS = ("calculated_cost", "provider_reported_cost", "pricing_version",
  "invoice_reconciled_cost", "costUSD", "total_cost_usd", "cost_usd")`: every planned record is filtered
  against it, and a hit is dropped with a warning. It cannot fire today. It pins the acceptance criterion "no
  CLI-estimated cost as billed cost" against regressions.
- Cache creation (resolved decision): no mapping change. `cacheCreationInputTokens` already becomes
  `cache_write_tokens` for every provider. `input_tokens` keeps its meaning, and the total input count is
  documented as `input_tokens + cache_read_tokens + cache_write_tokens`. Tests with spike-shaped numbers
  (`inputTokens` 12, `cacheCreationInputTokens` 58000) pin that for a third-party bucket.

### 2. Collector parity (`orchestrator/run_usage_collector.py`)

`sanitise` handles `price_source` as follows:
- it is added to `_ALLOWED_FIELDS` and `_STRING_FIELDS`;
- a value not in `usage_ledger.PRICE_SOURCES` is dropped with a warning;
- the vocabulary is imported, not copied, like `TARGET_REPO_RE`.

### 3. Tracing (`orchestrator/tracing.py`)

`AgentRunObserver` takes the resolved provenance, which comes from the same `from_env` resolution. For a
third-party session, `gen_ai.provider.name` is the provenance provider; otherwise it stays `PROVIDER`
(`anthropic`). The token attributes do not change.

### 4. ADR-012 amendment

Add "Amendment 2026-10-27: provider and price source (mctl-agents#826)" to
`docs/adr/012-model-usage-cost-attribution-contract.md`, covering:
- the `price_source` field and its vocabulary;
- that a third-party `provider` is declared by the lane, never taken from the CLI;
- that an undeclared non-Anthropic base URL records `unknown`/`unknown`;
- that the total input count is `input_tokens + cache_read_tokens + cache_write_tokens` (the author's
  decision on hir-95c5323867a3b06b);
- the server contract: mctl-api must not apply catalog prices when `price_source != mctl_catalog`. For
  `provider_free` it stores a zero or null cost under its own `pricing_version` (mctl-api's choice); for
  `unknown` it stores null.

Add invariants 13 to 15:
- 13: a third-party record carries `provider` and `price_source`;
- 14: no record carries any cost field from the producer;
- 15: `cache_write_tokens` is present whenever the bucket reported `cacheCreationInputTokens`.

Update follow-up 3 in `docs/spikes/791-hetzner-inference.md` to link to the amendment.

### 5. Spike harness (optional)

`tools/hetzner_inference_spike.py` records `cache_creation_input_tokens` and `cache_read_input_tokens` next to
`input_tokens`, and names the CLI figure `cli_cost_estimate_usd` for new runs. Committed #791 artifacts are not
rewritten, and `report` must still render them.

### Server dependency

mctl-api must accept and persist `price_source`. Until it does, no lane may declare third-party provenance.
The producer is safe either way: a rejected batch takes the existing "HTTP error, nothing stored, logged" path
in `_deliver`, so no wrongly priced row can be stored. Task 6 files the mctl-api issue.

## Alternatives

1. **Make `input_tokens` inclusive of cache creation for third-party rows.** This is the literal reading of
   the issue. The author rejected it on hir-95c5323867a3b06b: mctl-api prices `cache_write_tokens`
   separately, so an inclusive count would double-bill and break the column's meaning across providers.
2. **The producer sends `calculated_cost = 0` for Hetzner.** Rejected because ADR-012 gives pricing to
   mctl-api's versioned catalog, and the collector forbids producer cost fields. A producer-side zero would
   also erase the difference between "free" and "unknown".
3. **Infer the provider from `ANTHROPIC_BASE_URL` via a host table, with no declaration.** Simpler, but a host
   table would silently decide pricing. It is kept only as the fail-closed detector that yields `unknown`.
4. **Skip recording third-party usage entirely.** Safe for cost, but it loses the token evidence needed to
   evaluate the lane and hides experimental spend from operators.

## Platform impact

- **Migrations:** none in mctl-agents. Stored rows are untouched. mctl-api needs a nullable `price_source`
  column, in a separate repo.
- **Backward compatibility:** Anthropic records stay byte-identical (no `price_source`, `provider`
  unchanged). Third-party records appear only once a lane declares provenance or overrides the base URL, and
  neither is deployed today.
- **Resources:** negligible: one contextvar read and one URL parse per recorder.
- **Risks and mitigations:**
  - An undeclared override is mis-priced. Mitigation: fail closed to `unknown`/`unknown` with a warning.
  - mctl-api rejects the unknown field. Mitigation: the batch is not stored and a warning is logged, so no
    wrong row exists. The lane stays disabled until mctl-api supports the field.
  - The vocabulary drifts between the producer and the collector. Mitigation: the collector imports the
    constant.
  - The CLI's `model_usage` lacks `cacheCreationInputTokens` for Hetzner. Mitigation: the field stays absent,
    never 0, and the first lane run must confirm it (open question).
