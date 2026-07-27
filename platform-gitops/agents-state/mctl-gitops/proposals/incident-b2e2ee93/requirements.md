# Requirements: incident-b2e2ee93

## Incident
- ID: 6d4ba6cb-e86f-4e7b-b112-36bf0d217112
- Tenant: nfc
- Service: monitoring-kube-state-metrics
- Alert: generic
- Created: 2026-07-26T19:31:45.32166Z
- Summary: Deployment rollout is not progressing.

## Evidence
### Labels
- Type: generic
- Severity: warning
- Status: analyzing
- Occurrence Count: 1

### Log Snippet
No application logs available. Service may be in a deployment pending state.
This is an infrastructure/Kubernetes-level deployment issue indicated by AlertManager
monitoring the Deployment resource state.

## Acceptance Criteria
- WHEN the deployment rollout is unblocked (pod replicas become ready) THEN the alert stops firing for this tenant/service.
