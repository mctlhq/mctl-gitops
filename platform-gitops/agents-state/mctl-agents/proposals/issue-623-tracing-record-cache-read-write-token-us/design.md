# Design: issue-623-tracing-record-cache-read-write-token-us

## Current state

- `orchestrator/tracing.py`
  - `_usage_counts(usage)` (around line 922) maps only `input_tokens -> gen_ai.usage.input_tokens` and `output_tokens -> gen_ai.usage.output_tokens`. It accepts a value only if it is an `int` and not a `bool`. Every other key in the SDK `usage` mapping is ignored, including `cache_read_input_tokens` and `cache_creation_input_tokens`.
  - `AgentRunObserver._assistant` calls `_usage_counts(message.usage)` and sets the result on the per-message `chat <model>` span.
  - `AgentRunObserver._result` sums `_usage_counts(ResultMessage.usage)` into the two scalars `self._input_tokens` and `self._output_tokens`, behind a single `self._saw_usage` flag. `close()` writes both onto the `invoke_agent` span only when `_saw_usage` is true. So "absent" means the provider never reported usage, and 0 is never invented.
  - The observer never reads content blocks, tool inputs or results. That privacy property is not touched by this change.
- `orchestrator/tracing_sdk.py`
  - `_ALLOWED_KEY` allowlists `gen_ai.usage.input_tokens|output_tokens` only.
  - `_USAGE_TOKEN_KEYS` is the frozenset of the only keys allowed to contain "token". `key_allowed` checks it before the `_TOKEN_KEY` (`(?i)token`, from `orchestrator/redaction.py`) denylist.
  - `redact_attributes` drops a non-int or bool value under a `_USAGE_TOKEN_KEYS` key.
  - A new `gen_ai.usage.cache_*_tokens` key would therefore be **dropped at export** today, even if `tracing.py` emitted it. The allowlist change is required, not optional.
- `orchestrator/usage_ledger.py`
  - `_COUNTERS` already maps the SDK's `ResultMessage.model_usage` counters `cacheReadInputTokens -> cache_read_tokens` and `cacheCreationInputTokens -> cache_write_tokens`. The ledger already has both dimensions. Tracing is the only part missing them.
- Anthropic `usage` semantics: `input_tokens` is the uncached remainder, and the cache counters are reported separately. Recording them as separate attributes cannot double-count.
- Tests
  - `tests/test_tracing_agents.py::_result` already puts `cache_read_input_tokens: 9` into `ResultMessage.usage`. `test_model_spans_carry_model_usage_and_latency_but_no_prompt` asserts input 1500 and output 420 on the root, which confirms that the cache counter is silently ignored today.
  - `tests/test_tracing.py::test_catalog_keys_are_allowed` and `test_a_string_under_a_usage_counter_is_refused` pin the allowlist.
- Docs
  - `docs/observability/execution-traces.md` attribute table lists only input/output. It also notes that the Collector's `.*token.*` masking (mctl-gitops#1332) affects `gen_ai.usage.*_tokens`.
  - `docs/adr/012-model-usage-cost-attribution-contract.md` maps cache counters to an mctl-owned `mctl.gen_ai.usage.cache_*` name.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker-exec/values.yaml`: `otel.enabled: true`, `MCTL_TRACE_WORKFLOW_TYPES: DevLoopWorkflow`, `MCTL_TRACE_ARGO_PARAM: "true"`. Tracing is live for DevLoop on the exec worker.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker-implement/values.yaml`: has the same `MCTL_TRACE_WORKFLOW_TYPES` / `MCTL_TRACE_ARGO_PARAM` env (lines 105-106).
- Not checked: the Collector's current redaction config (mctl-gitops#1332 state) and Tempo contents. I made no mctl MCP calls, and the Collector config is outside `services/`/`tenants/`. Whether the new keys survive the Collector is unobserved and is listed under Open questions in requirements.md.

## Proposed solution

Only the existing GenAI tracing path in `orchestrator/tracing.py` changes, plus the export allowlist in `orchestrator/tracing_sdk.py`.

1. **Attribute names.** Use the OTel GenAI semantic-convention names, which are in development status:
   - `cache_read_input_tokens` -> `gen_ai.usage.cache_read.input_tokens`
   - `cache_creation_input_tokens` -> `gen_ai.usage.cache_creation.input_tokens`

   Add module constants for them in `tracing.py` (for example `USAGE_CACHE_READ` / `USAGE_CACHE_CREATION`) so tests and code share one spelling.

2. **`_usage_counts`.** Extend the `pairs` tuple with the two cache mappings. The int/not-bool check is unchanged, so a missing, `None`, string or bool counter produces no key. `chat` spans pick up the new attributes with no change to `_assistant`.

3. **`invoke_agent` aggregation.** Replace the two scalars and the single `_saw_usage` flag with `self._usage_totals: dict[str, int]`, keyed by attribute name.
   - `_result` adds each key that `_usage_counts` returned: `totals[k] = totals.get(k, 0) + v`.
   - `close()` sets `self._usage_totals` on the root when it is non-empty.

   Input and output behave exactly as before: they appear once any result frame reported them, summed over frames. A cache attribute appears only if some frame reported that counter, so it is never fabricated as 0. One small edge case changes. Today a result frame that reports only `input_tokens` makes `close()` also emit `output_tokens = 0`. After the change, only the reported key is emitted. That matches "no fabricated values". A test pins it, and if reviewers want exact parity, the first two keys can be seeded from `_saw_usage` instead.

4. **Export allowlist (`tracing_sdk.py`).**
   - Extend `_ALLOWED_KEY` with `usage\.cache_read\.input_tokens|usage\.cache_creation\.input_tokens`.
   - Add both keys to `_USAGE_TOKEN_KEYS`, so they bypass `_TOKEN_KEY` and fall under the int-only value rule in `redact_attributes`.

5. **Docs.**
   - Add one row to the attribute table in `docs/observability/execution-traces.md`.
   - Add one item to the #195 live-evidence checklist: cache attributes visible and unmasked in Tempo.
   - Amend the ADR-012 "OpenTelemetry mapping" row and its "Cache tokens have no stable upstream home" bullet. The new text should say that spans use the upstream development names, while the ledger record fields (`cache_read_tokens`/`cache_write_tokens`) stay mctl-owned and are the source of truth for accounting.
   - Add a CHANGELOG entry through release-please (a conventional `feat(tracing):` commit).

No change to `usage_ledger.py`, the Temporal path, metrics, or the providers.

## Alternatives

- **Follow ADR-012 literally (`mctl.gen_ai.usage.cache_read_tokens` / `cache_write_tokens`).** These names are guaranteed stable under the mctl namespace. Dropped as the default because the issue's acceptance criteria name `gen_ai.usage.*`, and Tempo/Grafana GenAI views recognise the upstream names. It is kept as the one-line fallback listed under Open questions in requirements.md.
- **Emit both the upstream and the mctl-prefixed names.** Dropped because two attributes for the same counter invite double-summing in queries and double the surface the Collector redaction must handle.
- **Fold cache tokens into `gen_ai.usage.input_tokens` (total prompt tokens).** The issue explicitly forbids this. It would also change the meaning of an existing attribute and break comparisons with older traces.
- **Read the counters from the usage ledger's `model_usage` instead of the message `usage`.** Dropped because the ledger works on cumulative per-model deltas at result granularity. That cannot populate per-message `chat` spans, and it would couple tracing to ledger internals.

## Platform impact

- **Migrations / compatibility.** None. These are purely additive span attributes, and existing attributes keep their values. Older traces simply lack the new keys.
- **Resource impact.** At most two extra integer attributes per `chat` and `invoke_agent` span. Negligible.
- **Privacy.** The values are integers, and the export layer rejects any non-int under these keys. No content is read.
- **Risk: Collector masking.** If mctl-gitops#1332's fix only special-cases input/output, the new keys may arrive as `****`. Mitigation: verify on the first deployed run and, if needed, extend the Collector rule in a gitops PR. The code needs no change for this.
- **Risk: upstream name churn.** The GenAI conventions are still in development. If they rename these keys, the change is two constants plus the allowlist. The ledger remains the accounting source of truth (ADR-012), so analytics are not affected.
- **Rollout.** Ships with the next mctl-agents image. The workers already have `otel.enabled: true` for `DevLoopWorkflow`, so the next real DevLoop produces the #195 evidence.
