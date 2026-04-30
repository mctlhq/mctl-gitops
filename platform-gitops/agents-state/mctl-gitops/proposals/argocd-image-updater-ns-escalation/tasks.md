# Tasks: argocd-image-updater-ns-escalation

- [ ] 1. Audit all ArgoCD Application resources for `argocd-image-updater.argoproj.io/*`
        annotations across both `admins` and `labs` namespaces — DoD: a documented list
        (or confirmed empty set) of Applications that actively use Image Updater, committed
        to the relevant ADR or decision log.

- [ ] 2. Decision gate: based on task 1, choose Option A (upgrade) or Option B (remove)
        and record the decision in `context/decisions/` as an ADR — DoD: ADR file
        committed and merged; action path agreed by platform team.

- [ ] 3a. (Option A — depends on 2) Identify the first upstream Image Updater release that
         patches CVE-2026-6388 — DoD: release tag noted in the ADR; image digest pinned.

- [ ] 3b. (Option A — depends on 3a) Update the Image Updater image tag in the relevant
          manifest or Helm values file under `platform-gitops/` — DoD: PR merged; ArgoCD
          sync completes without errors; Image Updater Pod shows `Running` with the new
          image digest.

- [ ] 3c. (Option A — depends on 3b) Convert Image Updater ClusterRole to a namespaced
          Role bound only to the namespace(s) confirmed in task 1 — DoD: ClusterRole and
          ClusterRoleBinding removed; namespaced Role and RoleBinding committed; ArgoCD
          sync clean; no RBAC-related errors in Image Updater logs.

- [ ] 3d. (Option B — depends on 2) Remove Image Updater Deployment, ServiceAccount,
          Role/ClusterRole, RoleBinding/ClusterRoleBinding from bootstrap chart — DoD:
          all resources deleted from cluster confirmed via `kubectl get` in both namespaces;
          ArgoCD sync reports no orphaned resources.

- [ ] 4. (depends on 3b or 3d) Update `context/current-version.md` or the relevant
         service manifest to reflect the change — DoD: file updated, committed, and merged.

## Tests

- [ ] T1. (Option A) Attempt to create an ImageUpdater resource in the `labs` namespace
          that references an Application in `admins` namespace; verify the update is
          rejected and an audit log entry is emitted — DoD: test script output shows
          rejection with expected error; log entry confirmed in Image Updater logs.

- [ ] T2. (Option A) Verify that a legitimate ImageUpdater resource in `labs` targeting a
          `labs` Application successfully triggers an image update — DoD: image tag on the
          target Application is updated as expected within the polling interval.

- [ ] T3. (Option B) After removal, verify that no Image Updater Pods or RBAC objects
          remain in either namespace — DoD: `kubectl get deployment,sa,role,rolebinding
          -A | grep image-updater` returns empty.

- [ ] T4. ArgoCD health check: both `admins` and `labs` ApplicationSets show `Healthy`
          and `Synced` after the change — DoD: ArgoCD UI / CLI confirms status; no
          degraded Applications.

## Rollback
- **Option A rollback:** revert the image tag commit in `mctl-gitops`; ArgoCD will
  re-sync to the previous image. If the ClusterRole was already converted to a Role,
  revert that commit as well. ArgoCD performs a rolling update back to the previous Pod.
- **Option B rollback:** revert the deletion commit; ArgoCD will re-create all deleted
  resources on the next sync. The Image Updater Deployment will restart from the image
  tag present in the reverted manifest.
- In either case, the rollback commit must be merged and synced within one sync interval
  (default 3 minutes) to minimize the window of divergence.
