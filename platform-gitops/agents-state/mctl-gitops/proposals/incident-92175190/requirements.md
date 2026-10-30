# Requirements: incident-92175190

## Incident
- ID: ab399378-bd0b-4f5b-9ff4-c92052175190
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramToolAvailabilityFastBurn
- Created: 2026-10-23T07:13:44.042854Z

### Summary
```
mctl-telegram: MCP tool availability fast burn (14.4x, 1h)
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
probe failed step=get_unread_messages err="MCP tool returned isError=true"
canary run complete ok=false tg_user_id=924671154 version=0.88.3
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
