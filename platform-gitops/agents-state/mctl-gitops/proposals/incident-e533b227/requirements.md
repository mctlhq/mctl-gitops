# Requirements: incident-e533b227

## Incident
- ID: 2cf2a119-1782-464c-a46e-70bce533b227
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramToolAvailabilityFastBurn (type=generic)
- Created: 2026-10-29T08:27:43.840578Z

### Summary
```
mctl-telegram: MCP tool availability fast burn (14.4x, 1h)
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
canary: probe failed step=list_dialogs err="MCP tool returned isError=true"
base-service: WARN mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
canary: probe failed step=get_unread_messages err="MCP tool returned isError=true"
base-service: WARN mcp tool call tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
canary: canary run complete ok=false tg_user_id=924671154 version=0.104.1
base-service: WARN search_messages user_id=154537 status=error slo_status=caller_error err="CHANNEL_INVALID" (excluded from SLO as caller error)
base-service: INFO search_messages / list_dialogs user_id=154537 status=ok (real user, healthy)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
