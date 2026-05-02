# Tasks: eso-cross-namespace-secret-access

- [ ] 1. Verify CVE-2026-22822 fix inclusion in helm-chart-2.4.1
  Check the ESO GitHub security advisory (https://github.com/external-secrets/external-secrets/security/advisories)
  and the chart's `Chart.yaml` / controller image tag to confirm `getSecretKey` namespace
  validation is present in the bundled controller version.
  **DoD:** A written note (PR description or ADR comment) records the ESO controller image tag,
  confirms the fix commit SHA is included, and links to the advisory.

- [ ] 2. Audit ExternalSecret manifests for cross-namespace Vault path references (depends on 1)
  Scan all files under `platform-gitops/argo-workflows/secrets/` for any `remoteRef.key` value
  that contains a Vault path segment belonging to a namespace other than the manifest's own
  namespace.
  **DoD:** Audit log records every manifest checked; zero cross-namespace path references found,
  or any found are corrected and the correction is reviewed before proceeding.

- [ ] 3. Assess CRD delta between current ESO chart version and helm-chart-2.4.1 (depends on 1)
  Run `kubectl diff` or compare the chart's `crds/` directory contents to the currently-applied
  CRDs to identify any schema changes.
  **DoD:** A diff output is attached to the PR. If no CRD changes: proceed directly to task 4.
  If CRD changes exist: task 4a (apply CRDs first) is inserted before task 4.

- [ ] 4. Update ESO Helm chart version pin in `platform-gitops/apps/` (depends on 2, 3)
  Change the chart version reference in the relevant ArgoCD Application manifest from the current
  version to `helm-chart-2.4.1`. If task 3 found CRD changes, apply the new CRD manifests via
  `kubectl apply -f crds/` before or alongside this commit.
  **DoD:** The PR diff shows exactly the chart version line changed (and CRD files if applicable);
  no other manifests are modified.

- [ ] 5. Commit, open PR, and trigger ArgoCD reconciliation (depends on 4)
  Push the branch, open a PR with a reference to CVE-2026-22822, and merge after review. Confirm
  ArgoCD syncs the ESO Application to `Synced / Healthy`.
  **DoD:** ArgoCD Application for ESO shows `Synced` and `Healthy` in the UI / via
  `argocd app get`; the ESO operator pod is running the new image.

- [ ] 6. Post-upgrade validation (depends on 5)
  Confirm `ClusterSecretStore vault-backend` status is `Ready=True`, all ExternalSecret
  resources across both tenant namespaces are `Ready=True`, and memory usage of the ESO operator
  pod has not materially increased (flag if > 10 % increase).
  **DoD:** Output of `kubectl get clustersecretstore vault-backend -o yaml` and
  `kubectl get externalsecrets -A` attached to the PR; memory before/after recorded.

- [ ] 7. Defence-in-depth Vault policy review (depends on 5)
  Verify that the Vault AppRole or Kubernetes auth role used by ESO has read access restricted to
  each tenant's own path prefix (`secret/data/admins/*` not accessible to the `labs` auth role
  and vice versa).
  **DoD:** Vault policy outputs for both tenant roles reviewed and confirmed; any overly broad
  policy is tightened and the change is committed to `infrastructure/` (or tracked as a follow-on
  task with a ticket).

## Tests

- [ ] T1. Legitimate ExternalSecret sync — After upgrade, confirm that a known-good ExternalSecret
  in `admins` and a known-good ExternalSecret in `labs` both reach `Ready=True` and their
  Kubernetes Secret data matches the expected Vault values.

- [ ] T2. Cross-namespace isolation regression test — Create a test ExternalSecret in the `labs`
  namespace with a `remoteRef.key` pointing to a Vault path under the `admins` prefix. Confirm
  ESO returns a `SecretSyncError` status condition and does NOT populate the Kubernetes Secret
  with `admins` data. Remove the test manifest after validation. Repeat symmetrically
  (`admins` attempting to read `labs` path).

- [ ] T3. CRD compatibility — If CRDs were updated in task 3, confirm that all existing
  ExternalSecret and ClusterSecretStore objects pass `kubectl get` without conversion errors after
  the upgrade.

- [ ] T4. Memory regression — Record ESO operator pod memory usage (via `kubectl top pod`)
  immediately before and 15 minutes after the upgrade. Confirm no increase greater than 10 %.

## Rollback

If the upgrade causes ExternalSecret reconciliation failures or operator crashes:

1. Revert the Helm chart version pin commit in `platform-gitops/apps/` (git revert or new commit
   restoring the previous chart version).
2. If CRDs were updated: apply the previous CRD version from git history using
   `kubectl apply -f` against the chart's `crds/` directory at the prior pinned version.
3. Merge the revert PR; ArgoCD will reconcile ESO back to the previous version.
4. Verify `ClusterSecretStore vault-backend` returns to `Ready=True` and all ExternalSecrets
   resume normal sync.
5. Open a follow-up ticket to investigate the root cause before re-attempting the upgrade.

Note: existing Kubernetes Secrets are not deleted by ESO during a version rollback. Tenant
workloads continue to consume the already-synced Secret data while the operator is rolled back.
