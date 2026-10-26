# Usage ledger: record provider and price source for third-party models

## Context

Spike #791 (verdict `ADOPT_EXPERIMENTAL_PROVIDER`, `docs/spikes/791-hetzner-inference.md`, follow-up 3) found
two accounting gaps that would corrupt the model-usage ledger (ADR-012) once an experimental Hetzner lane runs
the Claude Code CLI against `ANTHROPIC_BASE_URL=https://inference.hetzner.com/api`:

1. The CLI reports a non-zero `total_cost_usd` / `ModelUsage.costUSD` for Hetzner models. That is the CLI's own
   list-price estimate for a model it does not know. The provider charges $0 in the experimental phase.
2. The Messages `usage.input_tokens` excludes `cache_creation_input_tokens` (about 58k on the spike's
   long-context probe), so reading `input_tokens` alone under-counts the prompt.

Today the producer `orchestrator/usage_ledger.UsageRecorder` sends no cost. mctl-api prices the token counts
from its versioned catalog at ingest (ADR-012, amendment 2026-09-24). It copies `provider` verbatim from the
CLI's `ModelUsage.provider`, which describes the CLI's transport (`firstParty`, `bedrock`, ...). It cannot know
that `ANTHROPIC_BASE_URL` points at a third party. Nothing in the record says where its price comes from. A
Hetzner row would therefore look like a first-party Anthropic row, and mctl-api could price it with an
Anthropic price table. This proposal makes every usage record say who served it and where its price comes
from, before any experimental lane is allowed to write usage.

## User stories

- AS a platform operator reading `mctl_get_usage_summary` I WANT each row to say which provider served the
  tokens and where its price comes from SO THAT free experimental-provider usage is never summed into Anthropic
  spend.
- AS the owner of ADR-012 I WANT a CLI price estimate to never reach the ledger as a cost for a third-party
  model SO THAT an estimate is never laundered into a billing claim.
- AS an engineer comparing lanes I WANT the cache-creation share of the prompt recorded for every model
  SO THAT the full input token count of a third-party session can be reconstructed.

## Acceptance criteria (EARS)

- WHEN the recorder builds a record for a session whose model endpoint is a third-party provider THE SYSTEM
  SHALL set `provider` to that provider's id (e.g. `hetzner`) instead of the CLI-reported `ModelUsage.provider`.
- WHEN the recorder builds a record for a third-party provider THE SYSTEM SHALL set `price_source` to a value
  from the closed vocabulary {`mctl_catalog`, `provider_free`, `unknown`} that the lane declared, and never to
  `mctl_catalog`.
- WHEN the recorder builds a record for a default (Anthropic, no base-URL override) session THE SYSTEM SHALL
  keep `provider` from `ModelUsage.provider` as today, and its record SHALL be unchanged from today's records.
  `price_source` is omitted and means `mctl_catalog`.
- IF the process or the session environment points `ANTHROPIC_BASE_URL` at a host other than the Anthropic API
  AND no explicit provenance was declared THEN THE SYSTEM SHALL record `provider=unknown` and
  `price_source=unknown` and log one warning. It SHALL NOT fall back to the CLI-reported provider.
- WHEN a session's own options env (`ClaudeAgentOptions.env`, as passed to `tracing.agent_run`) points
  `ANTHROPIC_BASE_URL` at a non-Anthropic host AND no provenance was declared THE SYSTEM SHALL treat it
  exactly like a process-level override (`unknown`/`unknown`, one warning). The session env SHALL take
  precedence over `os.environ` for detection, because the provider seam of mctlhq/mctl-agents#824 sets the
  base URL only in the options env.
- WHILE recording any record THE SYSTEM SHALL NOT include `ModelUsage.costUSD`, `ResultMessage.total_cost_usd`
  or any value derived from them in any field, including `calculated_cost`, `provider_reported_cost`,
  `pricing_version` and `invoice_reconciled_cost`.
- WHEN a model bucket reports `cacheCreationInputTokens` THE SYSTEM SHALL record it as `cache_write_tokens` for
  every provider, so that the record's total input count is `input_tokens + cache_read_tokens +
  cache_write_tokens`.
- IF a third-party bucket reports `inputTokens` but no `cacheCreationInputTokens` THEN THE SYSTEM SHALL leave
  `cache_write_tokens` absent (never 0), per the ADR-012 absent-versus-zero rule.
- WHEN `orchestrator/run_usage_collector.py` forwards an artifact record that carries `price_source` THE
  SYSTEM SHALL forward it unchanged if it is in the vocabulary, and drop it with a warning otherwise.
- WHEN a model span is emitted for a third-party session THE SYSTEM SHALL set `gen_ai.provider.name` to the
  resolved provider instead of the hard-coded `anthropic`.

## Out of scope

- The provider seam in `config/model-policy.yaml` (spike follow-up 1) and per-model reasoning effort
  (follow-up 2). This proposal only consumes a declared provenance.
- The mctl-api side, which lives in `mctlhq/mctl-api`: accepting and storing `price_source`, and not applying
  the Anthropic price table to rows whose `price_source` is not `mctl_catalog`. It is recorded as a dependency.
- Future Hetzner pricing. `provider_free` is today's observed fact. A paid tier would need a new price source
  and catalog entry.
- Changing the meaning of the ledger's `input_tokens` field for existing Anthropic rows, and backfilling or
  rewriting stored rows.
- Rewriting the committed spike #791 artifacts.

## Decisions (owner review, 2026-10-27)

- Cache-creation tokens (human-input request `hir-95c5323867a3b06b`): **keep ADR-012's separate counters.**
  `cache_write_tokens` carries cache creation, and the total input is
  `input_tokens + cache_read_tokens + cache_write_tokens`. `input_tokens` is not made inclusive, because that
  would double-bill against `cache_write_tokens`.
- `provider_free` stays in the vocabulary. Which value the Hetzner lane declares (`provider_free` or `unknown`)
  is decided at adoption. Until mctl-api supports `price_source`, no lane declares third-party provenance.
- How a #824 `ProviderSpec` turns into a declared `ModelProvenance` is adoption work, not this change. This
  change only guarantees that an undeclared provider session fails closed to `unknown`/`unknown`.

## Open questions

- Not yet observed: whether the CLI's `model_usage` (not just the raw Messages `usage`) carries
  `cacheCreationInputTokens` for Hetzner models. The spike recorded `ResultMessage.usage.input_tokens` only.
- Not yet observed: how mctl-api's ingest treats an unknown `price_source` field (rejects the batch or ignores
  the field), and how it prices a `canonical_model` missing from its catalog. Its source is not in this
  clone.
