# Requirements: incident-a58acb7b

## Incident
- ID: 7e0dbb7c-991a-4e28-809b-0ef0a26457c1
- Tenant: argo-workflows
- Service: mctl-agents-issue-poll-1785258000-notify
- Alert: Pod container waiting longer than 1 hour
- Created: 2026-07-28T22:03:02Z
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
