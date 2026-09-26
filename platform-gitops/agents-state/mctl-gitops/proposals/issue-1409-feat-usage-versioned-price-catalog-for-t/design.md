# Design: issue-1409-feat-usage-versioned-price-catalog-for-t

## Current state

**mctl-api is deployed from an external chart.** `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`
is an ArgoCD `Application` whose only source is `repoURL https://github.com/mctlhq/mctl-api.git`,
`targetRevision: main`, `path: helm`, with inline `helm.values`. Everything this
repository controls about the pod is therefore whatever that chart's values
surface accepts, plus raw manifests applied into the `mctl-api` namespace by
root-app (`platform-gitops/bootstrap/templates/bootstrap/root-app.yaml`,
`path: platform-gitops/bootstrap`).

Verified against the upstream chart (`mctl-api` `helm/values.yaml` and
`helm/templates/deployment.yaml`, read at `main`):

- The values surface has `image`, `ingress`, `resources`, `env` (a free-form map
  rendered as literal env vars), `envFromSecret`, `envFromExtraSecret`,
  `openclaw.*`, and exactly four optional file mounts: `postgresCA`,
  `gitopsSSHSecret`, `githubAppTokenSecret` (+ `githubAppTokenKey`) and
  `usageWriterTokenSecret` (env-only, via `secretKeyRef`).
- There is **no** `configMaps`, `extraVolumes`, `extraVolumeMounts` or
  `extraObjects` value. The chart's `volumes:` block is a closed list:
  `gitops-cache` (emptyDir 500Mi), `roadmap-state` (emptyDir 64Mi) and the three
  conditional secret volumes. This is the same limitation already documented in
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-api-netpol.yaml`
  ("an external chart (mctl-api repo helm/) that has no extraObjects hook; this
  is the same pattern as mctl-api-rbac.yaml and mctl-api-monitor.yaml").
- There is no ConfigMap checksum pod annotation, so a ConfigMap edit alone never
  restarts the pod. This repo's existing workaround is the `ROLLOUT_MARKER` env
  var in `mctl-api.yaml` (comment at lines 31-38).

**The consumer side.** `cmd/api/main.go` (usage-ledger block) reads
`USAGE_PRICING_CATALOG`; if set, it calls `usage.LoadCatalogFile(path)`, and on
error logs `usage pricing catalog failed to load; usage will be recorded without
calculated cost` and continues with a nil catalog. `internal/usage/catalog_file.go`
expects a **JSON array** of `Pricing` objects. `internal/usage/pricing.go`
rejects an entry with no `version`, no `canonical_model` or no `effective_from`,
rejects a duplicate (model, provider, `effective_from`) triple, lower-cases model
and provider for lookup, resolves by instant and provider (a card with an empty
provider is a wildcard), and `Calculate` prices `input + output + cache_read +
cache_write` per million tokens plus `web_search_requests * web_search_per_call`,
writing `calculated_cost` and `pricing_version` onto the record at ingest only.
Provider constants are `firstParty`, `bedrock`, `vertex` (`internal/usage/types.go`).

**Nothing in this repository sets `USAGE_PRICING_CATALOG`** (grep over
`platform-gitops/` finds no occurrence), and the image already in production —
`image.tag: "4.54.0"` — does contain `internal/usage/catalog_file.go` (verified at
tag `4.54.0`). So no image bump is needed; only a file, a ConfigMap, a mount and
one env var.

**The pilot's models, from this repo.** `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`
pins `ISSUE_INVESTIGATOR_MODEL: claude-opus-5`.
`platform-gitops/agent-platform/execution-profiles/issue-investigator-default/profile.yaml`
records that this env var outranks the `service_agent` task, whose `balanced`
profile is `claude-sonnet-5` (mctl-agents `config/model-policy.yaml`), which is
what the implementer, the shepherd's implementer invocations and the incident
responder run (`cwft-mctl-agents-run.yaml` explains why
`INCIDENT_RESPONDER_MODEL` is deliberately unset). The `cheap` profile is
`claude-haiku-4-5` (mentor digest, review-findings normalisation) — one of the two
models the issue reports seeing in the ledger.

## Proposed solution

Four pieces, two repositories. The mctl-gitops side is self-contained and
reviewable on its own; the one-line chart hook is the only cross-repo dependency.

### 1. The catalog document (this repo, canonical)

`platform-gitops/bootstrap/files/usage-pricing/claude-firstparty.json` — a JSON
array of three `Pricing` entries. It lives **inside the bootstrap chart
directory** because that is the only way a Helm template can read it with
`.Files.Get`; `.Files` cannot reach outside the chart. Content (USD per million
tokens, provider `firstParty`, `effective_from: 2026-09-01T00:00:00Z`,
`version: 2026-09-01-firstparty-1`):

| canonical_model | input | output | cache_write (5m) | cache_read | web_search_per_call |
| --- | --- | --- | --- | --- | --- |
| `claude-opus-5` | 5.00 | 25.00 | 6.25 | 0.50 | 0.01 |
| `claude-sonnet-5` | 2.00 | 10.00 | 2.50 | 0.20 | 0.01 |
| `claude-haiku-4-5` | 1.00 | 5.00 | 1.25 | 0.10 | 0.01 |

Source for every figure, to be cited in the README next to the file:
`https://platform.claude.com/docs/en/about-claude/pricing`, retrieved 2026-09-26
— "Model pricing" table for base input / 5m cache writes / cache hits and
refreshes / output tokens, and "Specific tool pricing -> Web search tool" for
"$10 per 1,000 searches" (hence `0.01` per call, the unit `Pricing` uses).

`effective_from: 2026-09-01T00:00:00Z` is not arbitrary: the same page's footnote
3 records that Claude Sonnet 5's $2/$10 became the standard price on 2026-09-01
(the scheduled increase to $3/$15 did not occur), and the ledger's first rows are
from 2026-09-24, when `usageWriter.enabled` was flipped. Every pilot row
therefore resolves to this card, and the date is defensible from the cited page
rather than invented. `cache_write` uses the 5-minute column because
`usage.Record` has one undifferentiated `CacheWriteTokens` counter and nothing in
mctl-agents sets a `cache_control` TTL, so the SDK default (5m) applies.

A sibling `README.md` in the same directory carries: one line per rate with its
source page, section and retrieval date; the append-only rule (a price change
adds a card with a later `effective_from` and a new `version`, never edits one,
per ADR-012 invariant 7); the 5m-cache-write assumption; and the restart
requirement below.

### 2. The ConfigMap (this repo)

`platform-gitops/bootstrap/templates/mctl-platform/mctl-api-usage-pricing.yaml`,
a raw manifest in namespace `mctl-api` rendered by root-app — the established
pattern for objects the external chart cannot render (`mctl-api-netpol.yaml`,
`mctl-api-rbac.yaml`, `mctl-api-monitor.yaml`, `mctl-api-secrets.yaml`). Its
single key `catalog.json` is filled with
`{{ .Files.Get "files/usage-pricing/claude-firstparty.json" | nindent 4 }}`, so
the committed JSON is the one source of truth and the template holds no second
copy that could drift.

### 3. The mount (mctl-api chart, cross-repo)

Add one narrow optional value to `mctl-api/helm`, in the style of the four mounts
that already exist there:

```yaml
# Optional: mount a versioned usage price catalog (mctlhq/.github#50).
# When set, mounts the named ConfigMap's key at
# /etc/mctl-api/usage-pricing/catalog.json and sets USAGE_PRICING_CATALOG.
usagePricingCatalog:
  configMapName: ""
  key: catalog.json
```

rendering a `configMap` volume (whole-directory mount, not `subPath`, so kubelet
keeps the file current), a read-only `volumeMount` at
`/etc/mctl-api/usage-pricing`, and `USAGE_PRICING_CATALOG` pointing at the file.
`defaultMode: 0444` for the same reason the chart's own comments give for
`githubAppTokenSecret` and `postgresCA`: the chart sets no `securityContext` and
the image runs as uid 1000. A ConfigMap, not a Secret — a published rate is
public, and the file is already in git.

This needs a companion issue on mctlhq/mctl-api. Because the Application tracks
`targetRevision: main` for the chart, merging there is enough; no `image.tag`
bump is required (4.54.0 already loads the catalog).

### 4. Wiring and restart (this repo)

In `mctl-api.yaml`'s inline values: `usagePricingCatalog.configMapName:
mctl-api-usage-pricing`, and bump `ROLLOUT_MARKER` in the same commit — the
comment there already explains that this is how GitOps restarts the pod, and a
catalog read once at startup is exactly the case that needs it. Setting
`USAGE_PRICING_CATALOG` explicitly under `env:` is unnecessary (the chart sets
it) and is deliberately avoided so the path is defined in one place.

Sequencing matters and mirrors the `LIFECYCLE_DB_URL` precedent in the same file
(#1245): land the catalog file + ConfigMap first, let root-app sync, then land the
values + `ROLLOUT_MARKER` commit. A pod that restarts against a `configMapName`
whose ConfigMap has not synced yet would fail to mount and CrashLoop, which is
strictly worse than the current no-cost state. Two commits, or one PR with the
chart value added only after the ConfigMap is observed live.

### CI

Extend `.github/workflows/validate-manifests.yml` with a step modelled on the
existing "Render and validate the usage-writer overlay (.github#50)": render
`platform-gitops/bootstrap`, assert the `mctl-api-usage-pricing` ConfigMap and
the `usagePricingCatalog` value appear, run the rendered output through
kubeconform, and validate the committed JSON itself (parses as an array; every
entry has `version`, `canonical_model`, `effective_from`; no duplicate
(model, provider, `effective_from`) triple; every rate is a non-negative number).
That last check is the local mirror of `usage.NewCatalog`'s own validation, so a
malformed card fails the PR instead of degrading a production pod to a log line.

## Alternatives

**A. Point `USAGE_PRICING_CATALOG` at the in-pod gitops clone.** mctl-api already
clones this repository into `/data/mctl-gitops` (`GITOPS_LOCAL_PATH`), so
committing the catalog anywhere in the repo would eventually make it visible at
`/data/mctl-gitops/<path>` with **no chart change at all** — a pure one-file,
one-env-var GitOps change. Dropped: `LoadCatalogFile` runs once during startup in
`main.go`, while the clone is lazy and owned by a different subsystem whose
volume is an `emptyDir` recreated on every restart. At startup the file is
reliably absent, the catalog load fails, and the process keeps a nil catalog for
the pod's whole life — which is precisely the acceptance criterion this issue
sets ("no usage pricing catalog failed to load log line"). It would also make
pricing depend on the clone credential.

**B. Reuse an existing optional mount.** `postgresCA` mounts a Secret key at
`/etc/cnpg/ca.crt` and `gitopsSSHSecret` at `/etc/gitops-ssh/`, both already in
the chart. Stuffing the catalog JSON into one of those keys needs no chart
change. Dropped outright: it puts a rate card in a slot whose name promises a CA
certificate, occupies a value a real TLS upgrade needs, and hides public data in a
Secret. The confusion cost lands on whoever next debugs database TLS.

**C. Bake the catalog into the mctl-api image.** A default rate card compiled in
or shipped in the image with a default path. Dropped, and the code says why:
`catalog_file.go`'s own doc comment ("baking one into a binary means a price
change needs a release, and a wrong constant silently produces plausible-looking
money"). It also removes the rates from owner review in GitOps.

**D. Generic `configMaps`/`extraVolumes` hooks in the mctl-api chart**, like
`base-service` has. More flexible than the narrow `usagePricingCatalog` value.
Dropped for now: the chart's deliberate style is one named, commented mount per
purpose, and a generic hook is a wider blast radius than this issue needs. If a
second file mount is ever wanted, that is the moment to generalise.

## Platform impact

- **Migrations:** none. No schema change, no back-fill. `Calculate` runs at ingest
  only, so rows recorded before the rollout keep `calculated_cost = NULL` and an
  empty `pricing_version` forever — which satisfies "no existing ledger row is
  changed" and leaves a visible, honest before/after boundary in the data.
- **Backward compatibility:** `usagePricingCatalog.configMapName` defaults to
  `""`, so the chart change is inert for any other consumer, and an unset value
  reproduces today's behaviour exactly. Setting `USAGE_PRICING_CATALOG` cannot
  break unrelated endpoints: a bad file is logged and skipped by design.
- **Resource impact:** one ConfigMap of a few hundred bytes and one read-only
  volume. No CPU/memory change; the current limits (650m / 320Mi) are untouched.
- **Risk: CrashLoop on a missing ConfigMap.** A pod restarting with
  `configMapName` set before root-app has created the ConfigMap cannot mount and
  will not start. Mitigation: the two-step sequencing above, and the CI assertion
  that the ConfigMap renders. Rollback is a one-line revert.
- **Risk: wrong money that looks right.** A typo in a rate produces plausible
  costs on every new row, and those rows are never re-priced. Mitigations: the
  rates are stated in this proposal for owner review before merge; the README
  cites page, section and retrieval date per rate; the JSON is in the provider's
  published unit so no arithmetic is needed to check it; CI validates structure;
  and a correction is itself append-only (new `effective_from`, new `version`), so
  the mispriced window stays identifiable by `pricing_version`.
- **Risk: silently unpriced models.** A model or provider with no card yields
  `ErrNoPricing` and a row with no cost — the same state as today, never a wrong
  number. Detection is a query for post-rollout rows with `calculated_cost IS
  NULL`; the follow-up is another card, not a code change.
- **Risk: stale rates after a provider change.** Nothing here watches the
  provider's page. Accepted for the pilot; the README's append-only recipe plus a
  periodic owner check is the process answer, and #50's non-goal list already
  excludes invoice reconciliation that would have caught it automatically.
- **Operational note:** editing the catalog does not restart the pod on its own
  (no checksum annotation in the external chart), so every catalog-content change
  must bump `ROLLOUT_MARKER` in the same commit or the running pod keeps pricing
  from the old card.
