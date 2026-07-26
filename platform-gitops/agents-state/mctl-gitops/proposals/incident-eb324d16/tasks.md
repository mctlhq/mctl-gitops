# Tasks: incident-eb324d16

1. [ ] Verify the current resource limits for nfc-quirestack-api deployment (check pod requests/limits)
2. [ ] Inspect ArgoCD app health via `argocd app get nfc-quirestack-api` to confirm unhealthy resource
3. [ ] If readiness timeout: increase pod memory request from current value to 512Mi
4. [ ] If memory is sufficient: check RBAC ClusterRole permissions and image pull secrets
5. [ ] Apply the resource change to `helm/charts/quirestack-api/values-nfc.yaml`
6. [ ] Verify the ArgoCD sync completes successfully and app health returns to Healthy
7. [ ] Confirm the alert stops firing
