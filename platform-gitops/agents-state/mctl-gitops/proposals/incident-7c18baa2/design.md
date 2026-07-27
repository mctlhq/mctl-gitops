# Design: incident-7c18baa2

## Diagnosis
ArgoCD OutOfSync alert for admins-openclaw indicates the deployed application has drifted from the desired GitOps state. The alert has been firing for 1+ hour without resolution, suggesting either:
1. The sync policy is not set to automatic (manual sync only)
2. A recent commit to the admins-openclaw Helm values or kustomize overlays has not propagated to the cluster
3. ArgoCD webhook refresh is delayed or misconfigured

The most likely fix: enable auto-sync on the admins-openclaw application in ArgoCD.

## Proposed Fix
File: platform-gitops/tenants/admins/openclaw/argocd-app.yaml (or equivalent)
Field: spec.syncPolicy.automated
Current value: null or missing (manual sync)
New value: { allow: true, prune: true, selfHeal: true }

If auto-sync is already enabled, run an immediate ArgoCD sync to resolve drift.

## Scope
Minimal. Only enable or refresh the sync policy for the admins-openclaw application.
