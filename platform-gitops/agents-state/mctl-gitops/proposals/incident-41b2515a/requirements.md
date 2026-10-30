# Requirements: incident-41b2515a

## Incident
- ID: 5ddf5bc3-74f2-40ca-b036-044541b2515a
- Tenant: monitoring
- Service: prometheus-pushgateway
- Alert: MctlTelegramCanaryFailing (type generic)
- Created: 2026-10-28T21:31:22.614375Z

### Summary
```
mctl-telegram canary probe has been failing for ~25 minutes
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
canary: INFO probe ok step=oauth_metadata
canary: INFO probe ok step=mcp_init
canary: ERROR probe failed step=list_dialogs err="MCP tool returned isError=true" flood_wait=false
canary: ERROR probe failed step=get_unread_messages err="MCP tool returned isError=true" flood_wait=false
canary: INFO canary run complete ok=false tg_user_id=924671154 version=0.104.1
base-service: WARN mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
