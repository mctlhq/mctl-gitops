# Requirements: incident-2e838012

## Incident
- ID: ed74f422-7aaa-4a56-bc2e-d7542e838012
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowFastBurn
- Created: 2026-09-07T06:22:43.745594Z

### Summary
```
mctl-telegram: session borrow fast burn (14.4x, 1h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
tenant: labs
service: (not set on incident record; inferred as mctl-telegram from alert name and summary)
severity: warning
confidence: LOW
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramSessionBorrowFastBurn). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
```
{"time":"2026-09-07T07:10:03.938394433Z","level":"INFO","msg":"metrics pushed to pushgateway","url":"http://prometheus-pushgateway.monitoring.svc.cluster.local:9091"}
{"time":"2026-09-07T07:04:07.360215115Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":1,"status":"ok","peer":"chat:<id>"}
{"time":"2026-09-07T07:01:19.407236554Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"chat:<id>"}
{"time":"2026-09-07T07:01:19.253790294Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"user:<id>"}
{"time":"2026-09-07T07:01:18.694304585Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"user:<id>"}
{"time":"2026-09-07T07:01:18.153999491Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"chat:<id>"}
{"time":"2026-09-07T07:01:17.645687413Z","level":"WARN","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"error","peer":"channel:<id>","err":"peer \"channel:[redacted]\" could not be accessed (CHANNEL_INVALID): it is not in your dialog list; call list_dialogs and use an id exactly as returned there"}
{"time":"2026-09-07T07:01:17.47175876Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"user:<id>"}
{"time":"2026-09-07T07:01:17.073938351Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"chat:<id>"}
{"time":"2026-09-07T07:01:16.896860686Z","level":"WARN","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"error","peer":"user:<id>","err":"peer \"user:[redacted]\" could not be accessed (PEER_ID_INVALID): it is not in your dialog list; call list_dialogs and use an id exactly as returned there"}
{"time":"2026-09-07T07:01:16.601627275Z","level":"WARN","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"error","peer":"user:<id>","err":"peer \"user:[redacted]\" could not be accessed (PEER_ID_INVALID): it is not in your dialog list; call list_dialogs and use an id exactly as returned there"}
{"time":"2026-09-07T07:01:15.887703835Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"user:<id>"}
{"time":"2026-09-07T07:00:46.476678782Z","level":"INFO","msg":"mcp tool call","tool":"list_dialogs","user_id":9980,"status":"ok"}
{"time":"2026-09-07T06:56:37.600588982Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":1,"status":"ok","peer":"chat:<id>"}
{"time":"2026-09-07T06:56:34.303015701Z","level":"INFO","msg":"mcp tool call","tool":"list_dialogs","user_id":1,"status":"ok"}
{"time":"2026-09-07T06:45:30.00483844Z","level":"INFO","msg":"mcp tool call","tool":"send_message:sent","user_id":1,"status":"ok","peer":"user:<id>"}
{"time":"2026-09-07T06:42:54.265239367Z","level":"INFO","msg":"idle telegram client, closing","user_id":9980,"idle":651278792772}
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
