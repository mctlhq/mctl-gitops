# Requirements: incident-0c5e067d

## Incident
- ID: 6b074aa1-d4e3-4535-94fd-5e8e0c5e067d
- Tenant: labs
- Service: mctl-telegram (service field empty on the incident; taken from the summary)
- Alert: MctlTelegramToolAvailabilitySlowBurn (type=generic)
- Created: 2026-10-23T00:17:43.849222Z

### Summary
```
mctl-telegram: MCP tool availability slow burn (6x, 6h)
```

## Evidence
### Labels
```
(no labels were returned by the incident API)
```

### Log Snippet
```
{"level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.084433644,"version":"0.88.3"}  (canary pod, 2026-10-23T01:10:03Z)
{"level":"INFO","msg":"mcp tool call","tool":"list_dialogs","user_id":245,"status":"ok"}  (labs-mctl-telegram base-service)
{"level":"INFO","msg":"mcp tool call","tool":"get_unread_messages","user_id":245,"status":"ok"}  (labs-mctl-telegram base-service)
{"level":"WARN","msg":"human input poll actor failed","user_id":1,"outcome":"api_503"}  (labs-mctl-telegram-preview base-service, repeats roughly every 30-60s from 00:52Z to 01:09Z)
{"level":"INFO","msg":"bridge: daemon disconnected","user_id":6462}  (01:05:27Z)
{"level":"INFO","msg":"bridge: daemon connected","user_id":6462}  (01:05:30Z)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
