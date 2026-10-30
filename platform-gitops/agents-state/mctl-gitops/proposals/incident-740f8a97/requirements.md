# Requirements: incident-740f8a97

## Incident
- ID: b350e5ec-a876-435f-af1d-d956740f8a97
- Tenant: labs
- Service: (empty)
- Alert: MctlTelegramSessionBorrowSlowBurn (type generic)
- Created: 2026-10-23T07:31:43.843664Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
status: escalated
analysis: no skill matched this ticket (type=generic)
```

### Log Snippet
```
2026-10-23T09:10:03Z base-service WARN tool=list_dialogs user_id=245 status=error reason=telegram_error err="no active session"
2026-10-23T09:10:03Z base-service WARN tool=get_unread_messages user_id=245 status=error reason=telegram_error err="no active session"
2026-10-23T09:10:16Z base-service WARN tool=list_dialogs user_id=245 status=error err="no active session"
2026-10-23T09:11:08Z base-service WARN tool=search_messages user_id=183623 status=error reason=telegram_error slo_status=caller_error err="MessagesSearch: rpc error code 400: CHANNEL_INVALID"
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
