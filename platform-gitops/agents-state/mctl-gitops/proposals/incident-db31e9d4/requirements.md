# Requirements: incident-db31e9d4

## Incident
- ID: cf13e9a5-72c6-4adc-9f81-adf6db31e9d4
- Tenant: labs
- Service: mctl-telegram
- Alert: HighToolErrorRate
- Created: 2026-10-23T07:18:39.940419Z

### Summary
```
mctl-telegram: more than 10% of tool calls are failing
```

## Evidence
### Labels
```
type: generic
severity: warning
status: escalated
```

### Log Snippet
```
mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
mcp tool call tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
probe failed step=list_dialogs err="MCP tool returned isError=true" flood_wait=false
canary run complete ok=false tg_user_id=924671154 version=0.88.3
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
