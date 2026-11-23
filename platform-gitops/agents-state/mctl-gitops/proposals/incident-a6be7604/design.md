# Design: incident-a6be7604

## Confidence: LOW

## Diagnosis
The ArgoCD application admins-mctl-agents-worker is Healthy (pods run and process work normally) but reports OutOfSync with an empty revision, and the alert fired after one hour of this state. Service logs contain no sync-related errors, so the cause is not visible from the workload; mctl-agent had no skill for this alert and diagnosed nothing. Likely candidates, all unverified: (1) a field in the rendered manifests that drifts from live state (for example a controller-mutated field, or a value like the image tag 1.117.0 in platform-gitops/services/admins/mctl-agents-worker/values.yaml that does not match what is deployed), requiring an ignoreDifferences entry or a values correction; (2) an Application-level problem (the empty revision suggests the app has not resolved a target revision recently, e.g. a repo-server or manifest-generation error). The implementer must verify before changing anything.

## Proposed Fix
1. Inspect platform-gitops/services/admins/mctl-agents-worker/values.yaml and the Application definition for admins-mctl-agents-worker; compare with the live resources to find the drifting resource.
2. If the diff is a controller-mutated or defaulted field, add a narrowly scoped ignoreDifferences entry for that single field on that Application.
3. If values.yaml is stale or invalid, correct the single offending field.
4. If no drift is identifiable in git, make no change and record that in the PR description for human triage.

## Scope
Minimal. Only touch the single field or rule that causes this specific OutOfSync state for admins-mctl-agents-worker. Do not alter other applications, sync policies globally, or RBAC. The unrelated warnings in the worker logs (branch-protection probe permission, 404 on executions/context) are out of scope.
