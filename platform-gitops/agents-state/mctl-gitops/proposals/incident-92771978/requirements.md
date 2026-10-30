# Requirements: incident-92771978

## Incident
- ID: argo-mctl-agents-shepherd-2a4c585a-1792771978
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd, workflow mctl-agents-shepherd-2a4c585a)
- Created: 2026-10-23T16:12:58Z

### Summary
```
shepherd shepherd issue-556-spike-governance-compare-jev-and-clef-de Failed after 506.969944s - https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-2a4c585a | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
fingerprint: workflow_failed:shepherd:mctl-agents:issue-556-spike-governance-compare-jev-and-clef-de
occurrence_count: 1
```

### Log Snippet
```
canary: probe ok step=mcp_init
canary: probe failed step=list_dialogs err="MCP tool returned isError=true"
base-service: WARN mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
canary: probe failed step=get_unread_messages err="MCP tool returned isError=true"
canary: canary run complete ok=false tg_user_id=924671154 version=0.89.0
```

## Acceptance Criteria
- WHEN the change is applied THEN the post-deploy-verify check for labs/mctl-telegram stops flagging the canary and the shepherd workflow no longer fails on it.
