# Design: incident-f9a3e210

## Diagnosis
ArgoCD OutOfSync alert for ovk-openclaw follows the same pattern as the admins-openclaw incident: the deployed application has drifted from the desired GitOps state and has not been synced for 1+ hour. This is consistent with manual-sync-only policy without automatic reconciliation.

Root cause: ovk-openclaw application sync policy does not have auto-sync enabled, or the webhook refresh failed to trigger an immediate sync after a recent commit.

## Proposed Fix
File: platform-gitops/tenants/ovk/openclaw/argocd-app.yaml (or equivalent)
Field: spec.syncPolicy.automated
Current value: null or missing (manual sync)
New value: { allow: true, prune: true, selfHeal: true }

If auto-sync is already enabled, run an immediate ArgoCD sync to resolve drift.

## Scope
Minimal. Only enable or refresh the sync policy for the ovk-openclaw application.
