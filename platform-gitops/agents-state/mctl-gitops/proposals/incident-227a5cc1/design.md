# Design: incident-227a5cc1

## Diagnosis
The ArgoCD application admins-openclaw is in OutOfSync state. This is the second incident of the same type affecting a different OpenClaw tenant. Root cause is likely one of: (1) ArgoCD auto-sync is disabled or broken on both applications, (2) a recent configuration drift on both services, or (3) a cluster-level issue affecting ArgoCD's ability to sync. The fact that two separate tenants' OpenClaw instances both show this issue suggests a common cause rather than individual service problems.

## Proposed Fix
1. Check the ArgoCD controller health and logs to see if there is a systemic issue preventing syncs.
2. Locate the ArgoCD Application manifest for admins-openclaw:
   - File: `platform-gitops/argocd/applications/admins-openclaw.yaml`
   - Verify syncPolicy.automated is enabled:
     ```yaml
     spec:
       syncPolicy:
         automated:
           prune: true
           selfHeal: true
     ```
3. If auto-sync is already enabled and controller is healthy, trigger a manual sync via ArgoCD CLI.

## Scope
Minimal. Only enable or verify auto-sync on admins-openclaw and check controller health. No cascading changes.

## Confidence: MEDIUM
Pattern matches incident-1164fda3. Without access to live ArgoCD state, the exact root cause (application-level or controller-level) cannot be confirmed.
