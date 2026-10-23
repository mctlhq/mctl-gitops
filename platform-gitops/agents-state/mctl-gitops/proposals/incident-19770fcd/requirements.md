# Requirements: incident-19770fcd

## Incident
- ID: 9c1f8049-eb24-4066-b495-a46619770fcd
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowFastBurn
- Created: 2026-10-23T09:46:43.847626Z

### Summary
```
mctl-telegram: session borrow fast burn (14.4x, 1h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
severity: critical
tenant: labs
analysis: Escalated, no skill matched
```

### Log Snippet
```
canary ERROR probe failed step=list_dialogs err="MCP tool returned isError=true"
base-service WARN mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
canary ERROR probe failed step=get_unread_messages err="MCP tool returned isError=true"
base-service WARN mcp tool call tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
canary INFO canary run complete ok=false tg_user_id=924671154 version=0.88.3
(repeats every ~10 minutes at 11:00 and 11:10; mcp_init and oauth_metadata steps pass)
base-service INFO mcp tool call tool=list_dialogs user_id=9980 status=ok
base-service INFO mcp tool call tool=get_messages user_id=9980 status=ok
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
