# Tasks: argocd-image-updater-ns-escalation

- [ ] 1. Identify the running argocd-image-updater version — inspect the image tag in
  `platform-gitops/services/admins/argocd-image-updater/values.yaml` (or equivalent path).
  DoD: current version recorded in a comment or PR description.

- [ ] 2. Check upstream argoproj-labs/argocd-image-updater releases for the version that patches
  CVE-2026-6388 — DoD: patched version tag confirmed, or confirmation that no patch exists yet
  (triggering Option B).

- [ ] 3. Apply Option A or B (depends on 2):
  - **Option A:** Update the image tag in the Helm values file to the patched release; add
    `--namespace admins` to the controller args.
  - **Option B:** Set `replicaCount: 0` and add a comment referencing CVE-2026-6388.
  DoD: git commit with the change; ArgoCD Application shows `Synced`.

- [ ] 4. Tighten the RBAC manifest — replace the ClusterRole binding with a Role + RoleBinding
  scoped to the `admins` namespace (depends on 3). DoD: `kubectl get clusterrolebinding` shows no
  image-updater cluster-level binding.

- [ ] 5. Validate cross-tenant isolation — create a test ImageUpdater annotation on a `labs`
  Application and confirm no update is triggered in `admins` (depends on 3, 4). DoD: ArgoCD
  audit log shows no cross-namespace image-update event.

## Tests

- [ ] T1. Attempt to create an ImageUpdater resource in `labs` that targets an `admins`
  Application — expect rejection or no-op with the patched version.
- [ ] T2. Confirm all `admins` Applications in ArgoCD are `Healthy` and `Synced` after the change.
- [ ] T3. Confirm all `labs` Applications in ArgoCD are `Healthy` and `Synced` (no side effects).
- [ ] T4. Run `kubectl auth can-i update applications.argoproj.io --as=system:serviceaccount:admins:argocd-image-updater -n labs` — must return `no`.

## Rollback

1. Revert the Helm values commit (`git revert <sha>`).
2. Push the revert commit; ArgoCD syncs back to the previous image-updater configuration.
3. If the ClusterRole was tightened in a separate commit, revert that commit as well.
