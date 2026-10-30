# Requirements: incident-ea2c2de3

## Incident
- ID: 29aaa2a6-6316-4989-a0fd-7cb1ea2c2de3
- Tenant: platform-events
- Service: valkey-0
- Alert: CPUThrottlingHigh (type resource_limit)
- Created: 2026-10-26T18:29:45.251293Z

### Summary
```
Processes experience elevated CPU throttling.
```

## Evidence
### Labels
```
none provided
```

### Log Snippet
```
no log lines returned by mctl_get_service_logs for platform-events/valkey-0
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
