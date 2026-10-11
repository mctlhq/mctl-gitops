# Tasks: issue-623-tracing-record-cache-read-write-token-us

- [ ] 1. In `orchestrator/tracing_sdk.py`, add `gen_ai.usage.cache_read.input_tokens` and `gen_ai.usage.cache_creation.input_tokens` to `_ALLOWED_KEY` and `_USAGE_TOKEN_KEYS`. — DoD: `key_allowed` returns True for both, and `redact_attributes` keeps them as ints and drops them as str/bool.
- [ ] 2. In `orchestrator/tracing.py`, add constants for the two names and extend the `pairs` tuple in `_usage_counts` with `cache_read_input_tokens` and `cache_creation_input_tokens` (depends on 1). — DoD: `chat` spans carry the cache attributes when the SDK reports them, and nothing changes otherwise.
- [ ] 3. Replace `AgentRunObserver._input_tokens` / `_output_tokens` / `_saw_usage` with a per-key `_usage_totals` dict. Fill it in `_result` and emit it in `close()` when non-empty (depends on 2). — DoD: `invoke_agent` input/output sums are unchanged, cache sums appear only when some result frame reported them, and nothing is ever added to `input_tokens`.
- [ ] 4. Docs (depends on 3):
  - add an attribute-table row and a #195 checklist item in `docs/observability/execution-traces.md`;
  - amend the cache row and the bullet in ADR-012's "OpenTelemetry mapping" section;
  - update the `AgentRunObserver` docstring.

  DoD: the docs name the two attributes, their spans and their source (SDK `usage`).
- [ ] 5. After release, run one real DevLoop on the deployed workers and link its Tempo trace on mctl-agents#195, showing `chat` spans with cache attributes as integers (not `****`). If they are masked, open the mctl-gitops Collector follow-up (depends on 4). — DoD: an evidence comment is posted on #195.

## Tests

- [ ] T1. `tests/test_tracing_agents.py`, input/output only: an `AssistantMessage` and a `ResultMessage` with only input/output. The `chat` and `invoke_agent` spans have no `gen_ai.usage.cache_*` keys, and input/output values equal today's.
- [ ] T2. Cache read only: `usage={"input_tokens": 3, "output_tokens": 5, "cache_read_input_tokens": 4000}`. The `chat` span has `gen_ai.usage.cache_read.input_tokens == 4000`, has no cache_creation key, and `input_tokens == 3` (not 4003).
- [ ] T3. Cache write only: `cache_creation_input_tokens: 1200`. The `chat` span has `gen_ai.usage.cache_creation.input_tokens == 1200` and no cache_read key.
- [ ] T4. Both dimensions across two result frames: the `invoke_agent` span sums each cache counter over frames, input/output sums are unchanged, and `input_tokens` excludes the cache counters. Update the existing `_result` fixture (which already sets `cache_read_input_tokens: 9`) and its root assertions.
- [ ] T5. Provider omits cache usage, or reports `None`, `"12"` or `True`: no cache attribute on any span, and no 0 is fabricated.
- [ ] T6. `tests/test_tracing.py`: add both keys to `test_catalog_keys_are_allowed`, and add a string-value refusal test like `test_a_string_under_a_usage_counter_is_refused` for each new key.
- [ ] T7. Privacy regression: the existing `_assert_no_payload` checks still pass on the stream with cache counters.
- [ ] T8. `uv run pytest tests/test_tracing.py tests/test_tracing_agents.py tests/test_usage_ledger*.py` passes. The ledger tests are unchanged, which shows its semantics did not move.

## Rollback

Revert the PR, or roll the worker image back to the previous mctl-agents tag. The change only adds span attributes, with no data migration, ledger change or config change, so a revert just removes the two attributes from new spans. If only the export is a problem (for example, Collector masking noise), removing the two keys from `_USAGE_TOKEN_KEYS`/`_ALLOWED_KEY` stops them leaving the process without touching the observer.
