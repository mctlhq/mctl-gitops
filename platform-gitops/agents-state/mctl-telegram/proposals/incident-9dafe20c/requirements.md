# Requirements: incident-9dafe20c

## Incident
- ID: f68375fe-513e-44c4-98d5-858b9dafe20c
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramToolAvailabilitySlowBurn
- Created: 2026-09-07T10:02:43.866212Z

### Summary
```
mctl-telegram: MCP tool availability slow burn (6x, 6h)
```

## Evidence
### Labels
```
(none provided by mctl_get_incident for this incident)
```

### Log Snippet
```
{"time":"2026-09-07T11:01:21.770495066Z","level":"WARN","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"error","peer":"channel:<id>","err":"peer \"channel:[redacted]\" could not be accessed (CHANNEL_INVALID): it is not in your dialog list; call list_dialogs and use an id exactly as returned there"}
{"time":"2026-09-07T11:01:19.693663937Z","level":"WARN","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"error","peer":"user:<id>","err":"peer \"user:[redacted]\" could not be accessed (PEER_ID_INVALID): it is not in your dialog list; call list_dialogs and use an id exactly as returned there"}
{"time":"2026-09-07T11:01:19.021426509Z","level":"WARN","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"error","peer":"user:<id>","err":"peer \"user:[redacted]\" could not be accessed (PEER_ID_INVALID): it is not in your dialog list; call list_dialogs and use an id exactly as returned there"}
{"time":"2026-09-07T11:10:03.493525598Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.240773241,"tg_user_id":"924671154","version":"0.62.0"}
{"time":"2026-09-07T11:10:03.482424263Z","level":"INFO","msg":"mcp tool call","tool":"get_unread_messages","user_id":245,"status":"ok"}
{"time":"2026-09-07T11:00:03.231702893Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.179346451,"tg_user_id":"924671154","version":"0.62.0"}
{"time":"2026-09-07T11:00:39.258672655Z","level":"INFO","msg":"mcp tool call","tool":"list_dialogs","user_id":9980,"status":"ok"}
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service due to client-supplied invalid peer/channel references, while still firing for genuine service-side tool failures.
