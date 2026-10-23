# Requirements: incident-a068195b

## Incident
- ID: ad67cfd8-3ef7-47b7-9aba-f8dda068195b
- Tenant: erpact
- Service: erpact-control-scheduler
- Alert: CPUThrottlingHigh (type resource_limit)
- Created: 2026-10-23T11:11:44.79196Z

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
(no log lines returned by mctl_get_service_logs for erpact/erpact-control-scheduler)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
