# Requirements: incident-agents-incidents-1784513700

## Incident
- ID: argo-mctl-agents-incidents-1784513700-1784513827
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (Argo Workflows)
- Created: 2026-07-20T02:17:07.949263Z
- Summary: mctl-agents-run incident-responder Failed after 122.201957s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784513700

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
No Loki log lines returned for service=mctl-agents team=admins (since=6h,
count=0) — this class of short-lived CronWorkflow job pod does not retain
Loki-queryable logs after completion.
mctl_get_workflow_status for this workflow name returned "workflow record
not found in audit log" — the Argo Workflow audit record has already been
pruned (mctl_list_recent_agent_runs only retains the ~10 most recent
submissions across all mctl-agents pipelines).
Runtime (122.201957s, ~2-3 minutes) matches the fast-fail signature
(~100-210s) already documented in
mctl-gitops/proposals/incident-mctl-agents-oauth-quota-exhaustion
(status: implemented) as consistent with an OAuth token auth failure on
both the primary and fallback credential, rather than a step timeout
(~300s+, seen separately in incident-agents-run-f868212c) or a full
work cycle (which normally takes much longer, running multiple
service-agents plus a mentor pass).
This incident is one of a consecutive run of same-signature failures on
every 15/45-minute incident-responder tick going back at least to
2026-07-19T19:28Z (9+ hours at the time of triage), well past the 6h
staleness threshold set by the already-implemented
MctlAgentsPipelineStale alert (mctl-gitops PR #595).
```

## Acceptance Criteria
- WHEN the underlying cause of the incident-responder CronWorkflow failure
  is addressed THEN mctl-agents-incidents runs complete without error.
- WHEN the fix is applied THEN this incident class stops recurring for the
  incident-responder pipeline specifically.
