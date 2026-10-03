# Design: issue-403-feat-usage-mount-the-usage-price-catalog

## Current state

**The consumer already exists.** `cmd/api/main.go` lines ~338-376 wire the
usage ledger:

```go
var usageStore *usage.Store
usageDBURL := postgresURL(os.Getenv("USAGE_DB_URL"))
if usageDBURL == "" { usageDBURL = postgresURL(os.Getenv("AUDIT_DB_URL")) }
if usageDBURL != "" {
    var pricing *usage.Catalog
    if path := os.Getenv("USAGE_PRICING_CATALOG"); path != "" {
        pc, pcErr := usage.LoadCatalogFile(path)
        if pcErr != nil {
            slog.Error("usage pricing catalog failed to load; usage will be recorded without calculated cost", "error", pcErr)
        } else { pricing = pc }
    }
    us, usErr := initStore(initCtx, storeFailures, "usage ledger", ...)
    ...
}
```

Three facts follow from that block and matter for this design:

1. The variable is a **path to a file**, read with `os.ReadFile` in
   `internal/usage/catalog_file.go` (`LoadCatalogFile`, with a scoped
   `#nosec G304` justified by "supplied by the operator in the deployment
   manifest"). So the delivery mechanism must be a volume, not an env value
   carrying JSON.
2. An **unset variable and an unreadable file are both non-fatal**. Unset means
   no catalog; unreadable means an ERROR log and no catalog. Either way the
   store is still created and every token count is still recorded. The chart
   must not turn that graceful degradation into a pod that cannot start.
3. The content must parse as the JSON array of `usage.Pricing`
   (`internal/usage/pricing.go`) that `ParseCatalog` expects — which is exactly
   the schema the gitops ConfigMap is documented to hold.

`internal/usage/store.go` is the other half: the schema has
`calculated_cost NUMERIC`, `pricing_version TEXT NOT NULL DEFAULT ''` and the
constraint `calculated_cost_requires_version` (`CHECK (calculated_cost IS NULL
OR pricing_version <> '')`), and line ~252 logs
`usage record stored without calculated cost: no pricing card matched`. With no
catalog every row takes the null-cost path.

**The chart is the missing piece.** `helm/values.yaml` (104 lines) has
`envFromSecret`, `envFromExtraSecret`, `gitopsSSHSecret`, `githubAppTokenSecret`
+ `githubAppTokenKey`, `postgresCA.{secretName,key}`, `usageWriterTokenSecret`
and the `openclaw` quota block — and no usage-pricing value at all.
`helm/templates/deployment.yaml` (189 lines) has the matching conditionals:

- `env:` gates `GITOPS_SSH_KEY_PATH` on `.Values.gitopsSSHSecret`,
  `GITHUB_APP_TOKEN_FILE` on `.Values.githubAppTokenSecret`, and
  `MCTL_USAGE_WRITER_TOKEN` (a `secretKeyRef` with `optional: true`) on
  `.Values.usageWriterTokenSecret`;
- `volumeMounts:` has unconditional `gitops-cache` and `roadmap-state`, then
  `gitops-ssh`, `github-app-token` and `cnpg-ca` each behind their value, each
  with `readOnly: true`;
- `volumes:` mirrors those, with long comments on `defaultMode` — 0444 for
  `github-app-token` and `cnpg-ca` because "Kubelet writes secret volume files
  as root:root unless the pod sets `securityContext.fsGroup`, and this chart
  sets no securityContext at all while the image runs as uid 1000".

There is **no chart test and no Helm step in CI**. `.github/workflows/validate.yml`
runs `golangci-lint`, then `go build ./...` and `go test -p 1 ./...` against a
Postgres service. `Makefile` has `build`, `test`, `fmt`, `clean` — nothing
chart-related. `cmd/api/main_test.go` only *mentions* the chart in a comment
(line 152, about the readiness probe). So the acceptance criterion "a chart
render test" means introducing that capability, not extending one.

`docs/model-usage-ledger.md` documents `USAGE_PRICING_CATALOG` as "Path to a
JSON rate-card file. Optional." with no word on how the path is produced.

## Proposed solution

### 1. Two values in `helm/values.yaml`

```yaml
# Optional: mount a versioned usage rate card from a ConfigMap.
#
# When set, the ConfigMap is mounted read-only at
# /etc/mctl-api/usage-pricing and USAGE_PRICING_CATALOG points at
# catalog.json inside it, which is what makes usage rows carry
# calculated_cost and pricing_version (internal/usage/store.go). Empty by
# default: an unset value renders exactly the chart that shipped before.
#
# The ConfigMap is owned by mctl-gitops (mctlhq/mctl-gitops#1409), not by
# this chart -- a published price is a fact with an effective date and is
# reviewed there against the provider's page. The volume reference is
# optional, so a ConfigMap that has not landed yet degrades to "no
# calculated cost" (one ERROR log) instead of a pod stuck pulling a
# missing volume.
usagePricingConfigMap: ""
# Key inside that ConfigMap holding the rate-card JSON. Defaults to
# "catalog.json", the key mctl-gitops publishes.
usagePricingConfigMapKey: ""
```

`usagePricingConfigMapKey` follows the established `githubAppTokenKey` /
`postgresCA.key` pattern (`""` in values, `| default "…"` in the template), so
the gitops follow-up stays the single line the issue promises.

### 2. Three guarded blocks in `helm/templates/deployment.yaml`

Env, appended to the existing `env:` list after the `usageWriterTokenSecret`
block (keeping the file's convention of one commented conditional per optional
input):

```yaml
{{- if .Values.usagePricingConfigMap }}
# The path, not the JSON. internal/usage/catalog_file.go reads this file
# with os.ReadFile; a rate card is reviewed as a file in GitOps, and an env
# value carrying the whole document would be unreviewable and would blow
# past the env size a card will grow into.
- name: USAGE_PRICING_CATALOG
  value: /etc/mctl-api/usage-pricing/catalog.json
{{- end }}
```

Mount, appended to `volumeMounts:` after the `cnpg-ca` block:

```yaml
{{- if .Values.usagePricingConfigMap }}
- name: usage-pricing
  mountPath: /etc/mctl-api/usage-pricing
  readOnly: true
{{- end }}
```

Volume, appended to `volumes:`:

```yaml
{{- if .Values.usagePricingConfigMap }}
# optional: true on purpose, and it is the whole ordering story. The chart
# ships first and mctl-gitops sets the value second, so there is a window
# in which the name resolves to nothing. A non-optional ConfigMap volume
# leaves the pod in ContainerCreating -- the control plane down over a rate
# card, which is the opposite of what cmd/api/main.go decided when it chose
# to log and continue on a load failure. Optional gives an empty directory,
# LoadCatalogFile returns ENOENT, one ERROR is logged, and usage is still
# recorded without a derived cost.
#
# A directory mount with items, not subPath: subPath copies are frozen at
# container start, so a corrected card would need a delete rather than a
# restart. No defaultMode override is needed -- unlike the Secret volumes
# above, ConfigMap volume files land 0644 and are readable by uid 1000.
- name: usage-pricing
  configMap:
    name: {{ .Values.usagePricingConfigMap }}
    optional: true
    items:
      - key: {{ .Values.usagePricingConfigMapKey | default "catalog.json" }}
        path: catalog.json
{{- end }}
```

The `items` projection is what decouples the ConfigMap key from the file name:
the env value is a template constant, so the path must not vary with the key.

Note this is intentionally *not* modelled on `envFromSecret`. Delivering the
catalog through `envFrom` is impossible — the code wants a path — and the
`githubAppTokenSecret` file-mount precedent is the one that fits.

### 3. Chart render test: `helm/render_test.go`

A new test-only Go package `package helm_test` in `helm/`. Verified in this
investigation that a directory holding only `_test.go` files is fine for this
repo's gates: `go build ./...`, `go vet ./...` and `go test ./...` all pass on
such a package, so no `doc.go` stub and no `Makefile` change to the build are
needed.

The test shells out to the real renderer, `helm template mctl-api ./ --show-only
templates/deployment.yaml` (with `--set usagePricingConfigMap=…` variants),
unmarshals the output with `gopkg.in/yaml.v3` — already a direct dependency in
`go.mod` — into a minimal struct (container `env`, `volumeMounts`, pod
`volumes`) and asserts structurally rather than by grep. Grep cannot tell
"`readOnly: true` on the usage-pricing mount" from "`readOnly: true` somewhere
in the file", and four such flags already render.

Cases:

1. **Default render** — no env named `USAGE_PRICING_CATALOG`, no volume or mount
   named `usage-pricing`; the five existing volumes are present.
2. **Set render** (`--set usagePricingConfigMap=mctl-api-usage-pricing`) — env
   present with value `/etc/mctl-api/usage-pricing/catalog.json`; mount
   `usage-pricing` at `/etc/mctl-api/usage-pricing` with `readOnly == true`;
   volume `usage-pricing` with `configMap.name == mctl-api-usage-pricing`,
   `optional == true`, one item `catalog.json -> catalog.json`. Assert the mount
   path is `path.Dir` of the env value and the item path is its `path.Base`, so
   the two can never drift apart silently.
3. **Empty-string render** (`--set usagePricingConfigMap=`) — output compared
   **byte-for-byte** against case 1. That is the literal "unchanged render when
   it is empty" criterion, and it is a stable comparison because both renders
   use the same chart, release name and image tag.
4. **Key override** (`--set usagePricingConfigMap=cm --set usagePricingConfigMapKey=rates.json`)
   — the item key becomes `rates.json` while `path` and the env value stay
   `catalog.json`.

Helm availability: `exec.LookPath("helm")`; when it is missing, `t.Skip` if
`os.Getenv("CI") == ""` and `t.Fatal` otherwise. A developer without Helm is not
blocked, and CI cannot pass the criterion vacuously. `.github/workflows/validate.yml`
gets `azure/setup-helm@v4` in the existing `test` job, before the build-and-test
step. This is the only CI change; no new job, so no new required-check plumbing.

### 4. Docs

One row and a short paragraph in `docs/model-usage-ledger.md`'s Configuration
section naming `usagePricingConfigMap` as the production delivery mechanism and
the ConfigMap as gitops-owned, so the next reader does not have to reverse the
chain from `os.Getenv`.

### 5. PR description

Must state that `usagePricingConfigMap: mctl-api-usage-pricing` in
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` is a required
one-line follow-up in `mctlhq/mctl-gitops` after this chart version ships, and
that nothing changes in production until it lands.

## Alternatives

**Deliver the catalog through `envFromSecret` / a plain env var holding the
JSON.** Dropped outright: `usage.LoadCatalogFile` takes a path and calls
`os.ReadFile`. Supporting an inline document would mean changing
`internal/usage` and `cmd/api/main.go`, which the issue explicitly keeps out of
scope, and would make the rate card unreviewable as a file and unbounded against
the env-size limit. The `githubAppTokenSecret` comment in the chart already
argues the file-mount case for a related reason.

**Bake the catalog into the chart as its own ConfigMap template.** Tempting —
it removes the cross-repo ordering problem entirely — but it moves the rate card
into this repo's release cycle, which is precisely what
`internal/usage/catalog_file.go`'s doc comment and `docs/model-usage-ledger.md`
argue against ("baking one into a binary means a price change needs a release").
It also duplicates `mctlhq/mctl-gitops#1409`, leaving two sources of truth for
money.

**Non-optional ConfigMap volume (omit `optional: true`).** Simpler, and it
surfaces a misconfigured name loudly. Dropped: the loud surface is the pod
stuck in `ContainerCreating` with no catalog *and* no API, which contradicts
`cmd/api/main.go`'s deliberate "recording usage without derived cost is
strictly better than recording nothing", and it makes the shipping order
(chart, then gitops value) into a production outage window rather than a
no-op. The absent-catalog case is not silent either way — it logs at ERROR and
the acceptance check greps for that log.

**`subPath` mount instead of a directory with `items`.** Fewer lines, mounts
just the one file. Dropped: `subPath` volume content is not updated when the
ConfigMap changes, so a corrected rate card would need the pod deleted rather
than restarted, and a `subPath` mount of a missing optional key behaves worse
than an empty directory.

**Chart render test as a shell script (`scripts/helm-render-test.sh`, alongside
the existing `seed-agent-platform.sh`) or as pure-Go text assertions over the
template file.** The shell version needs `yq` or Python+PyYAML for structural
assertions — neither guaranteed on the runner — and would live outside
`go test ./...`, the one gate contributors actually run. The pure-Go text
version never invokes Helm, so it asserts the template's characters rather than
its output and would not catch an indentation error that breaks the render.
Both were dropped in favour of `helm template` + `yaml.v3`.

## Platform impact

**Migrations.** None. No schema change; `usage_records` already has
`calculated_cost` and `pricing_version` with the
`calculated_cost_requires_version` constraint.

**Backward compatibility.** Total, by construction. Every change is behind
`{{- if .Values.usagePricingConfigMap }}` and the value defaults to `""`, which
render case 3 pins byte-for-byte. Deployments that never set the value —
including every current one — are unaffected by the chart bump.

**Resource impact.** One ConfigMap volume, a few KB of rate card in the pod's
tmpfs. No CPU or memory change; `helm/values.yaml` resource limits
(100m/128Mi request, 500m/256Mi limit) are untouched. Catalog parsing happens
once at startup and `usage.NewCatalog` sorts a handful of entries.

**Behaviour change once the gitops value lands.** New rows for models with a
matching card gain a non-null `calculated_cost` and a non-empty
`pricing_version`. Historical rows keep null costs — ADR-012 invariant 7 means
adding a card cannot reach back, and re-deriving old costs is a separate
backfill. Dashboards summing `calculated_cost` will show a step change at
rollout; that is the intended outcome, not a regression, but it is worth saying
in the PR.

**Risks and mitigations.**

- *ConfigMap absent or key renamed.* Mitigated by `optional: true`: empty
  directory, `LoadCatalogFile` ENOENT, one ERROR log, API healthy. The
  acceptance check is exactly the absence of that log.
- *Malformed rate card.* `ParseCatalog` / `NewCatalog` reject bad JSON,
  a missing `version`, and duplicate `(model, provider, effective_from)`
  triples; `main.go` logs and continues with no catalog. Costs stay null rather
  than becoming wrong — the failure mode `internal/usage` was built to prefer.
- *Wrong rates (plausible-looking money).* Out of this repo's hands by design;
  the card is reviewed in `mctlhq/mctl-gitops`. Worth noting that
  `pricing_version` on each row makes a later audit able to say which card
  produced a number.
- *File unreadable as uid 1000.* Not a risk for ConfigMap volumes — unlike the
  Secret volumes in this chart, which needed `defaultMode: 0444` for exactly
  this reason, ConfigMap files land world-readable at 0644. Deliberately no
  `defaultMode` override, and the template comment records why.
- *New CI dependency on `helm`.* One `azure/setup-helm@v4` step in an existing
  job. If the action is unavailable the `test` job fails loudly at setup rather
  than skipping the assertion, and the test's `CI`-aware skip rule means a
  missing binary in CI is a failure, not a pass.
- *Stale mount path.* The env value, the `mountPath` and the item `path` are
  three literals that must agree. Render case 2 asserts the relationship
  (`path.Dir` / `path.Base` of the env value) rather than restating the
  constants, so a future edit to one of them fails the test.
