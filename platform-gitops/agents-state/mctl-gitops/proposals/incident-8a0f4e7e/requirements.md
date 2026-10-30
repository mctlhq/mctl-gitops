# Requirements: incident-8a0f4e7e

## Incident
- ID: 62e6ff4c-fb29-4abc-8fde-b79c8a0f4e7e
- Tenant: platform
- Service: MctlApiDown
- Alert: MctlApiDown (type generic, source alertmanager, severity critical)
- Created: 2026-10-21T10:32:55.536278Z

### Summary
```
api.mctl.ai has failed its health check for 3 minutes
```

## Evidence
### Labels
```
none provided in incident record
```

### Log Snippet
```
mctl_get_service_logs(team=platform, service=mctl-api, since=1h) returned zero lines.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
