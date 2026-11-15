# Design: incident-0b2f8701

## Confidence: LOW

## Diagnosis
The ArgoCD application admins-mctl-agents-worker is Healthy (pod running, worker processing normally) but has been OutOfSync for over an hour, with an empty revision reported. mctl-agent had no skill for this alert, so nothing was analysed. Logs do not point at a cause; the worker is functioning. Likely causes are drift between live manifests and the rendered chart in platform-gitops/services/admins/mctl-agents-worker (e.g. a field mutated by a controller or HPA/replica drift, a missing ignoreDifferences entry, or a values change not yet synced with automated sync disabled/failing). The 404 on mctl-api executions/context and the branch-protection warning are unrelated to ArgoCD sync.

## Proposed Fix
Verify first, do not change blindly:
1. Inspect platform-gitops/services/admins/mctl-agents-worker/values.yaml and the Application definition for admins-mctl-agents-worker (sync policy, ignoreDifferences).
2. If the diff is a controller-mutated field (replicas, caBundle, status-like field), add a narrow ignoreDifferences entry for that single field.
3. If the diff is a real pending change and automated sync is off, enable or trigger the sync via the normal GitOps path.
4. If no diff can be identified from the repo, make no change and record that a live `argocd app diff` is needed.

## Scope
Minimal. Only touch the single field or sync setting that causes this OutOfSync state.
