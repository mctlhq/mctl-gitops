# Design: incident-bdd1cf4b

## Confidence: LOW

## Diagnosis
ArgoCD application admins-mctl-agents-worker (project apps, destination namespace admins) has been OutOfSync for over an hour while Health is Healthy and the pod is serving normally with no errors in logs. The reported sync revision is empty, which suggests ArgoCD cannot resolve or compare a target revision, or that a field in the live object drifts from the rendered manifest (for example a controller- or mutating-webhook-managed field, or HPA/replica drift) without any workload failure. mctl-agent had no skill for ArgoCDApplicationOutOfSyncLong, so nothing was analysed. The root cause could not be confirmed from the available tools (no ArgoCD diff output was accessible).

## Proposed Fix
Verify first, then apply the minimal change:
1. Inspect platform-gitops/services/admins/mctl-agents-worker/values.yaml and the matching ArgoCD Application / ApplicationSet definition in mctl-gitops for the admins-mctl-agents-worker app. Confirm the targetRevision and path resolve to existing content (an empty revision suggests a bad or missing ref).
2. If the cause is a field that is mutated at runtime (replicas under HPA, webhook-injected annotations), add the corresponding ignoreDifferences entry for that field on this Application only.
3. If the cause is a wrong targetRevision/path, correct that single field.
4. If no drift cause can be identified from the repo, make no change and report that in the PR description.

## Scope
Minimal. Only touch the single field or rule that causes this specific OutOfSync state for admins-mctl-agents-worker. Do not alter other applications, sync policies globally, or any secrets/RBAC.
