# Design: incident-d7b7eb91

## Confidence: LOW

## Diagnosis
The ArgoCD application admins-mctl-agents-worker is Healthy and its pods run normally (logs show no errors), but syncStatus is OutOfSync and the reported revision is empty. mctl-agent had no skill for ArgoCDApplicationOutOfSyncLong, so nothing was analysed. The service has two workloads (admins-mctl-agents-worker and admins-mctl-agents-worker-exec), which suggests a persistent diff between the live and desired manifests (for example a field mutated by a controller or HPA, or a values/chart mismatch in the gitops definition) rather than a runtime failure. The exact diff could not be observed with the available tools, so the root cause is unconfirmed.

## Proposed Fix
1. Inspect platform-gitops/services/admins/mctl-agents-worker/values.yaml (and the related -exec instance, if defined separately) and the ArgoCD Application for this service, looking for fields that drift from live state (replicas managed by autoscaling, defaulted or mutated fields, a stale image tag versus 1.117.0).
2. If a drifting field is found, either set the desired value to match the live state or add an ignoreDifferences entry for that single field in the Application.
3. If no drift cause is found in the repo, make no change and report that a manual `argocd app diff admins-mctl-agents-worker` is needed.

## Scope
Minimal. Only touch the single field or rule that causes this specific OutOfSync state. Do not change unrelated services.
