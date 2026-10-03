# Requirements: incident-d7920bbc

## Incident
- ID: 8b011abd-bc60-4586-89b2-40aad7920bbc
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn (type=generic)
- Created: 2026-10-01T09:34:43.747838Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
tenant: labs
service: (empty)
severity: warning
source: alertmanager
status: escalated
analysis: no skill matched this ticket (type=generic, alert=MctlTelegramSessionBorrowSlowBurn); needs a human or a new skill
```

### Log Snippet
```
09:59:55 WARN mcp tool call get_messages user_id=105074 status=error reason=telegram_error err="peer not in dialog list ... USERNAME_NOT_OCCUPIED (rpc error code 400)"
09:59:55 WARN mcp mtproto error tool=get_messages mtproto_code=USERNAME_NOT_OCCUPIED http_code=400
10:10:02 INFO canary run complete ok=true duration_seconds=1.14 version=0.75.0
10:11:15 INFO idle telegram client, closing user_id=105074 idle=609781498096
10:11:22 INFO idle telegram client, closing user_id=9980 idle=642597591665
All other mcp tool calls in the last ~40 minutes: status=ok
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service, or fires only on genuine session borrow failures.
