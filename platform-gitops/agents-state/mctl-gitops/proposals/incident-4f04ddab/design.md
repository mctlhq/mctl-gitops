# Design: incident-4f04ddab

## Confidence: LOW

## Diagnosis
The ArgoCD app-of-apps `root-app` has been OutOfSync for over an hour. mctl-agent had no skill for ArgoCDApplicationOutOfSyncLong, so nothing was analysed. No logs were obtainable because `argocd` is not a tenant. The root cause is unknown. Likely candidates: a child Application manifest in mctl-gitops that is invalid or drifting, a field managed by a controller that needs ignoreDifferences, or a failed sync (for example a missing CRD or a validation error). The warning is not necessarily a defect in mctl-gitops.

## Proposed Fix
Do not guess a change. The implementer should first verify:
1. Inspect the root-app Application manifest in mctl-gitops and its rendered child Applications for schema or validation errors.
2. Identify which child resource is reported OutOfSync (if repo state is available) and compare the live and desired values.
3. If the diff is a controller-mutated field, add a narrowly scoped `ignoreDifferences` entry for that field only on the affected resource. If a manifest is invalid, fix that single manifest.
If no defect is found in the repository, make no change and note that a human needs to check the ArgoCD UI.

## Scope
Minimal. Only touch the single field or manifest that causes root-app to be OutOfSync. Make no broader sync-policy changes (such as enabling prune or force) without evidence.
