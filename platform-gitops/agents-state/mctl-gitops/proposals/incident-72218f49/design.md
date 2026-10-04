# Design: incident-72218f49

## Confidence: LOW

## Diagnosis
The ArgoCD application argocd-self-managed has been OutOfSync for over one hour. mctl-agent had no skill matching ArgoCDApplicationOutOfSyncLong, so nothing was analysed. No logs were available from Loki (the app is not a long-lived service pod) and the incident carries no labels or evidence, so the root cause is unknown. Likely candidates: a drift between the live ArgoCD resources and the manifests in mctl-gitops (for example a field mutated by a controller and missing from ignoreDifferences), a failed or pending sync, or a chart/values change that has not been applied. The implementer must verify before changing anything.

## Proposed Fix
1. Inspect the Application manifest for argocd-self-managed under platform-gitops in mctl-gitops and identify which resources are OutOfSync (the sync status diff).
2. If the drift is a controller-mutated field, add a narrowly scoped ignoreDifferences entry for that resource and field only.
3. If the drift is caused by a manifest error in the repo, correct that single value.
4. If nothing in the repo explains the drift, make no change and report that a human needs to check the live diff.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert. Do not change sync policy, prune settings, or RBAC.
