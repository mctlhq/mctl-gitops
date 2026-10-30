# Tasks: incident-3c416177

1. [ ] Verify the alert MctlTelegramToolAvailabilityFastBurn is no longer firing and labs-mctl-telegram is Healthy/Synced; if so, make no change and stop.
2. [ ] If still firing, review readiness probe and rollout settings in platform-gitops/services/labs/mctl-telegram/values.yaml for a no-ready-pod window during deploys.
3. [ ] Apply only the minimal change identified in step 2, if any.
