# Requirements: incident-7fb35eac

## Incident
- ID: 8cd239ab-a2cb-4b9d-8218-ab2a7fb35eac
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowFastBurn
- Created: 2026-10-23T07:13:44.063692Z

### Summary
```
mctl-telegram: session borrow fast burn (14.4x, 1h)
```

## Evidence
### Labels
```
type: generic
severity: critical
status: escalated
```

### Log Snippet
```
mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
mcp tool call tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
probe failed step=list_dialogs err="MCP tool returned isError=true" flood_wait=false
canary run complete ok=false tg_user_id=924671154 version=0.88.3
mcp tool call tool=get_messages user_id=9980 status=ok
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
