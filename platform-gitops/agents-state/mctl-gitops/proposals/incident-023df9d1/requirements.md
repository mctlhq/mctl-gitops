# Requirements: incident-023df9d1

## Incident
- ID: eb83eabd-a11f-4b2a-9541-296c023df9d1
- Tenant: erpact
- Service: (none reported)
- Alert: PreviewReaperFailing (type=generic)
- Created: 2026-10-19T22:24:00.297111Z

### Summary
```
preview-reaper in erpact has failed with no success in 3h
```

## Evidence
### Labels
```
(no labels returned by the incident API)
```

### Log Snippet
```
No log lines returned by mctl_get_service_logs for erpact/preview-reaper over the last 6h (count=0).
```

mctl-agent analysis: no skill matched (type=generic, alert=PreviewReaperFailing); nothing was analysed.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
