# Requirements: incident-87dca34b

## Incident
- ID: 33677590-1d17-476b-a914-ad0c87dca34b
- Tenant: platform
- Service: TooHighChurnRate24h
- Alert: TooHighChurnRate24h
- Created: 2026-10-23T18:16:59.85877Z

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
```

### Log Snippet
```
(no log lines returned; "TooHighChurnRate24h" is an alert name, not a deployed service)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
