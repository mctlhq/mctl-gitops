# Requirements: incident-6010313b

## Incident
- ID: b2566ca7-de4f-4334-a226-f3966010313b
- Tenant: vault
- Service: vault
- Alert: StatefulSet rollout not complete (type generic)
- Created: 2026-10-26T18:24:45.540176Z

### Summary
```
StatefulSet update has not been rolled out.
```

## Evidence
### Labels
```
none provided
```

### Log Snippet
```
no log lines returned by mctl_get_service_logs for vault/vault
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
