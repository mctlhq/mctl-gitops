# Requirements: incident-1ad5823f

## Incident
- ID: 47266b59-ad17-4360-a67a-63a21ad5823f
- Tenant: erpact
- Service: erpact-control-scheduler
- Alert: CPUThrottlingHigh (type resource_limit)
- Created: 2026-10-26T18:24:45.272392Z

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
no log lines returned by mctl_get_service_logs for erpact/erpact-control-scheduler
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
