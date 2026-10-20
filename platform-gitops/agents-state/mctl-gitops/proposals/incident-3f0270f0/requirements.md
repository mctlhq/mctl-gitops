# Requirements: incident-3f0270f0

## Incident
- ID: 4e2ab4b2-514e-451b-99dd-87623f0270f0
- Tenant: mctl
- Service: (none)
- Alert: PreviewReaperNotTriggered
- Created: 2026-10-20T01:49:00.292998Z

### Summary
```
preview-reaper in mctl has not been triggered for 3h
```

## Evidence
### Labels
```
tenant: mctl
type: generic
severity: warning
source: alertmanager
```

### Log Snippet
```
No log lines returned for preview-reaper in team mctl (count 0). No Argo workflows listed for the mctl team.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
