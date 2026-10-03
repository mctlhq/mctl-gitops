# Requirements: incident-210417c4

## Incident
- ID: 8c695622-bfed-4b1f-b586-0bd0210417c4
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowFastBurn
- Created: 2026-09-11T10:32:43.732057Z

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
service: (empty in incident record; alert concerns labs/mctl-telegram)
severity: warning
alertname: MctlTelegramSessionBorrowFastBurn
occurrence_count: 1
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramSessionBorrowFastBurn). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
Last ~15 log lines for labs/mctl-telegram at incident time (2026-09-11 ~11:00-11:11 UTC).
No session-borrow, pool, or Telegram-client error lines appear in this window;
all MCP tool calls and canary probe steps report status "ok".
```
{"time":"2026-09-11T11:10:59Z","level":"INFO","msg":"mcp tool call","tool":"list_dialogs","user_id":245,"status":"ok"}
{"time":"2026-09-11T11:10:57Z","level":"INFO","msg":"mcp tool call","tool":"list_dialogs","user_id":245,"status":"ok"}
{"time":"2026-09-11T11:10:55Z","level":"INFO","msg":"mcp tool call","tool":"list_dialogs","user_id":245,"status":"ok"}
{"time":"2026-09-11T11:10:03Z","level":"INFO","msg":"metrics pushed to pushgateway","url":"http://prometheus-pushgateway.monitoring.svc.cluster.local:9091"}
{"time":"2026-09-11T11:10:03Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.347919342,"tg_user_id":"924671154","version":"0.64.2"}
{"time":"2026-09-11T11:10:03Z","level":"INFO","msg":"probe ok","step":"get_unread_messages"}
{"time":"2026-09-11T11:10:03Z","level":"INFO","msg":"mcp tool call","tool":"get_unread_messages","user_id":245,"status":"ok"}
{"time":"2026-09-11T11:10:03Z","level":"INFO","msg":"probe start","step":"get_unread_messages","tg_user_id":"924671154"}
{"time":"2026-09-11T11:10:03Z","level":"INFO","msg":"probe ok","step":"list_dialogs"}
{"time":"2026-09-11T11:10:02Z","level":"INFO","msg":"mcp tool call","tool":"list_dialogs","user_id":245,"status":"ok"}
{"time":"2026-09-11T11:01:43Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"username:len=13"}
{"time":"2026-09-11T11:01:09Z","level":"INFO","msg":"mcp tool call","tool":"list_dialogs","user_id":9980,"status":"ok"}
{"time":"2026-09-11T11:00:03Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.388182931,"tg_user_id":"924671154","version":"0.64.2"}
{"time":"2026-09-11T10:41:58Z","level":"INFO","msg":"idle telegram client, closing","user_id":9980,"idle":608788556487}
```

## Acceptance Criteria
- WHEN the change is applied THEN future occurrences of MctlTelegramSessionBorrowFastBurn are
  triaged by an mctl-agent skill instead of always escalating for human review.
