# Requirements: incident-17840745

## Incident
- ID: argo-mctl-agents-incidents-1784074500-1784074702
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (argo-workflows)
- Created: 2026-07-15T00:18:22.537752Z
- Summary: mctl-agents-run incident-responder Failed after 196.418420s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784074500

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
https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784074500
```

## Acceptance Criteria
- WHEN the fix is applied THEN the mctl-agents-run incident-responder workflow completes without failure.
- WHEN the cron fires at :15 and :45 past each hour THEN the workflow reaches a terminal status of Succeeded, not Failed.
