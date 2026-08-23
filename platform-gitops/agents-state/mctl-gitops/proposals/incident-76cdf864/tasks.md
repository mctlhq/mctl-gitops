# Tasks: incident-76cdf864

1. [ ] Locate `services/labs/mctl-telegram/values.yaml` in mctl-gitops
2. [ ] Add or update `podAnnotations` with timestamp: `deployment.restart-timestamp: "2026-08-23T03:00:47Z"`
3. [ ] Commit the change to trigger ArgoCD sync
4. [ ] Wait for ArgoCD to apply the change and roll out new pods (pods will restart)
5. [ ] Verify the canary probe resumes passing by checking mctl-telegram logs for successful probe runs
6. [ ] Confirm ArgoCD marks the labs-mctl-telegram application as Synced and Healthy
