# Requirements: incident-bb4f6134

## Incident
- ID: 2ff8eb3c-3061-4b4e-b485-4934bb4f6134
- Tenant: platform-events
- Service: valkey-0
- Alert: CPUThrottlingHigh (type resource_limit)
- Created: 2026-10-20T10:52:44.71324Z

### Summary
```
Processes experience elevated CPU throttling.
```

## Evidence
### Labels
```
(none returned by mctl_get_incident)
```

### Log Snippet
```
(no log lines returned by mctl_get_service_logs for platform-events/valkey-0)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
