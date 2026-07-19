# Requirements: incident-agents-incidents-1784484900

## Incident
- ID: argo-mctl-agents-incidents-1784484900-1784485053
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (Argo Workflows)
- Created: 2026-07-19T18:17:33.606887Z
- Summary: mctl-agents-run incident-responder Failed after 147.369683s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784484900

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
Workflow audit record for mctl-agents-incidents-1784484900 not found
(mctl_list_recent_agent_runs only retains the most recent ~10 submissions).
This is the third occurrence of an incident-responder cron run failing within
the last ~4 hours (see also incidents at 15:17:13Z and 14:48:19Z the same day),
and part of a larger recurring pattern of mctl-agents workflow_failed incidents
already tracked under proposals/mctl-gitops/incident-argo-mct (in-progress).
```

## Acceptance Criteria
- WHEN the underlying cause of the incident-responder cron workflow failure is
  addressed THEN mctl-agents-incidents runs complete without error.
- WHEN the fix is applied THEN this incident class stops recurring for the
  incident-responder workflow specifically.
