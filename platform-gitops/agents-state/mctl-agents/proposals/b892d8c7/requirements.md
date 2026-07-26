# Requirements: b892d8c7

## Incident
- ID: argo-mctl-agents-incidents-1785053700-1785053856
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Job: incident-responder
- Created: 2026-07-26T08:17:36.208495Z
- Summary: mctl-agents-run incident-responder Failed after 150.095632s

## Evidence
### Labels
- source: argo-workflows
- type: workflow_failed
- fingerprint: workflow_failed:run:incident-responder:
- severity: warning
- status: analyzing
- occurrence_count: 1

### Workflow Details
- Workflow: mctl-agents-run
- Job: incident-responder
- Execution Time: 150.095632 seconds
- Workflow URL: https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1785053700

### Log Status
No recent log lines available in Loki for this service at incident time.

## Acceptance Criteria
- WHEN the root cause is identified and fixed THEN the incident-responder job completes successfully without workflow failure.
- WHEN changes are applied THEN the mctl-agents-run workflow no longer exits with failure status for the incident-responder job.
