# Requirements: incident-87497762

## Incident
- ID: argo-mctl-agents-shepherd-1787497200-1787497762
- Tenant: admins
- Service: mctl-agents (shepherd)
- Alert: workflow_failed
- Created: 2026-08-23T15:09:22.942903Z

### Summary
```
shepherd workflow failed after post-deploy-verify detected labs-mctl-telegram service
became degraded. The service's canary probe repeatedly fails with MCP tool call errors
reporting "no active session" when attempting to call methods like list_dialogs and
get_unread_messages. Service remains synced in ArgoCD but marked Degraded.
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
fingerprint: workflow_failed:shepherd::
```

### Log Snippet
Post-deploy-verify logs from shepherd workflow:
```
Sleeping 300s for ArgoCD to reconcile post-merge…
Listing applications that became Degraded after 2026-08-23T15:00:00Z…
Newly Degraded apps detected: argocd/labs-mctl-telegram  — waiting 120s to confirm (rolling-update grace)…
Still Degraded after 120s grace: argocd/labs-mctl-telegram
```

Service logs from labs-mctl-telegram (multiple probes failing):
```
WARN mcp tool call tool=list_dialogs user_id=1 status=error err="no active session"
WARN mcp tool call tool=get_unread_messages user_id=1 status=error err="no active session"
ERROR probe failed step=list_dialogs err="MCP tool returned isError=true"
ERROR probe failed step=get_unread_messages err="MCP tool returned isError=true"
INFO canary run complete ok=false
```

Service health status:
```
argocd health: Degraded
syncStatus: Synced
imageTag: 0.50.1
```

## Acceptance Criteria
- WHEN the session management issue in labs-mctl-telegram is resolved THEN the canary probe will complete successfully (ok=true) THEN the service will become Healthy in ArgoCD THEN shepherd post-deploy-verify will pass and the workflow will complete successfully.
