# Requirements: incident-0ac79819

## Incident
- ID: f07a3322-3694-4dbb-bff4-226f0ac79819
- Tenant: labs
- Service: mctl-telegram
- Alert: more than 10 percent of tool calls failing (type generic)
- Created: 2026-10-28T21:26:39.906509Z

### Summary
```
mctl-telegram: more than 10% of tool calls are failing
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
analysis: argocd_sync_failed skill produced LOW-confidence diagnosis, fixable=false
```

### Log Snippet
```
base-service: WARN mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
base-service: WARN mcp tool call tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
pod labs-mctl-telegram-base-service-fc5d756f-rhx65: Running, ready=true, restarts=0, image ghcr.io/mctlhq/mctl-telegram:0.104.1
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
