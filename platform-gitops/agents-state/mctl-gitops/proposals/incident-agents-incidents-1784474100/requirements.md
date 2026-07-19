# Requirements: incident-agents-incidents-1784474100

## Incident
- ID: argo-mctl-agents-incidents-1784474100-1784474233
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (Argo Workflows)
- Created: 2026-07-19T15:17:13.359324Z
- Summary: mctl-agents-run incident-responder Failed after 128.299300s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784474100

## Evidence
### Labels
- source: argo-workflows
- type: workflow_failed
- severity: warning
- status: analyzing
- tenant: admins
- service: mctl-agents

### Log Snippet
```
No log lines available from Loki (mctl-agents service returned 0 lines for the
last 24h — this class of job pod does not appear to retain Loki-queryable logs
after completion).
Workflow audit record for mctl-agents-incidents-1784474100 not found
(mctl_list_recent_agent_runs only retains the most recent ~10 submissions).
Second occurrence that day of an incident-responder cron run failing after a
short runtime (~2 minutes), consistent with an early-stage crash rather than a
timeout. Part of a larger recurring pattern already tracked under
proposals/mctl-gitops/incident-argo-mct (in-progress).
```

## Acceptance Criteria
- WHEN the underlying cause of the incident-responder cron workflow failure is
  addressed THEN mctl-agents-incidents runs complete without error.
- WHEN the fix is applied THEN this incident class stops recurring for the
  incident-responder workflow specifically.
