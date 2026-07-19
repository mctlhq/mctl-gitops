# Requirements: incident-agents-incidents-1784472300

## Incident
- ID: argo-mctl-agents-incidents-1784472300-1784472499
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (Argo Workflows)
- Created: 2026-07-19T14:48:19.228373Z
- Summary: mctl-agents-run incident-responder Failed after 193.887592s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784472300

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
Workflow audit record for mctl-agents-incidents-1784472300 not found
(mctl_list_recent_agent_runs only retains the most recent ~10 submissions).
First of three same-day incident-responder cron failures (this one, then
15:17:13Z, then 18:17:33Z), all with short (~2-3 minute) runtimes. Part of a
larger recurring pattern already tracked under
proposals/mctl-gitops/incident-argo-mct (in-progress).
```

## Acceptance Criteria
- WHEN the underlying cause of the incident-responder cron workflow failure is
  addressed THEN mctl-agents-incidents runs complete without error.
- WHEN the fix is applied THEN this incident class stops recurring for the
  incident-responder workflow specifically.
