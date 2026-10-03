# Requirements: incident-e22f370d

## Incident
- ID: b87ca113-2bf5-4793-8b44-d343e22f370d
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-14T06:03:43.752225Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
type: generic
source: alertmanager
severity: warning
tenant: labs
alert: MctlTelegramSessionBorrowSlowBurn
occurrence_count: 1
```

### Log Snippet
```
{"time":"2026-09-14T07:11:45.918392178Z","level":"INFO","msg":"idle telegram client, closing","user_id":9980,"idle":620147626715}
{"time":"2026-09-14T07:10:03.32580927Z","level":"INFO","msg":"metrics pushed to pushgateway","url":"http://prometheus-pushgateway.monitoring.svc.cluster.local:9091"}
{"time":"2026-09-14T07:10:03.314939658Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.195038608,"tg_user_id":"924671154","version":"0.67.0"}
{"time":"2026-09-14T07:10:03.314900253Z","level":"INFO","msg":"probe ok","step":"get_unread_messages"}
{"time":"2026-09-14T07:10:03.2995618Z","level":"INFO","msg":"mcp tool call","tool":"get_unread_messages","user_id":245,"status":"ok","edge_route":"direct","edge_request_id":"a3ad91d5a8e819c0-AMS"}
{"time":"2026-09-14T07:10:03.140723365Z","level":"INFO","msg":"probe start","step":"get_unread_messages","tg_user_id":"924671154"}
{"time":"2026-09-14T07:10:03.140679113Z","level":"INFO","msg":"probe ok","step":"list_dialogs"}
{"time":"2026-09-14T07:10:03.124004403Z","level":"INFO","msg":"mcp tool call","tool":"list_dialogs","user_id":245,"status":"ok","edge_route":"direct","edge_request_id":"a3ad91d52f3219c0-AMS"}
{"time":"2026-09-14T07:10:03.056148665Z","level":"INFO","msg":"probe start","step":"list_dialogs","tg_user_id":"924671154"}
{"time":"2026-09-14T07:10:03.056122936Z","level":"INFO","msg":"probe ok","step":"mcp_init"}
{"time":"2026-09-14T07:10:03.017122143Z","level":"INFO","msg":"probe start","step":"mcp_init","tg_user_id":"924671154"}
{"time":"2026-09-14T07:10:03.01708014Z","level":"INFO","msg":"probe ok","step":"oauth_metadata"}
{"time":"2026-09-14T07:10:02.120566097Z","level":"INFO","msg":"probe start","step":"oauth_metadata","tg_user_id":"924671154"}
{"time":"2026-09-14T07:10:02.120183875Z","level":"INFO","msg":"token lifetime","expires_at":"2026-10-13T20:30:02Z"}
{"time":"2026-09-14T07:04:51.355882186Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":1,"status":"ok","peer":"user:<id>","edge_route":"portal","edge_request_id":"a3ad8a366adc4d20-IAD","mcp_method":"tools/call","mcp_name":"get_messages","protocol_version":"2026-07-28"}
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
