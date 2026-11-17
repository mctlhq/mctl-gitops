# Design: incident-c9b1d97a

## Confidence: LOW

## Diagnosis
The ArgoCD application admins-mctl-agents-worker is Healthy but reports syncStatus OutOfSync with an empty revision. The workload runs normally (image 1.117.0) and its logs show no error. mctl-agent had no skill for ArgoCDApplicationOutOfSyncLong, so nothing was analysed. Likely causes are persistent drift in a field mutated at runtime (for example an HPA-managed replica count or a controller-injected field) with no ignoreDifferences entry, or a values.yaml in platform-gitops/services/admins/mctl-agents-worker that does not render cleanly. The exact diff is not observable with the available tools, so this cannot be confirmed.

## Proposed Fix
1. Inspect platform-gitops/services/admins/mctl-agents-worker/values.yaml and the ArgoCD Application definition for admins-mctl-agents-worker, and identify the resource and field that differ between desired and live state.
2. If the drift is a runtime-mutated field, add a matching ignoreDifferences entry (or fix the values so the rendered manifest equals live state).
3. If no drift cause is found in the manifests, make no change and note that in the PR description so a human can run an ArgoCD diff.

## Scope
Minimal. Only touch the single field or rule that causes this specific OutOfSync state. Do not change image tags or unrelated values.
