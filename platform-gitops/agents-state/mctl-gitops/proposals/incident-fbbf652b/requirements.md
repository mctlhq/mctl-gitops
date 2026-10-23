# Requirements: incident-fbbf652b

## Incident
- ID: e11c75e9-14d7-4ddc-8557-ea8ffbbf652b
- Tenant: erpact
- Service: erpact-shared-scheduler
- Alert: CPUThrottlingHigh (type resource_limit)
- Created: 2026-10-23T11:11:44.809222Z

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
(no log lines returned by mctl_get_service_logs for erpact/erpact-shared-scheduler)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
