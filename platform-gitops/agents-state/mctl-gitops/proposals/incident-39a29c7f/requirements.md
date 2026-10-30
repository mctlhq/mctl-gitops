# Requirements: incident-39a29c7f

## Incident
- ID: e1812060-50e1-4058-b121-dfce39a29c7f
- Tenant: labs
- Service: labs-mctl-telegram
- Alert: ArgoCDApplicationDegraded (type argocd_app_degraded)
- Created: 2026-10-28T21:32:20.366794Z

### Summary
```
ArgoCD application labs-mctl-telegram has been Degraded for 30m
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
analysis: no skill matched this ticket
```

### Log Snippet
```
canary: probe ok step=oauth_metadata
canary: probe ok step=mcp_init
base-service: WARN mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
base-service: WARN mcp tool call tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
canary: ERROR probe failed step=list_dialogs err="MCP tool returned isError=true"
canary: INFO canary run complete ok=false version=0.104.1
pod labs-mctl-telegram-base-service-fc5d756f-rhx65: Running, ready=true, restarts=0
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
