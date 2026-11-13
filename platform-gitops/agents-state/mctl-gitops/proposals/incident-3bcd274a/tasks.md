# Tasks: incident-3bcd274a

1. [ ] Read platform-gitops/services/admins/mctl-agents-worker/values.yaml and the Application manifest for admins-mctl-agents-worker; identify which resource/field differs from live state.
2. [ ] If a controller-mutated field is the cause, add a scoped ignoreDifferences entry for it; otherwise align values with intended state.
3. [ ] If no cause is found in git, make no change and note that manual ArgoCD diff inspection is needed.
4. [ ] Verify the change touches only this application and looks correct.
