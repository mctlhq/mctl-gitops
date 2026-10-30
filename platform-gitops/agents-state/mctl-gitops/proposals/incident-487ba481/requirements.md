# Requirements: incident-487ba481

## Incident
- ID: 3064afdc-2510-47a6-9609-94af487ba481
- Tenant: vault
- Service: vault
- Alert: generic (alertmanager) - StatefulSet update has not been rolled out
- Created: 2026-10-19T22:58:45.535677Z

### Summary
```
StatefulSet update has not been rolled out.
```

## Evidence
### Labels
```
(no labels returned by mctl_get_incident)
```

### Log Snippet
```
(no log lines returned by mctl_get_service_logs for team=vault service=vault, last 50 lines)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
