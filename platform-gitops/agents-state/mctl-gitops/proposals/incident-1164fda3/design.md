# Design: incident-1164fda3

## Diagnosis
The ArgoCD application ovk-openclaw is in OutOfSync state, which typically means either: (1) manual changes were applied to the cluster that drift from git, (2) the gitops repository was updated but ArgoCD has not synced, or (3) ArgoCD sync is disabled and needs a manual trigger. Given no error logs are visible and the service age (2+ days), this is likely a case where auto-sync did not trigger or manual intervention was needed. The fix is to ensure the ArgoCD Application resource has auto-sync enabled and is current.

## Proposed Fix
In the mctl-gitops repository, locate the ArgoCD Application manifest for ovk-openclaw:
- File: `platform-gitops/argocd/applications/ovk-openclaw.yaml` (or similar)
- Add or verify the syncPolicy field has auto-sync enabled:
  ```yaml
  spec:
    syncPolicy:
      automated:
        prune: true
        selfHeal: true
  ```
- If auto-sync is already enabled, trigger a manual sync via:
  ```bash
  argocd app sync ovk-openclaw
  ```

## Scope
Minimal. Only enable auto-sync on the ovk-openclaw application or trigger manual sync. No other services affected.

## Confidence: MEDIUM
Diagnosis is based on the alert summary and common ArgoCD patterns. Exact cause (manual drift vs. sync disabled) cannot be confirmed without access to live ArgoCD state or recent pod logs.
