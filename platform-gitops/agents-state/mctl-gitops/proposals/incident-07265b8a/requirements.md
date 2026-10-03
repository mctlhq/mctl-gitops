# Requirements: incident-07265b8a

## Incident
- ID: 70488bfb-a6a8-4508-a9e5-da5007265b8a
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramToolAvailabilitySlowBurn (type=generic)
- Created: 2026-10-03T14:47:43.730074Z

### Summary
```
mctl-telegram: MCP tool availability slow burn (6x, 6h)
```

## Evidence
### Labels
```
tenant: labs
service: (empty)
severity: warning
source: alertmanager
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramToolAvailabilitySlowBurn). No diagnostic rule for this signal.
```

### Log Snippet
```
2026-10-03T16:10:03Z canary: canary run complete ok=true duration_seconds=1.30 version=0.78.0
2026-10-03T16:10:03Z canary: probe ok step=get_unread_messages
2026-10-03T16:10:02Z canary: probe ok step=list_dialogs
2026-10-03T16:10:02Z canary: probe ok step=mcp_init
2026-10-03T16:10:02Z canary: probe ok step=oauth_metadata
2026-10-03T16:10:01Z canary: token lifetime expires_at=2026-10-13T20:30:02Z
2026-10-03T16:00:02Z canary: canary run complete ok=true duration_seconds=0.95
2026-10-03T15:50:03Z canary: canary run complete ok=true duration_seconds=0.94
2026-10-03T16:00:25Z base-service (preview): mcp tool call tool=get_messages status=ok
2026-10-03T15:42:56Z base-service: idle telegram client, closing user_id=105074
(all 50 fetched lines are INFO level; no error or warn lines)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
