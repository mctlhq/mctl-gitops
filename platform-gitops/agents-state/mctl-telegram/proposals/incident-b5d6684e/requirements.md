# Requirements: incident-b5d6684e

## Incident
- ID: a0693eab-1a7f-4fdd-a900-7578b5d6684e
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-08T14:03:43.809759Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
severity: warning
tenant: labs
occurrence_count: 1
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramSessionBorrowSlowBurn). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
Loki was queried for labs/mctl-telegram over the 6h alert window; the tool
returned only the most recent ~50 lines (effectively the last ~10 minutes of
high-volume base-service traffic), not a spread across the full 6h burn
window. No line in the returned sample contains an error level entry or a
message naming "borrow" or "pool" — every mcp/oauth log line shown is
status=ok, and the canary's own probe runs (identity 924671154) all report
ok:true. This is evidence of absence in the sampled window only, not proof
the underlying Pool.Borrow() error rate is currently zero — the alert's own
6h ratio says otherwise.
```
{"time":"2026-09-08T15:11:30Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-08T15:11:25Z","level":"INFO","msg":"mcp tool call","tool":"get_media","user_id":9980,"status":"ok"}
{"time":"2026-09-08T15:11:21Z","level":"INFO","msg":"mcp tool call","tool":"prepare_get_media","user_id":9980,"status":"ok"}
{"time":"2026-09-08T15:10:03Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.168,"tg_user_id":"924671154","version":"0.62.2"}
{"time":"2026-09-08T15:10:03Z","level":"INFO","msg":"probe ok","step":"get_unread_messages"}
{"time":"2026-09-08T15:03:24Z","level":"INFO","msg":"oauth: client_registration request","client_name":"cmg0c9xxt020wec596hjg563i"}
{"time":"2026-09-08T15:01:42Z","level":"INFO","msg":"mcp tool call","tool":"get_unread_messages","user_id":9980,"status":"ok"}
{"time":"2026-09-08T15:00:45Z","level":"INFO","msg":"mcp tool call","tool":"list_dialogs","user_id":9980,"status":"ok"}
{"time":"2026-09-08T15:00:03Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.599,"tg_user_id":"924671154","version":"0.62.2"}
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
