# Design: incident-76648d7c

## Diagnosis
The ovk-openclaw ArgoCD application has been out of sync for over an hour despite the pod being Healthy. The empty revision field and OutOfSync status indicate that ArgoCD has not successfully synced the application. This typically occurs when:
1. Auto-sync is disabled on the application
2. There is a pending sync operation
3. ArgoCD has not refreshed its view of the application state

The fix is to ensure the ArgoCD Application manifest for ovk-openclaw has automatic syncing enabled with the syncPolicy.automated directive, allowing ArgoCD to automatically reconcile any drift.

## Confidence: LOW
Cannot access ArgoCD application manifests directly to verify current configuration. Diagnosis based on status fields and common ArgoCD patterns.

## Proposed Fix
In the mctl-gitops repository, ArgoCD Application CR for ovk-openclaw (located at platform-gitops/argocd-apps/apps/ovk-openclaw.yaml or similar path):
- Ensure syncPolicy.automated is set to true
- Ensure no manual sync requests are blocked
- Add selfHeal: true to enable automatic reconciliation
- Verify the git revision matches the deployed state
