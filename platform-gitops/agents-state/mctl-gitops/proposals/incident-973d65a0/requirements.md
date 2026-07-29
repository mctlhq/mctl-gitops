# Requirements: incident-973d65a0

## Incident
- ID: f94e64a7-577a-4254-b5ba-9752c4e0f048
- Tenant: argo-workflows
- Service: mctl-agents-issue-poll-1785258000-clone
- Alert: Pod container waiting longer than 1 hour
- Created: 2026-07-28T18:01:45Z
- Summary: Pod container waiting longer than 1 hour

## Evidence
### Labels
- Type: generic
- Source: alertmanager
- Severity: warning
- Status: analyzing

### Log Snippet
No logs available (pod stuck in waiting state, never reached running).

## Acceptance Criteria
- WHEN the cluster resource availability is improved or pod scheduling timeout is adjusted THEN the pod transitions from Waiting to Running state and the alert stops firing for this tenant/service.
