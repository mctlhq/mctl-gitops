# Design: incident-db3e25e7

## Confidence: LOW

## Diagnosis
The ArgoCD application admins-mctl-agents-worker is Healthy and the pod is serving normally (polling, policy decisions ALLOW, API calls 200), but ArgoCD reports syncStatus OutOfSync with an empty revision for over an hour. mctl-agent had no skill for ArgoCDApplicationOutOfSyncLong, so nothing was analysed. An empty revision suggests ArgoCD cannot resolve or compare the target revision (repo-server/manifest generation error, or a values.yaml / Application source reference that does not render), or there is persistent drift on a live field (for example a controller-mutated field not covered by ignoreDifferences). Logs alone do not identify which. A Temporal DeadlockError (TMPRL1101) appears in worker logs; it is probably unrelated to sync state but is noted as a separate observation. No instructions were found in the incident text.

## Proposed Fix
1. Inspect platform-gitops/services/admins/mctl-agents-worker/values.yaml and the generated ArgoCD Application for admins-mctl-agents-worker; confirm it renders with `helm template` against the base-service chart and that the targetRevision / source path are valid.
2. If a rendering or schema error is found, fix that specific field.
3. If the diff is only a controller-mutated field (e.g. replicas, status-like annotations), add a narrowly scoped ignoreDifferences entry for that field only.
4. If nothing is wrong in gitops, record the finding in the PR description rather than changing anything.

## Scope
Minimal. Only touch the single field or rule that causes this specific OutOfSync state. Do not change image tag, resources or unrelated services.
