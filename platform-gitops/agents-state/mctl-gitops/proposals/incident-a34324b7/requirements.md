# Requirements: incident-a34324b7

## Incident
- ID: da497bda-9db8-486e-8bd1-cae5a34324b7
- Tenant: erpact
- Service: (none)
- Alert: PreviewReaperNotTriggered
- Created: 2026-10-20T01:49:00.293126Z

### Summary
```
preview-reaper in erpact has not been triggered for 3h
```

## Evidence
### Labels
```
tenant: erpact
type: generic
severity: warning
source: alertmanager
```

### Log Snippet
```
No log lines returned for preview-reaper (count 0). No Argo workflows listed for the mctl team.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
