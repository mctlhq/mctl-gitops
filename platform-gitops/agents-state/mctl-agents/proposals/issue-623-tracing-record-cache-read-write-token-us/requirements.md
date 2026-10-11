# Record cache read/write token usage on GenAI spans

## Context

Execution tracing (mctl-agents#195) puts a `chat <model>` span on each model message and an `invoke_agent <agent>` span on each SDK session. Both carry only `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens`. `orchestrator/tracing.py::_usage_counts` reads just those two keys from the SDK `usage` dict and throws away `cache_read_input_tokens` and `cache_creation_input_tokens`. The usage ledger, `orchestrator/usage_ledger.py`, already keeps both cache counters (`_COUNTERS`: `cacheReadInputTokens -> cache_read_tokens`, `cacheCreationInputTokens -> cache_write_tokens`). In the live DevLoop trace `e60f96e049e77d9b181c694936570f57`, most Opus input was served from cache, so the trace showed 16 input tokens across 8 calls. That is a large under-report.

The issue asks the existing GenAI tracing path to keep the provider's cache-read and cache-write counters as span attributes, so traces and the ledger cover the same usage dimensions. Accounting semantics stay unchanged, nothing is double-counted, and no payload is added. This is the last token-usage item blocking mctl-agents#195.

## User stories

- AS a platform operator reading a DevLoop trace in Tempo I WANT each `chat` and `invoke_agent` span to show cache-read and cache-write tokens next to input/output tokens SO THAT I can see the real model usage of a run.
- AS the maintainer of #195 I WANT a deployed DevLoop trace with cache token attributes SO THAT the token-usage acceptance criterion can be closed.
- AS a security reviewer I WANT the new attributes limited to integer counters that pass the existing redaction allowlist SO THAT no prompt, completion or credential can reach a span.

## Acceptance criteria (EARS)

- WHEN an SDK `AssistantMessage.usage` mapping contains an integer `cache_read_input_tokens` THE SYSTEM SHALL set `gen_ai.usage.cache_read.input_tokens` to that value on the message's `chat` span.
- WHEN an SDK `AssistantMessage.usage` mapping contains an integer `cache_creation_input_tokens` THE SYSTEM SHALL set `gen_ai.usage.cache_creation.input_tokens` to that value on the message's `chat` span.
- WHEN `ResultMessage.usage` frames contain either cache counter THE SYSTEM SHALL set the matching attribute on the `invoke_agent` span. The value SHALL be summed over result frames in the same way as `gen_ai.usage.input_tokens` today.
- WHILE recording cache attributes THE SYSTEM SHALL keep `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` byte-for-byte as they are computed today. Cache counters SHALL never be added to `input_tokens`.
- IF the provider omits a cache counter, or reports it as a non-integer or a bool, THEN THE SYSTEM SHALL leave that attribute absent. It SHALL NOT be written as 0. On `invoke_agent`, a cache attribute SHALL appear only if at least one result frame reported that counter.
- IF a cache counter is reported as an integer 0 THEN THE SYSTEM SHALL record 0. This follows the existing input/output convention, where any reported integer is recorded.
- WHEN span attributes are exported THE SYSTEM SHALL let the two new keys through `orchestrator/tracing_sdk.redact_attributes` only as integers. A string or bool under either key SHALL be dropped.
- THE SYSTEM SHALL NOT add prompts, completions, tool inputs or outputs, credentials, or any other new non-counter attribute to spans as part of this change.
- THE SYSTEM SHALL NOT change `orchestrator/usage_ledger.py` records, pricing, or any metric labels.
- WHEN a real DevLoop runs on the deployed workers after release THE SYSTEM SHALL produce `chat` spans in Tempo that carry the cache attributes. That trace is the remaining token-usage evidence for mctl-agents#195.

## Out of scope

- Changes to usage-ledger accounting, cost calculation or pricing semantics.
- New metrics, or metric labels of any cardinality.
- The nested `usage.cache_creation.{ephemeral_5m_input_tokens, ephemeral_1h_input_tokens}` TTL breakdown, `server_tool_use`, and web-search counters.
- Providers or code paths that do not expose cache usage. Only the Claude Agent SDK observer exists today.
- The Collector's `.*token.*` masking (mctl-gitops#1332), which is a gitops change tracked separately. This proposal only notes that it must also cover the new keys.
- Fixing whether `ResultMessage.usage` is per-turn or cumulative. The existing summation is kept as-is for all dimensions.

## Open questions

- **Attribute names.** The issue asks for `gen_ai.usage.*` attributes. ADR-012 (`docs/adr/012-model-usage-cost-attribution-contract.md`, "OpenTelemetry mapping") says cache tokens have "no stable upstream attribute" and should use an mctl-owned `mctl.gen_ai.usage.cache_*` name. This proposal follows the issue and uses the OTel GenAI development-status names `gen_ai.usage.cache_read.input_tokens` and `gen_ai.usage.cache_creation.input_tokens`. It also amends ADR-012's table to match. If reviewers would rather keep the ADR as written, the only changes are the two names: `mctl.gen_ai.usage.cache_read_tokens` / `mctl.gen_ai.usage.cache_write_tokens`. These still need to be added to `_USAGE_TOKEN_KEYS`, because `_TOKEN_KEY` would otherwise drop them.
- Whether the Collector redaction fix (mctl-gitops#1332) already covers keys like `gen_ai.usage.cache_read.input_tokens` could not be checked from this clone. If it does not, the Tempo evidence will show `****` or nothing, and a follow-up gitops change is needed.
- The mctl-docs telemetry attribute catalog (`docs/reference/telemetry-attributes.md`) needs the two names reserved. That is a separate repo and PR.
