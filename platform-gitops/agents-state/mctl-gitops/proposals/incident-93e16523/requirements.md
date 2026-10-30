# Requirements: incident-93e16523

## Incident
- ID: 96e29c7a-a477-45f5-b61c-1e3e93e16523
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramToolAvailabilitySlowBurn
- Created: 2026-10-28T21:21:43.965217Z

### Summary
```
mctl-telegram: MCP tool availability slow burn (6x, 6h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
severity: warning
status: escalated
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramToolAvailabilitySlowBurn).
```

### Log Snippet
```
22:10:17Z canary INFO probe ok step=mcp_init
22:10:17Z base-service WARN mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
22:10:17Z canary ERROR probe failed step=list_dialogs err="MCP tool returned isError=true"
22:10:17Z base-service WARN mcp tool call tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
22:10:17Z canary ERROR probe failed step=get_unread_messages err="MCP tool returned isError=true"
22:10:17Z canary INFO canary run complete ok=false version=0.104.1
22:10:04Z canary INFO canary run complete ok=false (same pattern on the parallel canary pod)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
