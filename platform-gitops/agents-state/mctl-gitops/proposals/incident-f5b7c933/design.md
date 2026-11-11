# Design: incident-f5b7c933

## Confidence: LOW

## Diagnosis
The ArgoCD application admins-mctl-agents-worker is Healthy but reports OutOfSync, and has stayed so for over an hour. The workload itself is fine: logs show normal operation with no crashes or errors. mctl-agent had no skill for this alert, so nothing was analysed. Likely causes are drift between live and desired manifests: a field mutated by a controller or operator (for example HPA-managed replicas, defaulted fields, or a second Deployment such as the "-exec" variant) that is not covered by ignoreDifferences, or a pending out-of-band change. The sync revision is empty in the status, which suggests the app has not completed a recent comparison or sync. The exact diff could not be observed with the available tools.

## Proposed Fix
1. In platform-gitops/services/admins/mctl-agents-worker/ (values.yaml and any app definition), compare the rendered Helm output against the live resources and identify which resource/field differs.
2. If the diff comes from a controller-managed field, add a matching ignoreDifferences entry to the ArgoCD Application for admins-mctl-agents-worker (or fix the values so the rendered manifest equals the live state).
3. If there is no persistent diff, no change is needed beyond a refresh/sync; in that case record this finding in the PR description and make no file change.

## Scope
Minimal. Only touch the single field or rule that causes this specific OutOfSync state for admins-mctl-agents-worker. Do not change image tags, resources, or other services.
