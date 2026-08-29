# Requirements: incident-76648d7c

## Incident
- ID: 75dee28b6d6c43a59ceaea8f76648d7c
- Tenant: ovk
- Service: openclaw
- Alert: ArgoCDApplicationOutOfSyncLong
- Created: 2026-08-29T20:27:20Z

### Summary
ArgoCD application ovk-openclaw OutOfSync for 1h. The application is Healthy (all pods running), but ArgoCD reports a sync status mismatch for over one hour.

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
- updatedAt: 2026-08-29T20:56:00Z

## Acceptance Criteria
- WHEN the ArgoCD application auto-sync is enabled and refreshed THEN the OutOfSync status clears and the application reaches InSync state.
