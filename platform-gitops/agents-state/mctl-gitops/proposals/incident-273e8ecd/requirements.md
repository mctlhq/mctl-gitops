# Requirements: incident-273e8ecd

## Incident
- ID: 1271ce87-fbd1-4c49-8aac-fa72273e8ecd
- Tenant: labs
- Service: mctl-telegram (incident service field empty)
- Alert: MctlTelegramSessionBorrowFastBurn (type generic)
- Created: 2026-10-28T21:21:44.172548Z

### Summary
```
mctl-telegram: session borrow fast burn (14.4x, 1h)
```

## Evidence
### Labels
```
source: alertmanager
severity: critical
analysis: no skill matched this ticket
```

### Log Snippet
```
base-service: WARN mcp tool call tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
base-service: WARN mcp tool call tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
base-service: INFO idle telegram client, closing user_id=1
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
