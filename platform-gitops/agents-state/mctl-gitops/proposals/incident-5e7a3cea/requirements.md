# Requirements: incident-5e7a3cea

## Incident
- ID: cf4c970a-6e26-49d3-8b01-1c1a5e7a3cea
- Tenant: labs
- Service: mctl-telegram (incident service field empty)
- Alert: MctlTelegramToolAvailabilityFastBurn (type generic)
- Created: 2026-10-28T21:21:44.038575Z

### Summary
```
mctl-telegram: MCP tool availability fast burn (14.4x, 1h)
```

## Evidence
### Labels
```
source: alertmanager
severity: critical
analysis: no skill matched this ticket
```

### Log Snippet
```
base-service: WARN mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
base-service: WARN mcp tool call tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
canary: ERROR probe failed step=list_dialogs err="MCP tool returned isError=true"
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
