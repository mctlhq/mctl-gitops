# Requirements: incident-b11a9798

## Incident
- ID: argo-mctl-agents-incidents-1784934900-1784935041
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (Argo Workflows)
- Created: 2026-07-24T23:17:21.254237Z
- Summary: mctl-agents-run incident-responder Failed after 135.070697s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784934900

## Evidence
### Labels
- source: argo-workflows
- type: workflow_failed
- severity: warning
- status: analyzing
- tenant: admins
- service: mctl-agents
- fingerprint: workflow_failed:run:incident-responder:
- occurrence_count: 7
- last_seen_at: 2026-07-25T02:18:31.336523Z

### Log Snippet
```
No log lines available from Loki (mctl-agents service returned 0 lines for
both a 6h and 24h window at triage time).
Argo workflow audit record not found for workflow name
"mctl-agents-incidents-1784934900" (mctl_get_workflow_status: "workflow
record not found in audit log"). mctl_list_recent_agent_runs at triage time
(2026-07-25T02:46Z) shows mctl-agents-implement ticks succeeding
repeatedly (02:15-02:40) and a new mctl-agents-incidents tick just
submitted at 02:45:00 with no completion recorded yet for that specific
pipeline in the visible window.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
