# Design: incident-820026be

## Confidence: LOW

## Diagnosis
The ArgoCD application admins-mctl-agents-worker is Healthy but OutOfSync, and its reported revision is empty. The workload itself runs fine (image 1.117.0, normal Temporal and API traffic in logs), so this is a manifest drift or sync-comparison problem, not a runtime failure. mctl-agent had no skill for ArgoCDApplicationOutOfSyncLong, so nothing was analysed. Likely causes, none verified: (a) a field in the rendered Helm output differs from the live object, for example a value mutated by a controller or an ignoreDifferences gap; (b) the Application points at a path or revision that failed to render; (c) a recent values.yaml change that was committed but not synced. The unrelated log warnings (branch-protection probe 403, executions/context 404) are not connected to sync state.

## Proposed Fix
Investigate before editing. In mctl-gitops, inspect platform-gitops/services/admins/mctl-agents-worker/values.yaml and the ArgoCD Application definition for admins-mctl-agents-worker. Compare the rendered chart (base-service) against the live resource diff reported by ArgoCD. Then apply the narrowest fix that matches the diff, one of:
- add an ignoreDifferences entry for the specific controller-managed field, or
- correct the values.yaml field that renders differently from the live object, or
- fix the Application source path or targetRevision if it renders no revision.
If the diff cannot be determined from the repository alone, make no change and record the finding in the PR description.

## Scope
Minimal. Only touch the single field or rule that causes this OutOfSync state for admins-mctl-agents-worker. Do not change image tags, secrets, network policy, or other services.
