# Tasks: issue-403-feat-usage-mount-the-usage-price-catalog

- [ ] 1. Add the two values to `helm/values.yaml`: `usagePricingConfigMap: ""`
      and `usagePricingConfigMapKey: ""`, placed after `usageWriterTokenSecret`
      with a comment block in the file's existing style (why a file and not
      `envFrom`, who owns the ConfigMap, why the reference is optional) — DoF:
      `helm lint helm/` passes; the two keys exist, both empty; no other value
      touched.

- [ ] 2. Add the `USAGE_PRICING_CATALOG` env block to
      `helm/templates/deployment.yaml` (depends on 1). Guarded by
      `{{- if .Values.usagePricingConfigMap }}`, appended to the container `env:`
      list after the `usageWriterTokenSecret` block, value
      `/etc/mctl-api/usage-pricing/catalog.json` — DoD:
      `helm template helm/ --set usagePricingConfigMap=cm` shows the env with
      that exact value; the default render shows no such env.

- [ ] 3. Add the `usage-pricing` `volumeMount` (depends on 2). Same guard,
      appended after the `cnpg-ca` mount, `mountPath: /etc/mctl-api/usage-pricing`,
      `readOnly: true` — DoD: the set render shows the mount with `readOnly: true`
      and the five pre-existing mounts unchanged.

- [ ] 4. Add the `usage-pricing` volume (depends on 3). Same guard, appended to
      `volumes:`, `configMap.name: {{ .Values.usagePricingConfigMap }}`,
      `optional: true`, one item
      `{{ .Values.usagePricingConfigMapKey | default "catalog.json" }} -> catalog.json`.
      Include the comment explaining `optional: true` (chart ships before the
      gitops value; a non-optional volume would leave the pod in
      `ContainerCreating` and contradict `cmd/api/main.go`'s log-and-continue),
      why a directory mount with `items` rather than `subPath`, and why no
      `defaultMode` override is needed (ConfigMap files land 0644, unlike the
      Secret volumes above) — DoD: the set render shows the volume with
      `optional: true` and the single item; the default render shows no
      `usage-pricing` volume.

- [ ] 5. Add the chart render test `helm/render_test.go` as `package helm_test`
      (depends on 4). Shell out to `helm template mctl-api ./ --show-only
      templates/deployment.yaml` with the variants below, unmarshal with
      `gopkg.in/yaml.v3` (already a direct dep) into a minimal
      env/volumeMounts/volumes struct, assert structurally. Resolve `helm` with
      `exec.LookPath`; `t.Skip` when it is missing and `os.Getenv("CI") == ""`,
      `t.Fatal` when it is missing and `CI` is set — DoD: `go build ./...`,
      `go vet ./...` and `go test ./helm/` all pass; the test fails if any of
      the env value, `mountPath`, `readOnly`, `optional` or the item mapping is
      changed.

- [ ] 6. Add `azure/setup-helm@v4` to the existing `test` job in
      `.github/workflows/validate.yml`, before the "go build & test" step
      (depends on 5) — DoD: the `test` job still runs `go test -p 1 ./...` with
      the same `TEST_DB_URL`/`TEST_DATABASE_URL` env; `helm version` succeeds on
      the runner; no new job and no change to the `lint` job.

- [ ] 7. Extend `docs/model-usage-ledger.md` Configuration section (depends on
      2): note that in production the path comes from the chart value
      `usagePricingConfigMap`, which mounts the gitops-owned
      `mctl-api-usage-pricing` ConfigMap (key `catalog.json`) read-only at
      `/etc/mctl-api/usage-pricing`, and that an absent ConfigMap degrades to
      "no calculated cost" with one ERROR log — DoD: the table row and paragraph
      exist, naming no rate values.

- [ ] 8. Write the PR description (depends on 1-7): state that
      `usagePricingConfigMap: mctl-api-usage-pricing` in
      `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` is a
      required one-line follow-up in `mctlhq/mctl-gitops` after this chart
      version ships; that production behaviour is unchanged until it lands; and
      that afterwards new rows gain `calculated_cost` while historical rows keep
      null (ADR-012 invariant 7), so cost dashboards will show a step change.
      Reference `mctlhq/mctl-gitops#1409`, `mctlhq/mctl-gitops#1421` and
      `mctlhq/.github#50` — DoD: the PR body contains the follow-up line
      verbatim and the step-change note.

## Tests

- [ ] T1. `TestDeploymentDefaultRenderHasNoUsagePricing` — default render:
      no env named `USAGE_PRICING_CATALOG`, no volume named `usage-pricing`, no
      mount named `usage-pricing`; `gitops-cache` and `roadmap-state` still
      present.
- [ ] T2. `TestDeploymentRendersUsagePricingEnvAndMount` —
      `--set usagePricingConfigMap=mctl-api-usage-pricing`: env value is
      `/etc/mctl-api/usage-pricing/catalog.json`; the `usage-pricing` mount's
      `mountPath` equals `path.Dir` of that env value and its `readOnly` is
      `true`; the volume's `configMap.name` is `mctl-api-usage-pricing`,
      `optional` is `true`, and it has exactly one item whose `path` equals
      `path.Base` of the env value. Asserting the dir/base relationship rather
      than restating the literals is what makes a future one-sided edit fail.
- [ ] T3. `TestDeploymentEmptyUsagePricingRendersUnchanged` —
      `--set usagePricingConfigMap=` output is byte-identical to the default
      render. This is the issue's "unchanged render when it is empty".
- [ ] T4. `TestDeploymentUsagePricingKeyOverride` —
      `--set usagePricingConfigMap=cm --set usagePricingConfigMapKey=rates.json`:
      the item `key` is `rates.json` while the item `path` and the env value
      stay `catalog.json`, proving the ConfigMap key is decoupled from the
      mounted file name.
- [ ] T5. `TestDeploymentUsagePricingLeavesOtherVolumesIntact` — with the value
      set, `--set githubAppTokenSecret=s --set postgresCA.secretName=ca` still
      renders `github-app-token` and `cnpg-ca` with their `defaultMode: 0444`
      and `readOnly: true`, so the new blocks did not land inside an existing
      conditional.
- [ ] T6. `helm lint helm/` clean with the value set and unset (can be a
      subtest of the same package or a step in task 6).
- [ ] T7. Post-release manual verification, per the issue's acceptance: after
      the gitops one-liner lands, `mctl_get_service_logs` for `mctl-api` shows
      no `usage pricing catalog failed to load` and no
      `usage record stored without calculated cost: no pricing card matched`
      for `claude-opus-5`; a newly ingested `claude-opus-5` row read via
      `GET /api/v1/usage/records` carries a non-null `calculated_cost` and
      `pricing_version = 2026-09-01-firstparty-1`.

## Rollback

Three independent levers, cheapest first.

1. **No deploy required.** Until the mctl-gitops follow-up sets
   `usagePricingConfigMap`, this PR is inert in production — the value defaults
   to `""` and T3 pins the render as byte-identical. Merging and releasing the
   chart carries no runtime risk of its own.
2. **Revert the gitops one-liner.** If the mounted catalog misbehaves after the
   follow-up lands, remove `usagePricingConfigMap: mctl-api-usage-pricing` from
   `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` and let
   ArgoCD sync. The pod restarts without the env and the mount and returns to
   today's behaviour (token counts recorded, `calculated_cost` null). Rows
   already priced keep their `calculated_cost` and `pricing_version` — ADR-012
   invariant 7 — which is correct: they were derived from a card that really
   was in force.
3. **Rollback the chart.** `mctl_rollback_service team_name=mctl-platform
   component_name=mctl-api target_tag=<previous>` (confirm the previous tag with
   `mctl_get_service_config` first), or revert this PR in `mctl-api` and
   release. Note: if the gitops value is still set while the chart no longer
   knows the key, the value is simply ignored by Helm, so the order of 2 and 3
   does not matter.

No data migration to undo, and no state outside the pod is touched.
