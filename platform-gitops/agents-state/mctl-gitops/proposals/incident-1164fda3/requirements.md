# Requirements: incident-1164fda3

## Incident
- ID: 77c6bed0-8a1d-4bc5-b9f9-d72e8afff0cd
- Tenant: ovk
- Service: ovk-openclaw
- Alert: argocd_app_degraded
- Created: 2026-07-31T07:09:58.24156Z
- Summary: ArgoCD application ovk-openclaw OutOfSync for 1h

## Evidence
### Labels
- source: alertmanager
- type: argocd_app_degraded
- severity: warning
- occurrence_count: 1

### Diagnosis Context
ArgoCD application for tenant ovk's openclaw service has been out of sync for over 1 hour. This indicates a drift between the desired state in the git repository and the live cluster state. No recent logs available from Loki (service may have been unavailable or recently restarted).

## Acceptance Criteria
- WHEN ArgoCD is manually synced or auto-sync is triggered for the ovk-openclaw application THEN the OutOfSync alert stops firing.
- Verify that the application health is "Healthy" in ArgoCD UI.
