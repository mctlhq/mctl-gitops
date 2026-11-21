# Tasks: incident-1806e566

1. [ ] Locate the ArgoCD Application / ApplicationSet entry and services/admins/mctl-agents-worker/values.yaml for admins-mctl-agents-worker in mctl-gitops; verify repoURL, path and targetRevision resolve.
2. [ ] Identify the field causing OutOfSync (render manifests and compare to the expected live state); apply the single narrow fix (correct path/revision, or add ignoreDifferences for that field).
3. [ ] Verify the change looks correct and touches nothing else; if no git-side cause exists, make no change and note that a manual ArgoCD refresh is required.
