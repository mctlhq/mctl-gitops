# Design: incident-92766580

## Confidence: LOW

## Diagnosis
The shepherd run itself worked: it committed and pushed its status update. The workflow failed only in the post-deploy-verify step, which saw argocd/labs-mctl-telegram become Degraded after the merge and stay Degraded past the 120s grace period. This is a downstream symptom of the mctl-telegram degradation, not a shepherd bug. The same service is failing its canary with "no active session" (see incident 533000a1-84f3-4960-a8db-cf24c39c5ca7, proposal incident-c39c5ca7). Current ArgoCD state is Degraded, Synced, image 0.89.0. The exact failing resource is not known.

## Proposed Fix
Do not change the shepherd. Fix the mctl-telegram degradation per proposal incident-c39c5ca7. After that, confirm labs-mctl-telegram is Healthy. If it is still Degraded, find the unhealthy resource (pod, probe or the preview deployment labs-mctl-telegram-preview) and fix it.

## Scope
Minimal. Verify only. Make no change if the other proposal resolves the health state.
