# Requirements: incident-agents-run-f868212c

## Incident
- ID: argo-mctl-agents-run-f868212c-1784381073
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (Argo Workflows)
- Created: 2026-07-18T13:24:33.66319Z
- Summary: mctl-agents-run incident-responder Failed after 324.498225s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-run-f868212c

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
Workflow audit record for mctl-agents-run-f868212c not found
(mctl_list_recent_agent_runs only retains the most recent ~10 submissions).
Runtime (~5.4 minutes) is longer than the same-day incident-responder failures
seen on 2026-07-19 (~2-3 minutes each), suggesting this occurrence may be a
different failure mode (possibly lock contention — see design.md). Part of a
larger recurring pattern already tracked under
proposals/mctl-gitops/incident-argo-mct (in-progress).
```

## Acceptance Criteria
- WHEN the underlying cause of the incident-responder cron workflow failure is
  addressed THEN mctl-agents-run/incidents runs complete without error.
- WHEN the fix is applied THEN this incident class stops recurring for the
  incident-responder workflow specifically.
