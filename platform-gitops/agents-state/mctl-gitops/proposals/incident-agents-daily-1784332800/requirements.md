# Requirements: incident-agents-daily-1784332800

## Incident
- ID: argo-mctl-agents-daily-1784332800-1784333311
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (Argo Workflows)
- Created: 2026-07-18T00:08:31.827176Z
- Summary: mctl-agents-run full Failed after 507.877947s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-daily-1784332800

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
Workflow audit record for mctl-agents-daily-1784332800 not found
(mctl_list_recent_agent_runs only retains the most recent ~10 submissions).
This is the "full" daily pipeline run (broader scope than a single
incident-responder or implement run) and had the longest runtime of this batch
(~8.5 minutes), consistent with either an aggregated timeout across several
sub-steps or lock contention while waiting for the shared mctl-gitops write
lock (see design.md). Part of a larger recurring pattern already tracked under
proposals/mctl-gitops/incident-argo-mct (in-progress).
```

## Acceptance Criteria
- WHEN the underlying cause of the daily "full" pipeline workflow failure is
  addressed THEN mctl-agents-daily runs complete without error.
- WHEN the fix is applied THEN this incident class stops recurring for the
  daily full pipeline run specifically.
