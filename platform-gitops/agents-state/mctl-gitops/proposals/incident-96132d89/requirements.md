# Requirements: incident-96132d89

## Incident
- ID: 8bebff18-8426-4a1d-bd95-004196132d89
- Tenant: labs
- Service: mctl-telegram (service field empty on the incident; taken from the summary)
- Alert: MctlTelegramSessionBorrowSlowBurn (type=generic, source=alertmanager)
- Created: 2026-10-05T06:03:43.750525Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
(no labels were returned by the incident API)
```

### Log Snippet
```
{"level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.198858658,"version":"0.79.1"}  (07:10:03Z)
{"level":"INFO","msg":"probe ok","step":"get_unread_messages"}
{"level":"INFO","msg":"probe ok","step":"list_dialogs"}
{"level":"INFO","msg":"probe ok","step":"mcp_init"}
{"level":"INFO","msg":"probe ok","step":"oauth_metadata"}
{"level":"INFO","msg":"idle telegram client, closing","user_id":105074,"idle":631055627010}  (06:47:38Z)
{"level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":105074,"status":"ok"}  (07:08:32Z)
All other mcp tool call lines in the last hour: status=ok. No ERROR or WARN lines found.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service, or fires only on a real borrow failure.
