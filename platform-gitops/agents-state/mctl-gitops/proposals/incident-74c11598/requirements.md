# Requirements: incident-74c11598

## Incident
- ID: 5ebcf1be-f041-468d-bc40-d59974c11598
- Tenant: erpact
- Service: erpact-control-scheduler
- Alert: CPUThrottlingHigh (type resource_limit)
- Created: 2026-10-20T10:52:44.766386Z

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
(no log lines returned by mctl_get_service_logs for erpact/erpact-control-scheduler)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
