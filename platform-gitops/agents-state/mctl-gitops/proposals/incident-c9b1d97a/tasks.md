# Tasks: incident-c9b1d97a

1. [ ] Review platform-gitops/services/admins/mctl-agents-worker/values.yaml and its ArgoCD Application for the field causing OutOfSync drift.
2. [ ] Apply the minimal fix (ignoreDifferences entry or values correction) for that single field.
3. [ ] Verify the rendered manifests are valid and no unrelated values changed; if no cause is found, make no change and document it.
