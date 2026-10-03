# Requirements: incident-6670553a

## Incident
- ID: 277ec562-431c-4f02-b75a-5cba6670553a
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowFastBurn
- Created: 2026-09-22T07:20:43.753013Z

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
service: (empty in incident record; alert is scoped to mctl-telegram per summary/alert name)
severity: warning
alert: MctlTelegramSessionBorrowFastBurn
occurrence_count: 1
analysis (from mctl-agent): Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramSessionBorrowFastBurn). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
Loki logs for team=labs, service=mctl-telegram, most recent ~80 lines covering
approximately 2026-09-22T07:30:00Z through 2026-09-22T08:11:32Z (the log tool
has no offset/pagination and larger line counts for this service exceed the
response size limit, so the earlier part of the alert's 1h burn window,
approximately 06:20-07:30, could not be retrieved). No log line mentioning
"borrow", and no ERROR-level line of any kind, appears anywhere in the
retrieved range. Representative lines:
```
2026-09-22T08:11:32Z INFO idle telegram client, closing user_id=9980 idle_ns=612607227452
2026-09-22T08:10:03Z INFO canary run complete ok=true duration_seconds=1.645 tg_user_id=924671154 version=0.67.0
2026-09-22T08:10:03Z INFO probe ok step=get_unread_messages
2026-09-22T08:10:03Z INFO mcp tool call tool=get_unread_messages user_id=245 status=ok
2026-09-22T08:10:03Z INFO probe ok step=list_dialogs
2026-09-22T08:10:03Z INFO mcp tool call tool=list_dialogs user_id=245 status=ok
2026-09-22T08:07:12Z INFO oauth: client_registration request user_agent=Cursor/1.0.0 client_name=Cursor
2026-09-22T08:01:19Z INFO mcp tool call tool=get_messages user_id=9980 peer=user:<id> status=ok
2026-09-22T08:01:12Z INFO mcp tool call tool=get_messages user_id=9980 peer=channel:<id> status=ok
2026-09-22T08:01:12Z INFO mcp tool call tool=get_unread_messages user_id=9980 peer=user:<id> status=ok
2026-09-22T08:00:32Z INFO mcp tool call tool=list_dialogs user_id=9980 status=ok
2026-09-22T08:00:03Z INFO canary run complete ok=true duration_seconds=1.282 tg_user_id=924671154 version=0.67.0
2026-09-22T07:50:03Z INFO canary run complete ok=true duration_seconds=1.228 tg_user_id=924671154 version=0.67.0
2026-09-22T07:42:37Z INFO idle telegram client, closing user_id=9980 idle_ns=640611540862
2026-09-22T07:40:03Z INFO canary run complete ok=true duration_seconds=1.277 tg_user_id=924671154 version=0.67.0
2026-09-22T07:31:57Z INFO mcp tool call tool=get_messages user_id=9980 peer=channel:<id> status=ok
2026-09-22T07:31:42Z INFO oauth: client_registration request user_agent=Cursor/1.0.0 client_name=Cursor
2026-09-22T07:31:30Z INFO mcp tool call tool=get_messages user_id=9980 peer=chat:<id> status=ok
2026-09-22T07:30:03Z INFO canary run complete ok=true duration_seconds=1.260 tg_user_id=924671154 version=0.67.0
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
