# Requirements: incident-76cdf864

## Incident
- ID: 2463ac41bf854a77ac7d34e476cdf864
- Tenant: labs
- Service: labs-mctl-telegram
- Alert: ArgoCDApplicationDegraded
- Created: 2026-08-23T02:12:19Z

### Summary
ArgoCD application labs-mctl-telegram has been Degraded for 30m

## Evidence
### Labels
```
source: alertmanager
type: argocd_app_degraded
severity: warning
```

### Log Snippet
The canary probe for labs-mctl-telegram shows consistent failures across multiple runs:

Error pattern in mcp tool calls:
```
WARN mcp tool call tool=list_dialogs user_id=1 status=error err='no active session'
WARN mcp tool call tool=get_unread_messages user_id=1 status=error err='no active session'
ERROR probe failed step=list_dialogs err='MCP tool returned isError=true'
ERROR probe failed step=get_unread_messages err='MCP tool returned isError=true'
INFO canary run complete ok=false
```

The canary successfully completes:
- oauth_metadata check
- mcp_init setup

But fails when attempting user-scoped operations (list_dialogs, get_unread_messages) with 'no active session'.

## Acceptance Criteria
- WHEN the labs-mctl-telegram pods are restarted to clear session state THEN the canary probes resume passing THEN ArgoCD sync restores the app to healthy status.
