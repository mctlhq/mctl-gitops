# Requirements: incident-17840781

## Incident
- ID: argo-mctl-agents-incidents-1784078100-1784078299
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (argo-workflows)
- Created: 2026-07-15T01:18:19.120783Z
- Summary: mctl-agents-run incident-responder Failed after 193.121637s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784078100

## Evidence
### Labels
- source: argo-workflows
- type: workflow_failed
- severity: warning
- tenant: admins
- service: mctl-agents

### Log Snippet
```
No Loki logs available for admins/mctl-agents (count: 0, queried 24h window).
Primary diagnostic source: Argo Workflow UI at
https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784078100
```

## Acceptance Criteria
- WHEN the fix is applied THEN the mctl-agents-run incident-responder workflow completes without failure.
- WHEN the cron fires at :15 and :45 past each hour THEN the workflow reaches a terminal status of Succeeded, not Failed.
