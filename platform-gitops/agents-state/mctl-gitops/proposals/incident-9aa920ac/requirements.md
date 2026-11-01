# Requirements: incident-9aa920ac

## Incident
- ID: e43319af-620b-4335-a176-9dc09aa920ac
- Tenant: platform
- Service: TooHighChurnRate24h (the incident's service field holds the alert name; no such service exists)
- Alert: TooHighChurnRate24h (type: generic, source: alertmanager)
- Created: 2026-11-01T01:16:29.886373Z

### Summary
```
Too high number of new series created over last 24h
```

## Evidence
### Labels
```
severity: warning
source: alertmanager
```

### Log Snippet
```
No logs available. mctl_get_service_logs failed for platform/TooHighChurnRate24h:
"team and app must be DNS labels" (the service field is an alert name, not a workload).
mctl-agent analysis: no skill matched; nothing was analysed.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
