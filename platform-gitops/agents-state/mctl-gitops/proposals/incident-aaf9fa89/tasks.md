# Tasks: incident-aaf9fa89

1. [ ] Check platform-gitops/services/admins/openclaw/application.yaml or values.yaml
2. [ ] Verify that syncPolicy.automated is enabled (prune=true, selfHeal=true)
3. [ ] If sync is disabled, enable it; if enabled, check ArgoCD logs for sync errors
4. [ ] If there are validation errors in the manifest, correct them
5. [ ] Trigger manual sync in ArgoCD if automatic sync is now enabled
6. [ ] Verify that the application reaches Synced status
