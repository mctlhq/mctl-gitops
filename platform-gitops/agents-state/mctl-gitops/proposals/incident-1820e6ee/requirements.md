# Requirements: incident-1820e6ee

## Incident
- ID: argo-mctl-agents-daily-1784937600-1784937803
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (Argo Workflows)
- Created: 2026-07-25T00:03:23.977674Z
- Summary: mctl-agents-run full Failed after 198.480406s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-daily-1784937600

## Evidence
### Labels
- source: argo-workflows
- type: workflow_failed
- severity: warning
- status: analyzing
- tenant: admins
- service: mctl-agents
- fingerprint: workflow_failed:run:full:
- occurrence_count: 1

### Log Snippet
```
No log lines available from Loki (mctl-agents service returned 0 lines for
both a 6h and 24h window at triage time).
Argo workflow audit record not found for workflow name
"mctl-agents-daily-1784937600" (mctl_get_workflow_status: "workflow record
not found in audit log"). The argo-workflows source event does not persist
a separately queryable audit entry for cron-triggered runs.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
