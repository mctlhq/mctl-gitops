# Requirements: incident-7c18baa2

## Incident
- ID: e56ead41-8282-4a11-b4ae-3bbd88351d36
- Tenant: admins
- Service: admins-openclaw
- Alert: argocd_app_degraded
- Created: 2026-07-25T18:42:19Z
- Summary: ArgoCD application admins-openclaw OutOfSync for 1h

## Evidence
### Labels
- source: alertmanager
- severity: warning
- status: analyzing
- occurrence_count: 1

### Log Snippet
ArgoCD application admins-openclaw has been OutOfSync for 1 hour. This typically indicates:
1. Kubernetes manifests in GitOps repo differ from live cluster state
2. ArgoCD sync policy is not set to auto-sync
3. Helm values or base configuration has drifted

## Acceptance Criteria
- WHEN the sync policy is corrected or manifests are synchronized THEN the OutOfSync alert stops firing for this service.
