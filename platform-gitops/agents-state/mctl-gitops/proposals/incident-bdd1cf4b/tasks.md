# Tasks: incident-bdd1cf4b

1. [ ] Locate the ArgoCD Application definition for admins-mctl-agents-worker and its values at platform-gitops/services/admins/mctl-agents-worker/values.yaml; check targetRevision, path and any ignoreDifferences.
2. [ ] Identify the drift cause (bad or empty revision, or a runtime-mutated field); verify it before editing.
3. [ ] Apply the single minimal fix (correct the ref, or add a narrowly scoped ignoreDifferences entry); if no cause is found, make no change and say so in the PR.
4. [ ] Verify the diff touches only admins-mctl-agents-worker.
