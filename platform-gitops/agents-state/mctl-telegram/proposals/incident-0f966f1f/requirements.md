# Requirements: incident-0f966f1f

## Incident
- ID: d685163c-9ba9-4453-b968-38090f966f1f
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-24T09:02:43.739054Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
tenant: labs
service: (empty in incident record; inferred as mctl-telegram from alert name)
alert: MctlTelegramSessionBorrowSlowBurn
severity: warning
confidence: LOW
occurrence_count: 1
analysis (from mctl-agent): Escalated: no skill matched this ticket
  (type=generic, alert=MctlTelegramSessionBorrowSlowBurn). Evidence was
  collected, but the agent has no diagnostic rule for this signal, so nothing
  was analysed. Needs a human, or a new skill.
```

### Log Snippet
Fetched via mctl_get_service_logs(team=labs, service=mctl-telegram, since=6h,
lines=50). The tool has no offset/pagination and this service is high-volume,
so the 50 lines returned cover only roughly the trailing ~21 minutes of the 6h
alert window, not the full window.
```
{"time":"2026-09-24T10:11:32.928703328Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":1,"status":"ok"}
{"time":"2026-09-24T10:11:30.087833806Z","level":"INFO","msg":"mcp tool call","tool":"send_message:sent","user_id":1,"status":"ok"}
{"time":"2026-09-24T10:10:29.099693154Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":1,"status":"ok"}
{"time":"2026-09-24T10:10:03.464747074Z","level":"INFO","msg":"metrics pushed to pushgateway","url":"http://prometheus-pushgateway.monitoring.svc.cluster.local:9091"}
{"time":"2026-09-24T10:10:03.364567587Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.205738546,"tg_user_id":"924671154","version":"0.68.0"}
{"time":"2026-09-24T10:00:04.142708128Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.3784513569999999,"tg_user_id":"924671154","version":"0.68.0"}
{"time":"2026-09-24T09:55:19.966050978Z","level":"INFO","msg":"idle telegram client, closing","user_id":1,"idle":658038463385}
{"time":"2026-09-24T09:50:03.514792958Z","level":"INFO","msg":"metrics pushed to pushgateway","url":"http://prometheus-pushgateway.monitoring.svc.cluster.local:9091"}
```
No line at WARN/ERROR level, and no line containing "session", "borrow", or
"error" (case-insensitive), appears anywhere in the retrieved window. Every
sampled mcp tool call and canary probe reports status "ok" / ok:true. This is
the same "silent" evidence pattern already recorded in three earlier
escalations of this exact alert: incidents
08255c19-3574-4ce8-95ff-31d6776dd0cd (2026-09-07),
a0693eab-1a7f-4fdd-a900-7578b5d6684e (2026-09-08), and the related fast-burn
variant 277ec562-431c-4f02-b75a-5cba6670553a (2026-09-22) — the SLO alert
fires on `mctl_sessions_borrow_total{result="error"}`, but nothing in the
application logs currently signals a borrow failure.

## Acceptance Criteria
- WHEN a future `Pool.Borrow()` failure occurs (any
  `mctl_sessions_borrow_total{result="error"}` increment) THEN it produces a
  log line identifying the reason, so this alert is diagnosable from logs
  without needing raw metrics access.
- WHEN the change is applied THEN it does not alter `Pool.Borrow()` behavior,
  retry logic, or the SLO thresholds themselves.
