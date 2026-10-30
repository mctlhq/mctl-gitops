# Requirements: incident-e743f047

## Incident
- ID: 421d7a34-5769-46d0-ad7b-b4c8e743f047
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramOAuthAvailabilitySlowBurn
- Created: 2026-10-23T07:05:43.965851Z

### Summary
```
mctl-telegram: OAuth token endpoint slow burn (6x, 6h)
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
probe ok step=oauth_metadata
token lifetime expires_at=2026-11-02T20:40:03Z
probe failed step=list_dialogs err="MCP tool returned isError=true"
mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
canary run complete ok=false version=0.88.3
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
