# Tasks: argocd-repo-server-rce-network-isolation

- [ ] 1. Confirm the cluster's CNI enforces Kubernetes NetworkPolicy
      resources. — DoD: written confirmation (e.g. CNI product/version and
      documentation reference, or a quick test policy that provably blocks
      traffic) that NetworkPolicy is enforced in this cluster.
- [ ] 2. Identify the actual labels/selectors used by the deployed
      `argocd-repo-server`, `argocd-server`, and `argocd-application-controller`
      pods and their namespace (depends on 1). — DoD: exact label
      key/value pairs and namespace documented, sourced from the running
      cluster or the Argo CD chart's rendered manifests in this repo.
- [ ] 3. Author the NetworkPolicy manifest restricting ingress to the
      repo-server's internal port to only pods matching the
      `argocd-server` and `argocd-application-controller` selectors
      identified in task 2, placed under `platform-gitops/apps/` (or the
      appropriate Argo CD control-plane manifest location) (depends on 2).
      — DoD: manifest committed to this repo following existing YAML
      conventions (2-space indent).
- [ ] 4. Roll out via the standard ArgoCD sync flow and verify the policy
      is applied without manual `kubectl apply` (depends on 3). — DoD:
      `kubectl get networkpolicy` (or mctl equivalent) shows the resource
      Synced/Healthy in ArgoCD.
- [ ] 5. Verify normal Argo CD sync operations continue to succeed across a
      representative sample of Applications in `admins` and `labs`
      (depends on 4). — DoD: no new sync failures or manifest-rendering
      errors attributable to the NetworkPolicy in the 24 hours following
      rollout.

## Tests
- [ ] T1. From a pod without the allowed labels, attempt to reach the
      repo-server's internal port and confirm the connection is refused.
- [ ] T2. From an `argocd-server` pod, confirm the repo-server connection
      still succeeds (manifest rendering requests complete normally).
- [ ] T3. From an `argocd-application-controller` pod, confirm the
      repo-server connection still succeeds.
- [ ] T4. Trigger a full sync of a representative Application in `admins`
      and one in `labs` and confirm both complete successfully post-rollout.

## Rollback
Delete/revert the NetworkPolicy manifest commit and let ArgoCD self-sync
remove the resource, restoring the prior (unrestricted) network posture for
the repo-server. Since this is a single additive manifest with no
dependent resources, rollback is a one-line git revert with no data or
schema migration concerns. If task 5 finds sync failures, revert
immediately and re-verify the label selectors from task 2 before
reapplying.
