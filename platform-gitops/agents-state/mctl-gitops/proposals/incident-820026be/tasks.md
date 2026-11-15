# Tasks: incident-820026be

1. [ ] Inspect platform-gitops/services/admins/mctl-agents-worker/values.yaml and the ArgoCD Application for admins-mctl-agents-worker; identify which resource and field is OutOfSync.
2. [ ] Apply the narrowest fix for that field (ignoreDifferences entry, values correction, or source path/revision fix).
3. [ ] Verify the change renders cleanly and touches only this service; if the drift cannot be identified, make no change and explain in the PR description.
