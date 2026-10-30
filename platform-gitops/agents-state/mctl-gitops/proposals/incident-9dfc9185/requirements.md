# Requirements: incident-9dfc9185

## Incident
- ID: b4d11014-bad4-45ec-8a24-d33f9dfc9185
- Tenant: erpact
- Service: erpact-shared-scheduler
- Alert: CPUThrottlingHigh (type resource_limit)
- Created: 2026-10-26T18:24:45.295049Z

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
no log lines returned by mctl_get_service_logs for erpact/erpact-shared-scheduler
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
