# Tasks: eso-dns-exfil-patch

- [ ] 1. Verify patch inclusion in `helm-chart-2.4.1` — DoD: inspect `helm-chart-2.4.1`'s
  `Chart.yaml` and controller image tag to confirm it ships ESO v2.2.1+; if not, identify
  the correct Helm chart version that does and document it.

- [ ] 2. Audit existing ExternalSecret manifests for `getHostByName` usage (depends on 1) —
  DoD: a grep/search of all files under `platform-gitops/argo-workflows/secrets/` confirms
  zero occurrences of `getHostByName`; findings (if any) are documented in the PR description.

- [ ] 3. Identify ESO CRD changes between current version and v2.2.1 (depends on 1) — DoD:
  `kubectl diff` output for CRD resources is reviewed; any new required fields or schema
  constraints are listed; dry-run validation passes.

- [ ] 4. Apply ESO CRD updates to the cluster (depends on 3) — DoD: `kubectl apply -f crds/`
  completes without errors; existing ExternalSecret, ClusterSecretStore, and SecretStore
  objects remain in a valid state.

- [ ] 5. Update the ESO Helm chart version pin in `platform-gitops/` to the patched chart
  (depends on 2 and 4) — DoD: the relevant Helm values or ApplicationSet manifest references
  `helm-chart-2.4.1` (or confirmed patched version); change is committed and a PR is raised.

- [ ] 6. Merge and observe ESO upgrade via ArgoCD reconciliation (depends on 5) — DoD: ESO
  controller pods are running v2.2.1+; no CrashLoopBackOff; all ExternalSecrets across all
  tenant namespaces show `Ready=True` within 5 minutes of the rollout.

- [ ] 7. Add CI gate to reject ExternalSecret manifests containing `getHostByName` (depends on 6)
  — DoD: a Conftest policy or grep-based CI step fails the pipeline for any file in
  `platform-gitops/argo-workflows/secrets/` that contains the string `getHostByName`;
  gate is active on the main branch.

## Tests

- [ ] T1. Exploit reproduction test: create a test ExternalSecret with a template body containing
  `{{ getHostByName "test" }}` and apply it to a non-production namespace; assert that ESO
  v2.2.1+ rejects it with status condition `Ready=False` and reason `TemplateFunctionDenied`
  (or equivalent); assert no DNS query for `test` appears in CoreDNS logs.
- [ ] T2. Regression test: confirm that all pre-existing ExternalSecret objects in
  `platform-gitops/argo-workflows/secrets/` still reconcile to `Ready=True` after the upgrade.
- [ ] T3. ClusterSecretStore health test: confirm that the `vault-backend` ClusterSecretStore
  shows a Valid status and that a sample secret fetch from Vault succeeds post-upgrade.
- [ ] T4. CI gate test: introduce a test branch with a fabricated ExternalSecret containing
  `getHostByName` and verify the CI pipeline rejects it with a clear error message referencing
  CVE-2026-34984.

## Rollback
1. Revert the Helm chart version-pin commit in `platform-gitops/` to the previous ESO chart
   version.
2. Push the revert commit; ArgoCD will reconcile ESO back to the previous controller version.
3. Kubernetes Secrets already synced by ESO remain intact regardless of controller version; no
   secret data is lost during rollback.
4. If CRDs were upgraded, revert them using `kubectl apply -f` from the previous CRD manifests
   stored in git history, verifying that no existing objects use fields introduced only in the
   newer CRD version.
5. After rollback, the `getHostByName` vulnerability is re-opened; ensure the repository
   `platform-gitops/argo-workflows/secrets/` write access is temporarily restricted until a
   re-attempt can be scheduled.
