# Mount the usage price catalog ConfigMap and set USAGE_PRICING_CATALOG

## Context

`cmd/api/main.go` already knows how to price usage records: when
`USAGE_PRICING_CATALOG` names a readable file it calls
`usage.LoadCatalogFile` (`internal/usage/catalog_file.go`) and hands the
resulting `*usage.Catalog` to `usage.NewStore`, which derives
`calculated_cost` and stamps `pricing_version` on every ingested row
(`internal/usage/store.go`). The rate card deliberately lives outside the
binary — a published price is a fact about the world with an effective
date, and `docs/model-usage-ledger.md` spells out why baking one in would
be wrong.

The rate card now exists on the platform side: `mctlhq/mctl-gitops#1409` /
PR `mctlhq/mctl-gitops#1421` add ConfigMap `mctl-api-usage-pricing` in
namespace `mctl-api`, key `catalog.json`, holding the card in the
`internal/usage/pricing.go` `Pricing` schema. Nothing delivers it to the
process: `helm/values.yaml` has no value for it, `helm/templates/deployment.yaml`
has neither the env var nor a volume, and so `os.Getenv("USAGE_PRICING_CATALOG")`
is empty, no catalog is loaded, and every usage row carries a null
`calculated_cost`. This proposal closes exactly that gap in the chart —
one opt-in value that mounts the ConfigMap read-only and points the env
var at the mounted file.

## User stories

- AS a platform operator I WANT to name a ConfigMap in the chart values SO
  THAT mctl-api loads the versioned rate card and the usage ledger derives
  `calculated_cost` without a code change or an image rebuild.
- AS a platform operator I WANT the value empty by default SO THAT shipping
  this chart version changes nothing for any existing deployment.
- AS a platform operator I WANT a missing or unreadable ConfigMap to degrade
  rather than block SO THAT a rate-card mistake never keeps the control-plane
  API from starting.
- AS a reviewer I WANT a chart render test SO THAT the env var, the mount path
  and the read-only flag cannot silently drift apart from each other or from
  `usage.LoadCatalogFile`'s expectations.

## Acceptance criteria (EARS)

- WHEN `usagePricingConfigMap` is set to a non-empty ConfigMap name THE SYSTEM
  SHALL render, on the `mctl-api` container, an env var `USAGE_PRICING_CATALOG`
  whose value is `/etc/mctl-api/usage-pricing/catalog.json`.
- WHEN `usagePricingConfigMap` is set THE SYSTEM SHALL render a pod volume
  sourced from that ConfigMap and a container `volumeMount` of that volume at
  `/etc/mctl-api/usage-pricing` with `readOnly: true`.
- WHEN `usagePricingConfigMap` is set THE SYSTEM SHALL project the ConfigMap key
  given by `usagePricingConfigMapKey` (default `catalog.json`) to the file name
  `catalog.json` inside the mount directory, so that the rendered
  `USAGE_PRICING_CATALOG` path resolves to that key's content.
- WHEN `usagePricingConfigMap` is set THE SYSTEM SHALL mark the ConfigMap volume
  source `optional: true`.
- WHILE `usagePricingConfigMap` is empty (the default) THE SYSTEM SHALL render a
  Deployment byte-identical to the render with the value absent: no
  `USAGE_PRICING_CATALOG` env, no usage-pricing volume, no usage-pricing
  `volumeMount`.
- IF the named ConfigMap or its key is absent at pod start THEN THE SYSTEM SHALL
  still start the container, and `cmd/api/main.go` SHALL log
  `usage pricing catalog failed to load` at ERROR and record usage without a
  derived cost, exactly as it does today with an unreadable path.
- IF the mounted catalog parses THEN THE SYSTEM SHALL, for a newly ingested
  record matching a card, store a non-null `calculated_cost` together with the
  card's `pricing_version` (e.g. `2026-09-01-firstparty-1` for
  `claude-opus-5`).
- WHEN the chart is rendered with a `usagePricingConfigMap` value THE SYSTEM
  SHALL keep the existing volumes and mounts (`gitops-cache`, `roadmap-state`,
  `gitops-ssh`, `github-app-token`, `cnpg-ca`) unchanged.

## Out of scope

- The mctl-gitops change itself. Setting
  `usagePricingConfigMap: mctl-api-usage-pricing` in
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` is a
  one-line follow-up in `mctlhq/mctl-gitops` after this chart version ships,
  and the PR description must say so.
- Creating, editing or validating the `mctl-api-usage-pricing` ConfigMap or the
  rate values in it — that is `mctlhq/mctl-gitops#1409`.
- Any change to `internal/usage/*` (loader, catalog resolution, store schema)
  or to `cmd/api/main.go`'s catalog wiring. Those already work; only the
  chart is missing.
- Hot reload of the catalog. The catalog is read once at startup; a rate-card
  change still needs a pod restart. Watching the file is a separate concern.
- Backfilling `calculated_cost` on rows already ingested without a catalog.
  ADR-012 invariant 7 makes that a deliberate backfill, not a side effect of
  mounting a file.
- Making the catalog mandatory (failing readiness when it is absent).

## Open questions

- Exact mount directory and file name. The issue proposes
  `/etc/mctl-api/usage-pricing/catalog.json`; this proposal adopts it verbatim.
  No other chart path lives under `/etc/mctl-api`, so the prefix is new but
  consistent with `/etc/gitops-ssh` and `/etc/cnpg`.
- Whether the ConfigMap key should be configurable. The issue fixes it at
  `catalog.json`. This proposal adds `usagePricingConfigMapKey` defaulting to
  `catalog.json`, mirroring the existing `githubAppTokenKey` and
  `postgresCA.key` precedents; the default means the gitops follow-up stays a
  single line. If a reviewer prefers zero new surface, drop the key value and
  hardcode `catalog.json` — nothing else in the design depends on it.
- How the chart render test runs in CI. `.github/workflows/validate.yml` has no
  Helm step today, so the test needs `helm` on the runner. This proposal adds a
  `setup-helm` step to the existing `test` job and makes the test skip only
  when `CI` is unset, so it can never pass vacuously in CI. If the reviewer
  would rather not touch CI, the fallback is a pure-Go assertion over
  `helm/templates/deployment.yaml` text, which is weaker.
- Whether `docs/model-usage-ledger.md` should document the chart value. This
  proposal says yes (one table row plus two sentences), because the current
  Configuration table says "Path to a JSON rate-card file" with no hint of how
  that path comes to exist in production.
