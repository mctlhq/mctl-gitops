# Requirements: incident-f9a3e210

## Incident
- ID: f62a7bd7-aa18-4b81-b922-65d3a6ac68fd
- Tenant: ovk
- Service: ovk-openclaw
- Alert: argocd_app_degraded
- Created: 2026-07-25T18:37:19Z
- Summary: ArgoCD application ovk-openclaw OutOfSync for 1h

## Evidence
### Labels
- source: alertmanager
- severity: warning
- status: analyzing
- occurrence_count: 1

### Log Snippet
ArgoCD application ovk-openclaw has been OutOfSync for 1 hour. This indicates the deployed application state does not match the desired state in the GitOps repository. Similar to admins-openclaw, this suggests a sync policy or manifest drift issue.

## Acceptance Criteria
- WHEN the sync policy is corrected or manifests are synchronized THEN the OutOfSync alert stops firing for this service.
