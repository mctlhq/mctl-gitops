# Design: incident-84e0e5bf

## Confidence: LOW

## Diagnosis
The ArgoCD application admins-mctl-agents-worker is Healthy (pods running image 1.117.0 and processing work) but has been OutOfSync for over an hour. mctl-agent had no skill for ArgoCDApplicationOutOfSyncLong, so nothing was analysed. Pod logs contain no sync-related errors, so the cause is not visible from the service side. The reported sync revision is empty, which suggests the Application has not resolved a target revision (repo-server render failure, a recent gitops commit that changed the service values, or a live-vs-desired drift such as a field mutated by a controller or an HPA/replica difference). The two log warnings (404 on executions/context, branch-protection GraphQL permission) are unrelated to ArgoCD sync and are not the cause.

## Proposed Fix
Cannot be determined from available evidence. The implementer should verify before changing anything:
1. Inspect platform-gitops/services/admins/mctl-agents-worker/values.yaml and the Application manifest for this service; check recent commits touching them for invalid or non-rendering values.
2. Determine which resources are OutOfSync (ArgoCD diff). If the drift is a field mutated at runtime (e.g. replicas managed by HPA, defaulted fields), add the matching ignoreDifferences entry to the Application definition for that field only.
3. If the diff comes from a rendering error or a stale values field, correct that single field in values.yaml.
If no concrete cause is found in gitops, make no change and note that in the PR description.

## Scope
Minimal. Only touch the single field or ignoreDifferences rule that causes this specific OutOfSync state for admins-mctl-agents-worker.
