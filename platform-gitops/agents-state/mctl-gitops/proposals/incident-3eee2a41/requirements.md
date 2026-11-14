# Requirements: incident-3eee2a41

## Incident
- ID: 16d5f2db-3cb1-43ea-84fd-a8ce3eee2a41
- Tenant: erpact
- Service: erpact-control
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-14T09:21:20.364136Z

### Summary
```
ArgoCD application erpact-control OutOfSync for 1h
```

## Evidence
### Labels
```
none provided
```

### Log Snippet
```
mctl_get_service_logs: service not found: erpact-control (workspace "erpact")
mctl_list_services for erpact: count 0 (argocd ok, complete true)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
