# Tasks: issue-1405-chore-work-context-wire-the-surface-tele

- [ ] 1. Add the mctl-api gate to `platform-gitops/bootstrap/values.yaml`: a
  top-level `surfaceTelegramToken: { enabled: false }`, with the owner steps
  written above it in the shape `usageWriter` uses (Vault write with
  `printf '%s' "$(openssl rand -hex 32)" | vault kv patch -method=rw
  secret/platform/mctl-api/surface-tokens telegram-token=-`, never `put`, no
  trailing newline, >= 32 bytes per `minSurfaceTokenLen`, distinct from
  `MCTL_AGENT_SERVICE_TOKEN`; then the mctl-api chart value; then this flag)
  — DoD: `helm template test platform-gitops/bootstrap -f
  platform-gitops/bootstrap/values.yaml` renders identically to before the
  edit, and the comment names all four owner steps in order and states that
  none is performed by this change.

- [ ] 2. Add `platform-gitops/bootstrap/templates/mctl-platform/mctl-api-surface-telegram.yaml`
  (depends on 1): whole body inside
  `{{- if (default dict .Values.surfaceTelegramToken).enabled }}`, one
  `ExternalSecret` `mctl-api-surface-telegram` in namespace `mctl-api`,
  `refreshInterval: 1h`, `ClusterSecretStore vault-backend`,
  `target.name: mctl-api-surface-telegram`, `creationPolicy: Owner`, single
  `data` entry `secretKey: MCTL_SURFACE_TELEGRAM_TOKEN` from
  `key: platform/mctl-api/surface-tokens`, `property: telegram-token`; header
  comment mirroring `mctl-api-usage-writer.yaml` on why it is its own
  ExternalSecret and its own file — DoD: gate on renders exactly one new
  document and it passes `kubeconform -strict`; gate off renders nothing; the
  template also renders with the `surfaceTelegramToken` key deleted from
  values.

- [ ] 3. Wire it into the Application in
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` (depends
  on 2): inside the same gate, next to the existing `usageWriterTokenSecret`
  block, add `surfaceTelegramTokenSecret: mctl-api-surface-telegram` with a
  comment naming the mctl-api chart prerequisite (`helm/` must carry an
  optional `surfaceTelegramTokenSecret`, mirroring `usageWriterTokenSecret`)
  and stating that Helm ignores the value until it does — DoD: the gate-on
  render of `admins-mctl-api` contains the line inside
  `spec.sources[0].helm.values`; the gate-off render does not; nothing else
  in the Application's values diff.

- [ ] 4. Add the new template to the `ignore:` list in
  `.github/workflows/yamllint.yml` (depends on 2), beside
  `mctl-api-usage-writer.yaml`, with the existing rationale — DoD: `yamllint
  -c <that config> platform-gitops` passes locally.

- [ ] 5. Add the `workContext` block to
  `platform-gitops/helm-charts/base-service/values.yaml`: `enabled: false`,
  `featureEnabled: false`, `tenant: ""`, `apiBaseUrl: ""`,
  `tokenEnvName: MCTL_SURFACE_TELEGRAM_TOKEN`, `tokenVaultKey: ""`,
  `tokenVaultProperty: ""`, `tokenSecretName: ""`, `store: vault-backend`,
  `storeKind: ClusterSecretStore`, `refreshInterval: 1h`, each documented in
  the file's `# --` comment style — DoD: `helm lint
  platform-gitops/helm-charts/base-service` passes and the default render is
  unchanged.

- [ ] 6. Add `platform-gitops/helm-charts/base-service/templates/externalsecret-work-context.yaml`
  (depends on 5): whole body gated on `workContext.enabled`; `fail` with a
  named message when `tokenVaultKey` or `tokenVaultProperty` is empty; one
  `ExternalSecret` `<fullname>-work-context` with target
  `workContext.tokenSecretName | default "<fullname>-work-context"`,
  `creationPolicy: Owner`, store via the existing
  `base-service.secretStoreRef` helper, one `data` entry
  `secretKey: <tokenEnvName>` from `tokenVaultKey`/`tokenVaultProperty` with
  `conversionStrategy: Default`, `decodingStrategy: None`,
  `metadataPolicy: None` spelled out per the chart's #789 convention — DoD:
  gate on renders one valid `ExternalSecret`; gate off renders nothing; the
  empty-vault-key case fails the render with the named message.

- [ ] 7. Extend `base-service.env` in
  `platform-gitops/helm-charts/base-service/templates/_helpers.tpl` (depends
  on 5): under `workContext.enabled`, emit `WORK_CONTEXT_ENABLED` (quoted
  from `featureEnabled`), `MCTL_WORK_ITEM_TENANT` (from `tenant`, may be
  empty), `MCTL_API_BASE_URL` only when `apiBaseUrl` is non-empty, and
  `<tokenEnvName>` as `valueFrom.secretKeyRef` on the target Secret with
  `optional: true`; skip any name the service already set under `env:` or
  `envValueFrom:`, matching the `otel` precedence — DoD: gate-on render shows
  the four entries in that order; a values file that sets
  `WORK_CONTEXT_ENABLED` explicitly under `env:` renders exactly one such
  entry, the explicit one.

- [ ] 8. Extend the env guard in BOTH
  `platform-gitops/helm-charts/base-service/templates/deployment.yaml` and
  `templates/rollout.yaml` (depends on 7) to
  `{{- if or .Values.env .Values.envValueFrom .Values.otel.enabled (default dict .Values.workContext).enabled }}`
  — DoD: a values file with no `env:`/`envValueFrom:` and
  `workContext.enabled: true` renders the env block on both workload kinds.

- [ ] 9. Add the `workContext` block to
  `platform-gitops/services/labs/mctl-telegram/values.yaml` (depends on 5):
  `enabled: false`, `featureEnabled: false`, `tenant: ""`,
  `tokenVaultKey: secret/data/platform/mctl-api/surface-tokens`,
  `tokenVaultProperty: telegram-token`, `apiBaseUrl: ""` (leaves
  mctl-telegram's own `https://api.mctl.ai` default), with the owner steps as
  comments directly above: (1) Vault write, (2) set `tenant`, (3)
  `enabled: true` and confirm the Secret syncs, (4) `featureEnabled: true` —
  and a note that `strategy.type: Recreate` plus mctl-telegram's
  refuse-to-start-on-missing-token behaviour is why steps 3 and 4 are
  separate. No `envFrom` entry and no `extraExternalSecrets` entry is added —
  DoD: `helm template test platform-gitops/helm-charts/base-service -f
  platform-gitops/services/labs/mctl-telegram/values.yaml` is byte-identical
  to the pre-change render.

- [ ] 10. Add the bootstrap both-states CI step to
  `.github/workflows/validate-manifests.yml` (depends on 3), copied from the
  usage-writer step: render with `--set surfaceTelegramToken.enabled=false`
  and `=true`, `kubeconform -strict -summary` the on-render, and assert each
  of the markers `name: mctl-api-surface-telegram`,
  `surfaceTelegramTokenSecret: mctl-api-surface-telegram`,
  `property: telegram-token` is present on and absent off — DoD: the step
  passes on the branch and fails if either gate branch is broken (verified by
  temporarily inverting the gate).

- [ ] 11. Register `tests/test_base_service_work_context_env.py` as a new
  `run:` step in `.github/workflows/validate-manifests.yml` (depends on 12)
  with `python3 -m pip install --quiet pyyaml` first, in the style of the
  existing `Unit-test base-service's OTEL env on both workload kinds` step —
  DoD: the step runs in CI and fails when the test fails.

- [ ] 12. Write `tests/test_base_service_work_context_env.py` (depends on
  6, 7, 8, 9) as a plain script in this repo's convention — `ROOT =
  pathlib.Path(__file__).resolve().parents[1]`, module-level `failures`,
  `check(cond, msg)`, `sys.exit(1)`, `helm template` through
  `subprocess.run` — covering tests T1-T6 below. No pytest: this repo has
  none — DoD: `python3 tests/test_base_service_work_context_env.py` exits 0
  on the branch, and each check has been seen to fail once by hand-breaking
  the thing it guards.

## Tests

- [ ] T1. Gate off is indistinguishable from absent: render
  `platform-gitops/services/labs/mctl-telegram/values.yaml` as committed, and
  render a copy with the `workContext` key deleted; the two documents must be
  byte-identical. Same for `platform-gitops/bootstrap` with
  `surfaceTelegramToken.enabled: false` versus the key removed.
- [ ] T2. Gate on, mctl-telegram: exactly one `ExternalSecret`
  `labs-mctl-telegram-work-context` is added; the container env gains
  `MCTL_SURFACE_TELEGRAM_TOKEN` via `secretKeyRef` with `optional: true`
  pointing at that Secret's `MCTL_SURFACE_TELEGRAM_TOKEN` key, plus
  `WORK_CONTEXT_ENABLED` and `MCTL_WORK_ITEM_TENANT`; no `MCTL_API_BASE_URL`
  while `apiBaseUrl` is empty; and the pre-existing `env` map, `envValueFrom`,
  `envFrom` list and five `extraExternalSecrets` are untouched.
- [ ] T3. One property, two spellings: parse the Vault key/property out of
  `bootstrap/templates/mctl-platform/mctl-api-surface-telegram.yaml` and out
  of the labs values file, normalise a leading `secret/data/`, and assert
  both path and property are equal.
- [ ] T4. Both workload kinds: render a minimal values file with
  `workContext.enabled: true` and no `env:`/`envValueFrom:` as a `Deployment`
  and as a `Rollout` (the `blueGreen` path) and assert the same four env
  entries in both — the `tests/test_base_service_otel_env.py` trap.
- [ ] T5. Precedence and guard rails: a values file setting
  `WORK_CONTEXT_ENABLED` or `MCTL_WORK_ITEM_TENANT` explicitly under `env:`
  yields exactly one entry for that name, the explicit one; and
  `workContext.enabled: true` with an empty `tokenVaultKey` or
  `tokenVaultProperty` fails the render with the named message.
- [ ] T6. No collateral render change: every other values file under
  `platform-gitops/services/*/*/values.yaml` renders byte-identically to its
  pre-change render (the existing render-every-service CI loop plus
  `kubeconform -strict` covers validity; this check covers identity).
- [ ] T7. Gate on, mctl-api: the bootstrap CI step's three markers are
  present in the on-render and absent from the off-render, and the on-render
  passes `kubeconform -strict` against the CRD catalogue.

## Rollback

While both gates are off, rollback is `git revert` of the single merge: no
cluster object exists to remove, and ArgoCD's next sync is a no-op. The
change is deliberately shaped so that this is the state it lands in.

If a gate has been flipped and something is wrong:

1. Set `surfaceTelegramToken.enabled: false` in
   `platform-gitops/bootstrap/values.yaml` and/or `workContext.enabled:
   false` in `platform-gitops/services/labs/mctl-telegram/values.yaml`, and
   commit. Both ExternalSecrets use `creationPolicy: Owner`, so ArgoCD prunes
   them and Kubernetes garbage-collects the Secrets through their owner
   references; the Deployments lose the env entries and roll.
2. To disable the feature without unwinding the wiring — the smaller,
   preferred step — set `workContext.featureEnabled: false` only. The token
   stays mounted and mctl-telegram starts regardless of whether the Secret
   has synced.
3. If mctl-telegram is crash-looping because `WORK_CONTEXT_ENABLED` is true
   while the token or tenant is missing, step 2 is the fix and it is one
   values key. Note `strategy.type: Recreate`: the pod is replaced, not
   rolled, so expect a short gap rather than a degraded replica.
4. If mctl-api returns 401 for `surface:telegram` after the flip, the likely
   cause is the missing chart value in mctlhq/mctl-api (`helm/` without
   `surfaceTelegramTokenSecret`), not the gitops wiring: check
   `kubectl -n mctl-api get deploy mctl-api -o yaml` for an env entry named
   `MCTL_SURFACE_TELEGRAM_TOKEN`. Its absence means the value was ignored;
   revert step 1 for mctl-api and land the chart value first.
5. No Vault value is created, changed or deleted by this change or by its
   rollback. Rotating or removing the stored property is an owner action in
   both directions.
