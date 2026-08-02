# Requirements: incident-227a5cc1

## Incident
- ID: 80d5a70d-07b4-4c68-84f8-434f09330ffb
- Tenant: admins
- Service: admins-openclaw
- Alert: argocd_app_degraded
- Created: 2026-07-31T07:09:58.226011Z
- Summary: ArgoCD application admins-openclaw OutOfSync for 1h

## Evidence
### Labels
- source: alertmanager
- type: argocd_app_degraded
- severity: warning
- occurrence_count: 1

### Diagnosis Context
ArgoCD application for tenant admins's openclaw service has been out of sync for over 1 hour. Same pattern as incident 77c6bed0 (ovk-openclaw). This suggests a systemic issue with either the ArgoCD controller or sync policies across multiple OpenClaw instances.

## Acceptance Criteria
- WHEN the ArgoCD application is synced THEN the OutOfSync alert stops firing.
- Verify that the application health is "Healthy" in ArgoCD UI.
