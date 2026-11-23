# Tasks: incident-84e0e5bf

1. [ ] Review platform-gitops/services/admins/mctl-agents-worker/values.yaml and recent commits for it; identify the field causing the OutOfSync diff
2. [ ] If drift is runtime-mutated, add a narrowly scoped ignoreDifferences entry; if values are invalid, fix that single field
3. [ ] Verify the change renders cleanly and touches only this service; if no cause is found, make no change and report it
