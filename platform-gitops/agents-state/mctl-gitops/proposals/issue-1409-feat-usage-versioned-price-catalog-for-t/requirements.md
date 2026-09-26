# Versioned usage price catalog for the #50 pilot models, mounted into mctl-api

## Context

The FinOps usage ledger (mctlhq/.github#50, ADR-012) is live in production:
`usageWriter.enabled: true` in `platform-gitops/bootstrap/values.yaml` since
2026-09-24 renders the `mctl-api-usage-writer` ExternalSecret
(`platform-gitops/bootstrap/templates/mctl-platform/mctl-api-usage-writer.yaml`)
and hands the token to mctl-api through `usageWriterTokenSecret` in
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`. Agent runs
therefore append token counts. But mctl-api derives a cost only when
`USAGE_PRICING_CATALOG` names a readable rate-card file
(`cmd/api/main.go`, the `usage pricing catalog failed to load` branch), and no
manifest in this repository sets that variable. Production proves token
attribution and no cost attribution at all: every row carries
`calculated_cost = NULL` and an empty `pricing_version`.

This proposal adds the missing rate card as a reviewable, versioned GitOps
artifact and mounts it into the mctl-api pod. The rates are US dollars per
million tokens, exactly as the provider publishes them, so a reviewer can
compare the file against the provider's page without arithmetic
(`internal/usage/pricing.go`, type `Pricing`). Because `Catalog.Calculate` runs
once at ingest and stores both the number and the `Version` that produced it
(`internal/usage/pricing.go`), adding the catalog can only affect rows recorded
after it is loaded — no existing row is re-priced.

One constraint shapes the whole design: mctl-api does **not** use this
repository's `base-service` chart. Its ArgoCD Application renders the chart from
the mctl-api repository (`sources[0]: repoURL mctl-api.git, path helm`), and that
chart has no `configMaps`, `extraVolumes` or `extraVolumeMounts` values and no
`extraObjects` hook — the same fact already recorded in
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api-netpol.yaml`. Its
only file mounts are four purpose-built optional ones (`postgresCA`,
`gitopsSSHSecret`, `githubAppTokenSecret`, `usageWriterTokenSecret`). So the
catalog file and its ConfigMap belong here, and one narrow value must be added
to the mctl-api chart to mount it.

## User stories

- AS the platform owner I WANT every pilot usage row to carry a derived USD cost
  and the catalog version that produced it SO THAT #50 proves cost attribution,
  not only token attribution.
- AS a reviewer I WANT each rate in the catalog to cite the published source page
  it came from SO THAT I can verify the money without recomputing it.
- AS a platform engineer I WANT the catalog to live in GitOps as a versioned file
  SO THAT a provider price change is a reviewed commit, not a rebuild.
- AS an auditor I WANT a price change to add a new rate card rather than edit an
  existing one SO THAT historical costs stay reproducible (ADR-012 invariant 7).

## Acceptance criteria (EARS)

- WHEN the mctl-api pod starts with `USAGE_PRICING_CATALOG` pointing at the
  mounted catalog THE SYSTEM SHALL load it without emitting
  `usage pricing catalog failed to load`, and the usage ledger store SHALL be
  constructed with a non-nil `*usage.Catalog`.
- WHEN a usage record for `claude-opus-5`, `claude-sonnet-5` or
  `claude-haiku-4-5` with provider `firstParty` is ingested after the rollout
  THE SYSTEM SHALL store a non-null `calculated_cost` and the catalog's
  `pricing_version`.
- WHILE the catalog is loaded THE SYSTEM SHALL leave every usage row recorded
  before the rollout unchanged — no back-fill, no re-pricing, `calculated_cost`
  and `pricing_version` are written only at ingest.
- WHERE a rate appears in the catalog THE SYSTEM SHALL carry, in the README next
  to the file, the provider page URL, the retrieval date and the table the figure
  was read from, one line per rate.
- WHEN the catalog document is rendered into the ConfigMap THE SYSTEM SHALL
  produce byte-identical JSON to the committed file — the committed file is the
  single source, never a second copy inside a template.
- IF the catalog file is malformed, absent, or contains two cards claiming the
  same (canonical model, provider, `effective_from`) triple THEN THE SYSTEM SHALL
  keep serving every other API endpoint and record usage without a derived cost
  (`main.go` deliberately logs and continues; `NewCatalog` rejects the duplicate).
- WHEN a provider publishes a new rate THE SYSTEM SHALL express it as an
  additional entry with a later `effective_from` and a new `version`, and SHALL
  NOT edit an existing entry.
- WHEN the catalog's content changes THE SYSTEM SHALL require an explicit pod
  restart marker bump (`ROLLOUT_MARKER` in `mctl-api.yaml`) in the same commit,
  because mctl-api reads the file once at startup and the mctl-api chart renders
  no ConfigMap checksum annotation.
- WHILE the change is on a pull request THE SYSTEM SHALL fail CI if the rendered
  bootstrap output lacks the pricing ConfigMap or the chart value that mounts it,
  mirroring the existing `.github#50` usage-writer overlay assertion in
  `.github/workflows/validate-manifests.yml`.

## Out of scope

- Invoice reconciliation and the `invoice_reconciled_cost` column (#50 non-goal).
- Rates for any provider other than `firstParty` (`bedrock`, `vertex`) and for
  models outside the pilot set, including Batch API, fast-mode, 1-hour-cache and
  `inference_geo: "us"` multipliers.
- Back-filling or re-pricing existing ledger rows, and any re-pricing endpoint.
- Changing what the producers send (`orchestrator/usage_ledger.py` in
  mctl-agents) or which models the agents run.
- Dashboards, alerts or budget enforcement on the derived cost.

## Open questions

- **Cache-write TTL.** `usage.Record` has a single `CacheWriteTokens` counter and
  `Pricing` a single `cache_write_per_mtok`, but the provider publishes two write
  rates (5-minute 1.25x input, 1-hour 2x input). No `cache_control` TTL is set
  anywhere in mctl-agents, so the SDK default (5 minutes) is assumed and the 5m
  column is used. If a runner later opts into a 1-hour cache, cache writes are
  under-priced by 1.6x until a new card is added. Recorded, not blocking.
- **Records without `canonical_model`.** `Catalog.Calculate` falls back to
  `ModelKey` when `canonical_model` is absent, and `model_key` is the dated key
  as served (e.g. `claude-opus-5-20260401`). Such a row gets no price
  (`ErrNoPricing`). The producer does send `canonicalModel` when the SDK reports
  it (`orchestrator/usage_ledger.py`), so this is expected to be rare; the
  optional alias-card task covers it once a real unpriced `model_key` is observed
  in the ledger.
- **`version` granularity.** This proposal uses one publication version string
  shared by the three cards (`2026-09-01-firstparty-1`), so `pricing_version`
  answers "which catalog publication priced this row". A per-model version would
  answer "which card" instead. Owner may prefer the latter; changing it later is
  additive (new cards, new version).
- **Which models the pilot actually runs.** Grounded in this repo:
  `claude-opus-5` (`ISSUE_INVESTIGATOR_MODEL` in
  `cwft-mctl-agents-investigate.yaml`), `claude-sonnet-5` (profile `balanced` in
  mctl-agents `config/model-policy.yaml`, used by the implementer, the shepherd's
  implementer invocations and the incident responder) and `claude-haiku-4-5`
  (profile `cheap`: mentor digest, review-findings normalisation). The reviewer
  tiers in `mctlhq/.github` `claude-review.yml` resolve to the same three
  (`model-high: claude-opus-5`, `model-mid`/`model-low: claude-sonnet-5`), but
  those runs bill against GitHub Actions, not this ledger. Any fourth model that
  appears in the ledger needs a follow-up card.
