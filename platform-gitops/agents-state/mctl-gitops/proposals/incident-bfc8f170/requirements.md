# Requirements: incident-bfc8f170

## Incident
- ID: d1e53e0e-1cce-428d-bf12-2033bfc8f170
- Tenant: erpact
- Service: erpact-shared-scheduler
- Alert: CPUThrottlingHigh (type resource_limit)
- Created: 2026-10-20T10:52:44.843901Z

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
(no log lines returned by mctl_get_service_logs for erpact/erpact-shared-scheduler)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
