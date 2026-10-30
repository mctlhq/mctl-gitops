# Requirements: incident-c39c5ca7

## Incident
- ID: 533000a1-84f3-4960-a8db-cf24c39c5ca7
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowFastBurn
- Created: 2026-10-23T14:42:43.939955Z

### Summary
```
mctl-telegram: session borrow fast burn (14.4x, 1h)
```

## Evidence
### Labels
```
type: generic
severity: critical
source: alertmanager
tenant: labs
analysis: Escalated: no skill matched this ticket
```

### Log Snippet
```
WARN mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
ERROR probe failed step=list_dialogs err="MCP tool returned isError=true"
WARN mcp tool call tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
ERROR probe failed step=get_unread_messages err="MCP tool returned isError=true"
INFO canary run complete ok=false version=0.89.0 tg_user_id=924671154
INFO bridge: daemon connected user_id=6462 device_id=dev_d506989160c0f9c5b1cce53d7f60f6d5
INFO bridge: daemon disconnected user_id=6462
INFO bridge: daemon connected user_id=6462 device_id=dev_05d9b8cdd6eda7b60fa6604de92cd1fe
INFO bridge: daemon disconnected user_id=6462
(the connect/disconnect pair alternates between the two devices roughly every 1-3 seconds)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN the canary runs THEN list_dialogs and get_unread_messages succeed for the canary user.
