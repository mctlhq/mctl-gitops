# Requirements: incident-92772276

## Incident
- ID: argo-mctl-agents-shepherd-9d95e0ef-1792772276
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd, workflow mctl-agents-shepherd-aec06691)
- Created: 2026-10-23T16:17:56Z

### Summary
```
shepherd shepherd issue-716-refactor-db-replace-logtoolcall-s-positi Failed after 524.922703s - https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-9d95e0ef | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
fingerprint: workflow_failed:shepherd:mctl-telegram:issue-716-refactor-db-replace-logtoolcall-s-positi
occurrence_count: 4
```

### Log Snippet
```
canary: probe ok step=mcp_init
canary: probe failed step=list_dialogs err="MCP tool returned isError=true"
base-service: WARN mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
canary: probe failed step=get_unread_messages err="MCP tool returned isError=true"
base-service: WARN mcp tool call tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
canary: canary run complete ok=false tg_user_id=924671154 version=0.89.0
(real users, e.g. user_id 9980 and 96357, show status=ok for get_messages/send_message in the same window)
```

## Acceptance Criteria
- WHEN the change is applied THEN the post-deploy-verify check for labs/mctl-telegram stops flagging the canary and the shepherd workflow no longer fails on it.
