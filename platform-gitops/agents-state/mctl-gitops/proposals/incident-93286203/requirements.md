# Requirements: incident-93286203

## Incident
- ID: argo-mctl-agents-shepherd-1793285640-1793286203
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd)
- Created: 2026-10-29T15:03:24.238199Z

### Summary
```
shepherd shepherd (all open PRs) Failed after 545.469833s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-1793285640 | post-deploy-verify flagged: argocd/labs-mctl-telegram
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
fingerprint: workflow_failed:shepherd::
workflow_name: mctl-agents-shepherd-1793285640
```

### Log Snippet
```
post-deploy-verify: merged=yes shepherd=succeeded - verifying.
post-deploy-verify: Newly Degraded apps detected: argocd/labs-mctl-telegram - waiting 120s
post-deploy-verify: Still Degraded after 120s grace: argocd/labs-mctl-telegram
labs/mctl-telegram canary: probe ok step=mcp_init
labs/mctl-telegram canary: probe failed step=list_dialogs err="MCP tool returned isError=true"
labs/mctl-telegram base-service: mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
labs/mctl-telegram canary: probe failed step=get_unread_messages
labs/mctl-telegram canary: canary run complete ok=false version=0.104.1
labs/mctl-telegram events: Job labs-mctl-telegram-canary-* BackoffLimitExceeded (every 10 minutes since at least 15:20Z)
ArgoCD labs-mctl-telegram: health=Degraded sync=Synced, running pod Ready, 0 restarts
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
