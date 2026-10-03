# Tasks: incident-6c2905cf

1. [ ] Check whether `platform-gitops/services/labs/agent-worker-preview/values.yaml`
       already has a `strategy: {type: Recreate}` block (it may already have
       been added by sibling proposal `mctl-gitops/proposals/incident-
       3a73ead4`). If not, add it (place it near `replicaCount`, e.g.
       directly after the `imagePullSecrets` block).
2. [ ] Verify the change renders correctly, e.g. `helm template` the
       `base-service` chart with this values file and confirm
       `spec.strategy.type: Recreate` appears on the Deployment and no other
       field changed.
3. [ ] No image tag, resource limit, or other values changes are needed for
       this fix.
4. [ ] If possible, confirm via ArgoCD/cluster state that the stuck
       ReplicaSet's pod was Pending with an exceeded-quota event, per the
       LOW-confidence note in design.md.
