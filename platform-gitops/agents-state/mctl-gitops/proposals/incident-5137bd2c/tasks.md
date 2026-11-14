# Tasks: incident-5137bd2c

1. [ ] Locate the ArgoCD Application (or ApplicationSet entry) named erpact-infra in mctl-gitops.
2. [ ] Check whether its source path and targetRevision exist; if not, remove the stale manifest, otherwise add a single ignoreDifferences entry for the drifting field.
3. [ ] If the cause cannot be confirmed from the repository, make no change and note that manual inspection is needed.
4. [ ] Verify the resulting diff is limited to that one Application.
