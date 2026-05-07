# Tasks: vault-v2-major-upgrade-plan

- [ ] 1. Audit all ExternalSecret manifests for double-slash paths — grep
  `platform-gitops/services/` and `platform-gitops/argo-workflows/secrets/` for any path
  values containing `//`; produce a list of affected files and the corrected paths.
  DoD: grep returns zero matches; corrected manifests are reviewed and merged to the default
  branch before any Vault chart version is changed.

- [ ] 2. Confirm ESO compatibility with Vault v2.0.0 (depends on 1) — review ESO release
  notes and the Vault v2.0.0 changelog to verify the `vault-backend` ClusterSecretStore
  API contract is unchanged; identify any ESO configuration adjustments needed.
  DoD: written confirmation (comment in PR or ADR note) that ESO vX.Y.Z is compatible with
  Vault v2.0.0 and no ESO version bump is required.

- [ ] 3. Pin Vault Helm chart to v2.0.0 in `labs` namespace (depends on 1, 2) — update the
  chart version in `platform-gitops/services/labs/<vault-svc>/` and open a PR.
  DoD: ArgoCD syncs successfully in `labs`; ESO `vault-backend` ClusterSecretStore shows
  `Ready`; no ExternalSecret sync errors in ESO controller logs.

- [ ] 4. Measure `labs` memory consumption after upgrade (depends on 3) — observe Vault pod
  memory usage in the `labs` namespace for at least 30 minutes post-rollout.
  DoD: measured peak memory is documented; if usage approaches the `labs` tenant limit, a
  capacity-review issue is opened and promotion to `admins` is blocked until resolved.

- [ ] 5. Run smoke tests in `labs` (depends on 3, 4) — see Tests section below.
  DoD: all three smoke tests pass with no failures.

- [ ] 6. Promote Vault chart to v2.0.0 in `admins` namespace (depends on 5) — update the
  chart version in `platform-gitops/services/admins/<vault-svc>/` and open a PR.
  DoD: ArgoCD syncs successfully in `admins`; all ExternalSecret objects remain `Ready`;
  no errors in ESO controller or Vault server logs within 15 minutes of rollout.

- [ ] 7. Retire individual CVE patch proposals as superseded (depends on 6) — add a
  `.status.yaml` file to each of the four individual vault CVE proposal directories
  (`vault-cve-2026-token-exposure`, `vault-kvv2-deletion-bypass`, `vault-ldap-null-bind-bypass`,
  `vault-ssrf-acme-patch`) marking them superseded by `vault-v2-major-upgrade-plan`.
  DoD: each directory contains a `.status.yaml` with `status: superseded` and a reference
  to this proposal slug.

- [ ] 8. Update `context/current-version.md` with new Vault version (depends on 6) — record
  Vault v2.0.0 as the running version in the knowledge base.
  DoD: `context/current-version.md` reflects `vault: v2.0.0`; change is committed.

## Tests

- [ ] T1. ExternalSecret sync test — after upgrade in `labs`, confirm that every
  ExternalSecret object in the `labs` namespace reaches `Ready` status within the standard
  sync interval. Check with: `kubectl get externalsecrets -n labs -o wide` and confirm no
  `SecretSyncedError` conditions.

- [ ] T2. CVE-2026-5807 DoS vector test — initiate a root-token generation operation against
  the Vault API, then immediately cancel it; repeat five times in rapid succession. Confirm
  that the Vault server remains responsive to authenticated operator requests (e.g., `vault
  status` returns HTTP 200) throughout and after the sequence.

- [ ] T3. Double-slash path rejection test — submit a test ExternalSecret with a deliberately
  double-slashed path (e.g., `secret//data/test`) to the `labs` Vault. Confirm that Vault
  returns a 400-level error and the ESO controller logs a clear sync failure rather than
  silently returning an empty secret.

## Rollback

If the `labs` or `admins` upgrade causes ExternalSecret sync failures or Vault instability:

1. Revert the Helm chart version change via `git revert` on the relevant commit in
   `platform-gitops/services/<tenant>/<vault-svc>/`.
2. Merge and push the revert commit; ArgoCD will reconcile the chart back to the previous
   version automatically.
3. Verify that the ESO `vault-backend` ClusterSecretStore reconnects and all ExternalSecrets
   return to `Ready`.
4. Open a post-mortem issue documenting what failed and what must be resolved before
   re-attempting the upgrade.

No Vault data migration is performed during this upgrade (KV data is stored in the backend
storage, not in the chart), so a chart version rollback is sufficient to restore the
previous state without data loss.
