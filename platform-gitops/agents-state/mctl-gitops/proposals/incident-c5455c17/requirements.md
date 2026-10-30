# Requirements: incident-c5455c17

## Incident
- ID: d2c4fad7-c7c3-4384-b8c5-583ac5455c17
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowFastBurn (type=generic)
- Created: 2026-10-29T08:34:43.944136Z

### Summary
```
mctl-telegram: session borrow fast burn (14.4x, 1h)
```

## Evidence
### Labels
```
severity: critical
source: alertmanager
tenant: labs
```

### Log Snippet
```
canary: probe ok step=oauth_metadata
canary: probe ok step=mcp_init
canary: probe failed step=list_dialogs err="MCP tool returned isError=true"
base-service: WARN mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
canary: probe failed step=get_unread_messages err="MCP tool returned isError=true"
base-service: WARN mcp tool call tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
canary: canary run complete ok=false tg_user_id=924671154 version=0.104.1
base-service: INFO mcp tool call tool=search_messages user_id=154537 status=ok (many, real user)
base-service: INFO mcp tool call tool=list_dialogs user_id=154537 status=ok
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
