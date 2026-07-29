# Tasks: incident-c33cf596

1. [ ] Verify that BETTER_AUTH_SECRET is defined in the nfc tenant Vault or environment variable store, and that the quirestack-web Helm deployment includes it as an env var (check the deployment manifest or values.yaml).
2. [ ] If BETTER_AUTH_SECRET is missing, add it to the Vault path `secret/data/teams/nfc/quirestack-web/` and ensure the Helm template references it.
3. [ ] Verify the quirestack-web deployment is using the latest build (check the image tag in the ArgoCD Application or Helm values).
4. [ ] If the image tag is stale, bump it to the latest version to force a rolling restart and invalidate build caches.
5. [ ] Apply a rolling restart by adding or updating the `mctl.ai/restart-timestamp` annotation in the deployment template.
6. [ ] Sync the ArgoCD Application for nfc-quirestack-web to apply the changes.
7. [ ] Monitor the ArgoCD health status — it should return to Healthy within 2-3 minutes of the rolling restart.
8. [ ] Verify the pod logs no longer show "BETTER_AUTH_SECRET" errors or server action reference ID failures.
