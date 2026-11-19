# Design: incident-1806e566

## Confidence: LOW

## Diagnosis
The ArgoCD application admins-mctl-agents-worker is Healthy and its pod runs normally (image 1.117.0, no errors in the last hour of logs), but ArgoCD reports syncStatus OutOfSync with an empty revision for over an hour. mctl-agent had no skill for ArgoCDApplicationOutOfSyncLong, so nothing was analysed. Likely causes, none confirmed from the available tools: (a) live-state drift on a field that ArgoCD diffs but a controller or mutating webhook rewrites (needs ignoreDifferences), (b) the Application source cannot resolve a revision (empty revision suggests a repo/path/targetRevision or manifest-generation problem), or (c) a stale sync that never completed. The service logs contain no evidence of an application-level fault, so this is a GitOps-level problem.

## Proposed Fix
Implementer should verify before applying:
1. Inspect the Application definition for admins-mctl-agents-worker in mctl-gitops (platform-gitops/ apps/ApplicationSet for tenant admins) and confirm source.repoURL, path (services/admins/mctl-agents-worker) and targetRevision resolve to an existing path and values.yaml.
2. Compare the rendered manifests with what ArgoCD reports as the diff. If the diff is a field mutated at runtime, add a narrow spec.ignoreDifferences entry for exactly that field. If the path or revision is wrong, correct that single field.
3. If no drift or misconfiguration is found in git, make no change and record that a manual ArgoCD hard refresh / sync is the needed action.

## Scope
Minimal. Only touch the single field or rule that causes this specific OutOfSync state for admins-mctl-agents-worker. Do not alter other services, secrets, or policies.
