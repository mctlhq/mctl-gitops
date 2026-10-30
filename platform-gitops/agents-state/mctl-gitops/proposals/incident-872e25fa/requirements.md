# Requirements: incident-872e25fa

## Incident
- ID: 7badd9ef-a07e-46e7-8710-9810872e25fa
- Tenant: labs
- Service: mctl-telegram (service field empty on the incident; taken from the summary)
- Alert: MctlTelegramToolAvailabilityFastBurn
- Created: 2026-10-23T13:47:43.844408Z

### Summary
```
mctl-telegram: MCP tool availability fast burn (14.4x, 1h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
severity: critical
status: escalated
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramToolAvailabilityFastBurn).
```

### Log Snippet
```
15:10:16.526 WARN  mcp tool call tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
15:10:16.538 ERROR probe failed step=get_unread_messages err="MCP tool returned isError=true" (canary)
15:10:16.470 WARN  mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
15:10:16.483 ERROR probe failed step=list_dialogs err="MCP tool returned isError=true" (canary)
15:10:16.539 INFO  canary run complete ok=false tg_user_id=924671154 version=0.89.0
15:10:03.185 WARN  mcp tool call tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
15:10:03.131 WARN  mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
15:10:03.195 INFO  canary run complete ok=false tg_user_id=924671154 version=0.89.0
15:10:15.491 INFO  token lifetime expires_at=2026-11-02T20:40:03Z
Other users (user_id=9980 get_messages status=ok) succeed; bridge daemon connect/disconnect churn for user_id=6462 repeats every ~3s.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
