# Requirements: incident-ebca38d8

## Incident
- ID: 061a3c25-f2d0-4bc0-83fd-17a6ebca38d8
- Tenant: platform-events
- Service: valkey-0
- Alert: CPUThrottlingHigh (type resource_limit)
- Created: 2026-10-23T11:15:44.706524Z

### Summary
```
Processes experience elevated CPU throttling.
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
status: escalated
confidence: MEDIUM
```

### Log Snippet
```
(no log lines returned by mctl_get_service_logs for platform-events/valkey-0)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
