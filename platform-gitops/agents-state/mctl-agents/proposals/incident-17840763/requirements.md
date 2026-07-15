# Requirements: incident-17840763

## Incident
- ID: argo-mctl-agents-incidents-1784076300-1784076479
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (argo-workflows)
- Created: 2026-07-15T00:47:59.568303Z
- Summary: mctl-agents-run incident-responder Failed after 174.541617s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784076300

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
https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784076300
```

## Acceptance Criteria
- WHEN the fix is applied THEN the mctl-agents-run incident-responder workflow completes without failure.
- WHEN the cron fires at :15 and :45 past each hour THEN the workflow reaches a terminal status of Succeeded, not Failed.
