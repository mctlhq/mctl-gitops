# Requirements: incident-3ee9371a

## Incident
- ID: fd8fa685-d901-4b39-9016-29bb3ee9371a
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowFastBurn (type=generic, source=alertmanager)
- Created: 2026-10-23T17:44:43.844766Z

### Summary
```
mctl-telegram: session borrow fast burn (14.4x, 1h)
```

## Evidence
### Labels
```
severity: critical
tenant: labs
status: escalated
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramSessionBorrowFastBurn).
```

### Log Snippet
```
18:09:06 WARN db not reachable yet, retrying (labs-mctl-telegram): dial tcp 10.43.131.86:5432 (shared-pg-rw.platform-db.svc.cluster.local): connection refused
18:09:06 INFO starting auth_mode=local-jwt allow_send=true
18:09:08 INFO db reachable attempts=1
18:09:08 INFO listening addr=:8080
18:08:58 INFO shutdown signal received (old pod d4f9b44d5-rjrnw)
18:08:09 WARN db not reachable yet, retrying (labs-mctl-telegram-preview): connection refused
18:10:03 INFO canary run complete ok=true version=0.90.0
18:11:41-18:14:45 INFO mcp tool call send_message/get_messages/get_media/send_media status=ok
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
