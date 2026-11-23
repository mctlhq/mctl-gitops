# Tasks: incident-0b2f8701

1. [ ] Review platform-gitops/services/admins/mctl-agents-worker values and Application sync policy for admins-mctl-agents-worker; identify the drifting resource/field.
2. [ ] If drift is a controller-mutated field, add a narrow ignoreDifferences entry; if a real pending change, fix sync policy. If undeterminable, make no change and note it in the PR description.
3. [ ] Verify the change is limited to this one service and does not alter image tag 1.117.0.
