# Requirements: incident-d47188b2

## Incident
- ID: f0a20bacade0428bb7ecbba3d47188b2
- Tenant: admins
- Service: openclaw
- Alert: ArgoCDApplicationOutOfSyncLong
- Created: 2026-08-29T20:27:20Z

### Summary
ArgoCD application admins-openclaw OutOfSync for 1h. The application is Healthy (all pods running), but ArgoCD reports a sync status mismatch for over one hour.

## Evidence
### Labels
alert: ArgoCDApplicationOutOfSyncLong
severity: warning
type: argocd_app_degraded

### Log Snippet
No application logs available. ArgoCD status shows:
- health: Healthy
- syncStatus: OutOfSync
- revision: empty
- updatedAt: 2026-08-29T20:58:48Z

## Acceptance Criteria
- WHEN the ArgoCD application auto-sync is enabled and refreshed THEN the OutOfSync status clears and the application reaches InSync state.
