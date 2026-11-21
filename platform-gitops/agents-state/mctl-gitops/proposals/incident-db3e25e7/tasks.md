# Tasks: incident-db3e25e7

1. [ ] Render platform-gitops/services/admins/mctl-agents-worker/values.yaml with the base-service chart and identify why ArgoCD shows OutOfSync with empty revision
2. [ ] Apply the minimal fix (invalid field correction or narrowly scoped ignoreDifferences) in mctl-gitops
3. [ ] Verify the rendered diff is limited to that one change and the ArgoCD app would report Synced
