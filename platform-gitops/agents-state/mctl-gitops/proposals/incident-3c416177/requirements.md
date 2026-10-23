# Requirements: incident-3c416177

## Incident
- ID: 66919f80-cb88-4514-979f-c3793c416177
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramToolAvailabilityFastBurn (type=generic)
- Created: 2026-10-23T17:38:43.742155Z

### Summary
```
mctl-telegram: MCP tool availability fast burn (14.4x, 1h)
```

## Evidence
### Labels
```
tenant: labs
severity: critical
source: alertmanager
```

### Log Snippet
```
18:09:06 WARN db not reachable yet, retrying: dial tcp 10.43.131.86:5432 (shared-pg-rw.platform-db.svc.cluster.local): connect: connection refused (attempt 0, user=labs-mctl-telegram)
18:09:08 INFO db reachable (attempts=1)
18:09:08 INFO listening addr=:8080
18:08:58 INFO shutdown signal received (old pod d4f9b44d5-rjrnw)
18:08:09 WARN db not reachable yet, retrying: connection refused (preview pod, user=labs-mctl-telegram-preview)
18:08:11 INFO db reachable (attempts=1)
18:10:03 INFO probe ok step=mcp_init / list_dialogs / get_unread_messages
18:10:03 INFO canary run complete ok=true duration_seconds=1.41 version=0.90.0
18:09:08 WARN DEMO_REVIEWER_ENABLED is on (observed, unrelated to this alert)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
