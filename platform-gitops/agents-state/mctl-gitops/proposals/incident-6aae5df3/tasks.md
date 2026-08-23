# Tasks: incident-6aae5df3

1. [ ] Open `services/labs/mctl-telegram/values.yaml` in mctl-gitops
2. [ ] Locate the `podAnnotations` section (or create it if absent)
3. [ ] Add annotation: `deployment.restart-timestamp: "2026-08-23T03:00:47Z"`
4. [ ] Commit and push the change to trigger ArgoCD sync
5. [ ] Monitor mctl-telegram pod rollout to confirm new pods are created
6. [ ] Verify canary probe resumes passing in logs (look for successful probe step completions)
7. [ ] Wait for alert manager to detect probe recovery and clear the MctlTelegramCanaryFailing alert
