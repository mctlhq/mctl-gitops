# Usage ledger: record provider and price source for third-party models

## Context

Spike mctlhq/mctl-agents#791 (verdict `ADOPT_EXPERIMENTAL_PROVIDER`, `docs/spikes/791-hetzner-inference.md`,
follow-up 3) found two accounting gaps. Both would corrupt the model-usage ledger (ADR-012) once an
experimental Hetzner lane runs the Claude Code CLI against `ANTHROPIC_BASE_URL=https://inference.hetzner.com/api`:

1. For Hetzner models the CLI reports a non-zero `total_cost_usd` / `ModelUsage.costUSD`. That figure is the
   CLI's own list-price estimate for a model it does not know. The provider charges $0 in the experimental
   phase.
2. The Messages `usage.input_tokens` excludes `cache_creation_input_tokens` (about 58k on the spike's
   long-context probe), so `input_tokens` alone under-counts the prompt.

What the producer `orchestrator/usage_ledger.UsageRecorder` does today:
- It sends no cost. mctl-api prices the token counts from its versioned catalog at ingest (ADR-012, amendment
  2026-09-24).
- It already records `cacheCreationInputTokens` as `cache_write_tokens`.
- It copies `provider` verbatim from the CLI's `ModelUsage.provider`. That value describes the CLI's transport
  (`firstParty`, `bedrock`, ...), and the CLI has no way to know that `ANTHROPIC_BASE_URL` points at a third
  party.
- Nothing in the record says where its price comes from.

A Hetzner row would therefore look like a first-party Anthropic row. This proposal makes every record name the
provider that served it and where its price comes from, before any experimental lane may write usage.

## User stories

- AS a platform operator reading `mctl_get_usage_summary` I WANT each row to say which provider served the
  tokens and where its price comes from SO THAT free experimental-provider usage is never summed into Anthropic
  spend.
- AS the owner of ADR-012 I WANT a CLI price estimate never to reach the ledger as a cost for a third-party
  model SO THAT an estimate is never laundered into a billing claim.
- AS an engineer comparing lanes I WANT the cache-creation share of the prompt recorded for every model
  SO THAT the full input token count of a third-party session can be reconstructed.

## Acceptance criteria (EARS)

- WHEN the recorder builds a record for a session that has a declared third-party provenance THE SYSTEM SHALL
  set `provider` to the declared provider id (e.g. `hetzner`), not to the CLI-reported `ModelUsage.provider`.
- WHEN the recorder builds a record for a third-party provider THE SYSTEM SHALL set `price_source` to the
  value the lane declared, from the closed vocabulary {`mctl_catalog`, `provider_free`, `unknown`}. That value
  SHALL NOT be `mctl_catalog`.
- WHEN the recorder builds a record for a default session (Anthropic, no base-URL override) THE SYSTEM SHALL
  produce exactly today's record: `provider` from `ModelUsage.provider` and no `price_source` field. An absent
  `price_source` means `mctl_catalog`.
- IF the process environment or the session's options env points `ANTHROPIC_BASE_URL` at a host other than
  `api.anthropic.com` AND no provenance was declared THEN THE SYSTEM SHALL:
  - record `provider=unknown` and `price_source=unknown`;
  - log one warning;
  - not fall back to the CLI-reported provider.
- WHEN both env sources are present THE SYSTEM SHALL let the session env (`ClaudeAgentOptions.env`, as passed
  to `tracing.agent_run`) take precedence over `os.environ` for that detection. The provider seam of
  mctlhq/mctl-agents#824 sets the base URL only in the options env.
- WHILE recording any record THE SYSTEM SHALL NOT include `ModelUsage.costUSD`, `ResultMessage.total_cost_usd`
  or any value derived from them in any field. This covers `calculated_cost`, `provider_reported_cost`,
  `pricing_version` and `invoice_reconciled_cost`.
- WHEN a model bucket reports `cacheCreationInputTokens` THE SYSTEM SHALL record it as `cache_write_tokens`
  for every provider, third-party included. The record's total input count is then
  `input_tokens + cache_read_tokens + cache_write_tokens`.
- WHILE recording a third-party record THE SYSTEM SHALL keep `input_tokens` as the provider's
  non-cache input count, so that the columns mean the same thing as on Anthropic rows.
- IF a bucket does not report `cacheCreationInputTokens` THEN THE SYSTEM SHALL leave `cache_write_tokens`
  absent, never 0, per the ADR-012 absent-versus-zero rule.
- WHEN `orchestrator/run_usage_collector.py` forwards an artifact record that carries `price_source` THE
  SYSTEM SHALL forward a value that is in the vocabulary unchanged. It SHALL drop any other value with a
  warning, without failing the batch.
- WHEN a model span is emitted for a session with a declared or detected third-party provenance THE SYSTEM
  SHALL set `gen_ai.provider.name` to the resolved provider instead of the hard-coded `anthropic`.

## Out of scope

- The provider seam in `config/model-policy.yaml`: spike follow-up 1, mctlhq/mctl-agents#824, which is still
  unmerged. Per-model reasoning effort (follow-up 2) is also out. This proposal only consumes a declared
  provenance, and it fails closed when none is declared.
- The mctl-api side (`mctlhq/mctl-api`): accepting and persisting `price_source`, and pricing by it. That is
  recorded as a dependency.
- Future Hetzner pricing. `provider_free` is today's observed fact. A paid tier needs a catalog entry under
  `mctl_catalog`.
- Changing the meaning of the ledger's `input_tokens` field, and backfilling or rewriting stored rows.
- Rewriting the committed spike #791 artifacts.

## Decisions

- Cache-creation tokens (clarification request `hir-95c5323867a3b06b`, answered by the author): **keep
  ADR-012's separate counters.** `cache_write_tokens` carries cache creation, and the total input count is
  `input_tokens + cache_read_tokens + cache_write_tokens`. `input_tokens` is not made inclusive.
- Which value the Hetzner lane declares (`provider_free` or `unknown`) is decided when the lane is adopted.
  Until mctl-api supports `price_source`, no lane declares third-party provenance.

## Open questions

- Not yet observed: whether the CLI's `model_usage` carries `cacheCreationInputTokens` for Hetzner models. The
  spike recorded only `ResultMessage.usage`. The first lane run must confirm it. If the counter is missing, it
  stays absent rather than being guessed.
- Not yet observed: how mctl-api's ingest treats an unknown `price_source` field (it may reject the batch or
  ignore the field). Its source is not in this clone. Per the mctl-api#403 design, its catalog is keyed by
  `(model, provider, effective_from)`, so a `hetzner`/Qwen row should find no card and get a null
  `calculated_cost`. That was not verified against running code.
