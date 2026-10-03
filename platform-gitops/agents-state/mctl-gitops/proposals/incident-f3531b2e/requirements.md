# Requirements: incident-f3531b2e

## Incident
- ID: 5a1534d8-b8e8-4985-885d-a969f3531b2e
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-24T22:42:43.744625Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
(no labels were returned by mctl_get_incident for this incident — source=alertmanager, type=generic, severity=warning)
```

### Log Snippet
Last 50 lines fetched for tenant=labs, service=mctl-telegram (6h window, most recent
first, truncated here to the most relevant subset). No session-borrow failures, no
AUTH_KEY_DUPLICATED, and no errors of any kind appear in this window — every OAuth
client_registration, MCP tool call, and canary probe recorded here succeeded:
```
2026-09-24T23:12:45Z INFO oauth: client_registration audit outcome=accepted client_name="Google Antigravity"
2026-09-24T23:11:48Z INFO oauth: client_registration audit outcome=accepted client_name="Google Antigravity"
2026-09-24T23:10:03Z INFO canary run complete ok=true duration_seconds=1.235682149 tg_user_id=924671154 version=0.68.0
2026-09-24T23:10:03Z INFO probe ok step=get_unread_messages
2026-09-24T23:10:03Z INFO mcp tool call tool=get_unread_messages user_id=245 status=ok
2026-09-24T23:10:03Z INFO probe ok step=list_dialogs
2026-09-24T23:10:02Z INFO mcp tool call tool=list_dialogs user_id=245 status=ok
2026-09-24T23:10:02Z INFO probe ok step=mcp_init
2026-09-24T23:10:01Z INFO token lifetime expires_at=2026-10-13T20:30:02Z
2026-09-24T23:07:00Z INFO event outbox purged rows=2
2026-09-24T23:00:03Z INFO canary run complete ok=true duration_seconds=1.480919513 tg_user_id=924671154 version=0.68.0
2026-09-24T23:00:03Z INFO probe ok step=get_unread_messages
2026-09-24T23:00:03Z INFO mcp tool call tool=get_unread_messages user_id=245 status=ok
2026-09-24T23:00:03Z INFO probe ok step=list_dialogs
2026-09-24T22:59:02Z INFO mcp tool call tool=get_messages user_id=1 status=ok peer=user:<id>
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
