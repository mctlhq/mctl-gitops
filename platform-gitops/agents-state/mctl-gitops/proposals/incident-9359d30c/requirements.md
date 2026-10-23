# Requirements: incident-9359d30c

## Incident
- ID: 3d64a3c3-a6f3-4cf7-a0dc-ca2f9359d30c
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramToolAvailabilitySlowBurn
- Created: 2026-10-23T19:26:44.144779Z

### Summary
```
mctl-telegram: MCP tool availability slow burn (6x, 6h)
```

## Evidence
### Labels
```
source: alertmanager
type: generic
severity: warning
status: escalated
analysis: Escalated: no skill matched this ticket (type=generic, alert=MctlTelegramToolAvailabilitySlowBurn).
```

### Log Snippet
```
2026-10-23T20:10:03Z canary: canary run complete ok=true duration_seconds=1.19 version=0.91.0
2026-10-23T20:10:03Z canary: probe ok steps oauth_metadata, mcp_init, list_dialogs, get_unread_messages
2026-10-23T20:10:03Z base-service: mcp tool call tool=get_unread_messages status=ok
2026-10-23T20:10:03Z base-service: mcp tool call tool=list_dialogs status=ok
2026-10-23T20:01:25Z preview base-service: listening addr=:8080 (labs-mctl-telegram-preview, new pod)
2026-10-23T20:01:22Z preview base-service: WARN db not reachable yet, retrying err=connect: connection refused shared-pg-rw.platform-db.svc.cluster.local:5432 attempt=0
2026-10-23T20:01:24Z preview base-service: db reachable attempts=1
2026-10-23T20:01:13Z preview base-service (old pod): shutdown signal received
2026-10-23T20:00:04Z canary: canary run complete ok=true
2026-10-23T19:50:03Z canary: canary run complete ok=true
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
