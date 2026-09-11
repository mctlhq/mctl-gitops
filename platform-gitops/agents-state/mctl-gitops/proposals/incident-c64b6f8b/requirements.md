# Requirements: incident-c64b6f8b

## Incident
- ID: 53aa773f-0624-4197-a6b9-d6c6c64b6f8b
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-11T14:32:43.860285Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
(mctl_get_incident returned no separate labels field for this incident;
type=generic, source=alertmanager, tenant=labs, severity=warning)
```

### Log Snippet
Recent `labs/mctl-telegram` logs (canary probes and base-service MCP tool
calls) sampled at the time of writing. All entries observed are healthy
("ok") — no explicit session-borrow errors or timeouts appear in this
sample:
```
2026-09-11T15:10:03Z INFO canary run complete ok=true duration_seconds=1.589941445 tg_user_id=924671154 version=0.64.2
2026-09-11T15:10:03Z INFO probe ok step=get_unread_messages
2026-09-11T15:10:03Z INFO mcp tool call tool=get_unread_messages user_id=245 status=ok
2026-09-11T15:10:03Z INFO probe ok step=list_dialogs
2026-09-11T15:10:03Z INFO mcp tool call tool=list_dialogs user_id=245 status=ok
2026-09-11T15:10:03Z INFO probe ok step=mcp_init
2026-09-11T15:10:03Z INFO probe ok step=oauth_metadata
2026-09-11T15:10:02Z INFO token lifetime expires_at=2026-09-23T20:28:54Z
2026-09-11T15:03:45Z INFO mcp tool call tool=get_messages user_id=9980 status=ok peer=chat:<id>
2026-09-11T15:03:45Z INFO mcp tool call tool=get_messages user_id=9980 status=ok peer=channel:<id>
2026-09-11T15:03:17Z INFO mcp tool call tool=get_messages user_id=9980 status=ok peer=chat:<id>
2026-09-11T15:03:16Z INFO mcp tool call tool=get_messages user_id=9980 status=ok peer=user:<id>
2026-09-11T15:03:14Z INFO mcp tool call tool=get_messages user_id=9980 status=ok peer=username:len=13
2026-09-11T15:00:49Z INFO mcp tool call tool=list_dialogs user_id=9980 status=ok
2026-09-11T15:00:03Z INFO canary run complete ok=true duration_seconds=1.399462667 tg_user_id=924671154 version=0.64.2
2026-09-11T15:00:03Z INFO probe ok step=get_unread_messages
2026-09-11T15:00:03Z INFO mcp tool call tool=get_unread_messages user_id=245 status=ok
2026-09-11T15:00:03Z INFO probe ok step=list_dialogs
2026-09-11T15:00:03Z INFO mcp tool call tool=list_dialogs user_id=245 status=ok
2026-09-11T14:50:03Z INFO canary run complete ok=true duration_seconds=1.445383044 tg_user_id=924671154 version=0.64.2
2026-09-11T14:50:03Z INFO probe ok step=get_unread_messages
2026-09-11T14:50:03Z INFO mcp tool call tool=get_unread_messages user_id=245 status=ok
2026-09-11T14:50:03Z INFO mcp tool call tool=list_dialogs user_id=245 status=ok
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
