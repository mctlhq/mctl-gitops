# Tasks: incident-3a73ead4

1. [ ] Edit `platform-gitops/services/labs/agent-worker-preview/values.yaml`:
       add a top-level `strategy:` block with `type: Recreate` (place it near
       `replicaCount`, e.g. directly after the `imagePullSecrets` block).
2. [ ] Verify the change renders correctly, e.g. `helm template` the
       `base-service` chart with this values file and confirm
       `spec.strategy.type: Recreate` appears on the Deployment and no other
       field changed.
3. [ ] No image tag, resource limit, or other values changes are needed for
       this fix.
4. [ ] If possible, confirm via ArgoCD/cluster state that the stuck
       ReplicaSet's pod was Pending with an exceeded-quota event, per the
       LOW-confidence note in design.md.
