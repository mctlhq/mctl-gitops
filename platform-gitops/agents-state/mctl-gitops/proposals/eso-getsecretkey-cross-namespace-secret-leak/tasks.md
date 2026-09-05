# Tasks: eso-getsecretkey-cross-namespace-secret-leak

- [ ] 1. Locate the current External Secrets Operator chart version pin in
      `platform-gitops/bootstrap/` or `platform-gitops/apps/`. — DoD: exact
      current chart/app version identified and documented.
- [ ] 2. Grep all ExternalSecret manifests (primarily
      `platform-gitops/argo-workflows/secrets/`, plus any templated ones
      under `platform-gitops/argo-workflows/service-templates/` or
      `file-templates/`) for use of the `getSecretKey` template function
      (depends on 1). — DoD: written confirmation of zero usages, or a list
      of manifests needing rewrite before the bump.
- [ ] 3. IF usages found in task 2: rewrite affected ExternalSecret
      manifests to use a supported template function/provider before
      proceeding (depends on 2). — DoD: manifests updated and validated
      against a non-production ExternalSecret sync.
- [ ] 4. Bump the ESO chart version pin to a release bundling operator
      >=1.2.0 (e.g. helm-chart-2.10.0 or later) (depends on 2, and 3 if
      applicable). — DoD: git diff to the version pin committed, ArgoCD
      self-syncs the new chart, ESO controller pod reports the new version
      (e.g. via `kubectl get deploy -o jsonpath` image tag or controller
      logs).
- [ ] 5. Verify all ClusterSecretStore (`vault-backend`) and ExternalSecret
      resources across tenants remain Synced/Ready after the bump (depends
      on 4). — DoD: no ExternalSecret in `admins`, `labs`, or other tenants
      shows a new SecretSyncError post-upgrade.
- [ ] 6. Check ESO controller pod memory usage before/after the bump,
      specifically confirming no increase affecting the `labs` quota
      (depends on 4). — DoD: memory request/limit and observed usage
      recorded pre- and post-bump, confirming no measurable increase.

## Tests
- [ ] T1. Confirm the deployed ESO controller version is >=1.2.0 (or the
      version bundled by the new chart) after rollout.
- [ ] T2. Confirm the `getSecretKey` function is unavailable/removed in the
      new version (e.g. attempt a test ExternalSecret using it in a
      scratch/non-prod namespace and confirm it fails to render).
- [ ] T3. Confirm all existing ExternalSecret resources in `admins` and
      `labs` still resolve to the correct Vault paths with no SecretSyncError.
- [ ] T4. Confirm ESO controller memory usage post-upgrade is not higher
      than pre-upgrade baseline.

## Rollback
Revert the chart version-pin commit and let ArgoCD self-sync roll the ESO
controller back to the previous version. Because no ExternalSecret/CRD
schema changes are made (assuming task 2 finds no `getSecretKey` usage),
rollback is a single git revert. If task 3 rewrote any manifests, revert
those commits together with the chart pin to restore the prior consistent
state.
