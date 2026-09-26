# Usage pricing catalog

`claude-firstparty.json` is the versioned rate card mounted into mctl-api at
`/etc/mctl-api/usage-pricing/catalog.json` via the `mctl-api-usage-pricing`
ConfigMap (`../../templates/mctl-platform/mctl-api-usage-pricing.yaml`), read
by `internal/usage/pricing.go` (mctlhq/mctl-api) at startup
(`USAGE_PRICING_CATALOG`). It is the single source of truth for the file — the
ConfigMap template embeds it with `.Files.Get`, never a second copy.

Every figure below is US dollars per million tokens (`web_search_per_call` is
USD per call), read from
https://platform.claude.com/docs/en/about-claude/pricing, retrieved
2026-09-26.

| canonical_model | input | output | cache_write (5m) | cache_read | web_search_per_call | source |
| --- | --- | --- | --- | --- | --- | --- |
| `claude-opus-5` | 5.00 | 25.00 | 6.25 | 0.50 | 0.01 | "Model pricing" table (base input / 5m cache writes / cache hits and refreshes / output tokens) |
| `claude-sonnet-5` | 2.00 | 10.00 | 2.50 | 0.20 | 0.01 | "Model pricing" table |
| `claude-haiku-4-5` | 1.00 | 5.00 | 1.25 | 0.10 | 0.01 | "Model pricing" table |

`web_search_per_call: 0.01` for all three comes from the same page's
"Specific tool pricing -> Web search tool" section: $10 per 1,000 searches,
i.e. $0.01 per call.

## `effective_from` rationale

`effective_from: 2026-09-01T00:00:00Z` is not arbitrary: the pricing page's
footnote 3 records that Claude Sonnet 5's $2/$10 became the standard price on
2026-09-01 (the scheduled increase to $3/$15 did not occur), and the usage
ledger's first rows are from 2026-09-24, when `usageWriter.enabled` was
flipped on. Every pilot row therefore resolves to this one card.

## Cache-write assumption

The provider publishes two cache-write rates: 5-minute (1.25x input) and
1-hour (2x input). `usage.Record` has a single, undifferentiated
`CacheWriteTokens` counter, and nothing in mctl-agents sets a `cache_control`
TTL, so the Claude Agent SDK's default (5 minutes) applies. This card uses the
5-minute column. If a runner ever opts into a 1-hour cache, cache writes will
be under-priced by 1.6x until a new card accounts for it.

## Append-only rule (ADR-012 invariant 7)

A price change is a **new entry** with a later `effective_from` and a new
`version` — never an edit to an existing entry. `Catalog.Calculate` resolves a
record by the instant it was recorded and stores both the derived cost and the
`version` that produced it, so editing an existing entry in place would
silently change the meaning of every row already priced from it. `NewCatalog`
also rejects two entries that claim the same
(`canonical_model`, `provider`, `effective_from`) triple.

## Restart requirement

mctl-api reads this file once at startup (`LoadCatalogFile`) and the mctl-api
chart renders no ConfigMap checksum annotation, so editing this file's content
does not by itself restart the pod. Every commit that changes the catalog's
content must also bump `ROLLOUT_MARKER` in
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` in the same
commit, or the running pod keeps pricing from the old card.
