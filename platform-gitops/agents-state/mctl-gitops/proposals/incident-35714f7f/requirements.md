# Requirements: incident-35714f7f

## Incident
- ID: 304d2f99-c7bc-4a5d-82d6-d91735714f7f
- Tenant: platform
- Service: TooHighChurnRate24h
- Alert: TooHighChurnRate24h
- Created: 2026-11-04T12:27:02.306543Z

### Summary
```
Too high number of new series created over last 24h
```

## Evidence
### Labels
```
source: alertmanager
type: generic
severity: warning
occurrence_count: 1
```

### Log Snippet
```
No logs available: the "service" field of this incident holds the alert name (TooHighChurnRate24h), not a real workload, so mctl_get_service_logs rejected it ("team and app must be DNS labels").
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
