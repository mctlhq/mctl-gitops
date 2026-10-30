# Requirements: incident-cc0b6c7d

## Incident
- ID: 7b03b468-9302-48ac-8c24-ca71cc0b6c7d
- Tenant: commerce-proof
- Service: (none)
- Alert: PreviewReaperNotTriggered
- Created: 2026-10-20T01:49:00.395103Z

### Summary
```
preview-reaper in commerce-proof has not been triggered for 3h
```

## Evidence
### Labels
```
tenant: commerce-proof
type: generic
severity: warning
source: alertmanager
```

### Log Snippet
```
No log lines returned for preview-reaper (mctl_get_service_logs returned count 0). No Argo workflows listed for the mctl team.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
