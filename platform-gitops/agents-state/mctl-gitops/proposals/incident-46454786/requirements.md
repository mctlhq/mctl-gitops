# Requirements: incident-46454786

## Incident
- ID: c16a448d-f6cf-419b-ae0b-07e346454786
- Tenant: platform
- Service: MctlTelegramConnectorNoFirstCall
- Alert: MctlTelegramConnectorNoFirstCall (type=generic, source=alertmanager)
- Created: 2026-11-01T12:39:39.926032Z

### Summary
```
mctl-telegram: other connectors get tokens but never make a call
```

## Evidence
### Labels
```
(none returned by the incident API; the "service" field holds the alert name, not a deployable service)
```

### Log Snippet
Logs for the real workload (team labs, service mctl-telegram), last 3h, tail:
```
2026-11-01T13:10:08Z canary: token lifetime expires_at=2026-11-29T11:42:56Z
2026-11-01T13:10:08Z canary: probe ok step=oauth_metadata, mcp_init, list_dialogs, get_unread_messages
2026-11-01T13:10:08Z canary: canary run complete ok=true duration_seconds=1.146 version=0.119.0
2026-11-01T13:10:08Z base-service: mcp tool call tool=list_dialogs user_id=6462 status=ok
2026-11-01T13:10:08Z base-service: mcp tool call tool=get_unread_messages user_id=6462 status=ok
2026-11-01T13:10:08Z base-service: oauth: callback request rejected reason=unknown_state prefetch=false (canary negative probe, expected)
2026-11-01T13:09:05Z base-service: mcp tool call tool=get_messages user_id=96357 status=ok
2026-11-01T13:04:11Z base-service: mcp tool call tool=send_message:sent user_id=6462 status=ok
2026-11-01T13:03:54Z base-service: mcp tool call tool=get_messages user_id=267999 status=ok (many)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
