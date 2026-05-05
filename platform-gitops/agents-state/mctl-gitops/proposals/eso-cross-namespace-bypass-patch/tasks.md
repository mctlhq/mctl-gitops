# Tasks: eso-cross-namespace-bypass-patch

- [ ] 1. Identify the file in `platform-gitops/` that pins the ESO Helm chart version — DoD: file path and current chart version string are documented in the PR description.
- [ ] 2. Audit all ExternalSecret manifests under `platform-gitops/` to confirm none rely on cross-namespace secret access (depends on 1) — DoD: a checklist in the PR description confirms every ExternalSecret references only Vault paths appropriate for its own namespace; any anomalies are flagged and resolved before merge.
- [ ] 3. Update the ESO Helm chart version to `helm-chart-2.4.1` in the pinned file (depends on 2) — DoD: a single-line diff shows the version string changed to `helm-chart-2.4.1`; no other configuration fields are modified.
- [ ] 4. Open a pull request with the change and obtain at least one peer review (depends on 3) — DoD: PR is approved by a second platform engineer and all CI checks pass.
- [ ] 5. Merge the PR to the main branch (depends on 4) — DoD: commit is visible on main; ArgoCD detects the Application drift within its polling interval.
- [ ] 6. Verify ESO rollout completes successfully (depends on 5) — DoD: ESO controller pod shows `Running` with the image corresponding to helm-chart-2.4.1; the ArgoCD Application for ESO shows `Synced / Healthy` at `ops.mctl.ai`.
- [ ] 7. Validate all ExternalSecrets in both tenants reconcile successfully post-upgrade (depends on 6) — DoD: `kubectl get externalsecret -A` shows all resources in `Ready` condition; no `SecretSyncError` events in any namespace.

## Tests

- [ ] T1. Confirm the ESO controller image digest or tag matches the expected value for helm-chart-2.4.1 via `kubectl get deployment -n admins -o jsonpath='{.spec.template.spec.containers[0].image}'`.
- [ ] T2. Create a test ExternalSecret in the `labs` namespace that references a Vault path that is only authorised for the `admins` namespace and confirm the controller rejects the sync with an appropriate error condition (tests CVE-2026-22822 remediation).
- [ ] T3. Confirm at least one existing ExternalSecret in `admins` and one in `labs` successfully sync their target Kubernetes Secret after the upgrade (tests backward compatibility of legitimate use).
- [ ] T4. Verify the Vault ClusterSecretStore (`vault-backend`) remains in `Valid` condition after the upgrade via `kubectl get clustersecretstore vault-backend -o jsonpath='{.status.conditions}'`.
- [ ] T5. Review ESO controller logs for the 15 minutes following rollout and confirm no error-level messages related to secret reconciliation, namespace validation, or Vault connectivity.

## Rollback
If the upgraded ESO controller fails readiness probes or ExternalSecret reconciliation breaks after the merge:

1. Revert the chart-version commit on the main branch (or push a revert commit) — ArgoCD reconciles and Helm downgrades the ESO Deployment.
2. If ArgoCD cannot reconcile (e.g., ESO controller crash-loop), run `kubectl rollout undo deployment/external-secrets -n admins` to restore the previous pod revision immediately.
3. Note: existing Kubernetes Secrets synced before the upgrade remain present in the cluster during and after rollback. Applications will not lose access to previously synced secret values during the rollback window.
4. Confirm all ExternalSecrets return to `Ready` condition after rollback by checking `kubectl get externalsecret -A`.
