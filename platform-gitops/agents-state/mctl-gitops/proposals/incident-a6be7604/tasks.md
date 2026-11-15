# Tasks: incident-a6be7604

1. [ ] Read platform-gitops/services/admins/mctl-agents-worker/values.yaml and the ArgoCD Application manifest for admins-mctl-agents-worker; identify which resource differs from live state (diagnosis confidence is LOW, verify first).
2. [ ] Apply the minimal fix: either correct the single stale values field or add a narrowly scoped ignoreDifferences entry for the drifting field only.
3. [ ] Verify the change renders cleanly (helm template / CI checks) and touches only admins-mctl-agents-worker.
4. [ ] If no drift can be identified from git, make no change and note this in the PR description for human triage.
