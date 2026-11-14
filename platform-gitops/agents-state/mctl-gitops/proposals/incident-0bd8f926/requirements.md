# Requirements: incident-0bd8f926

## Incident
- ID: f317207b-0849-416e-b214-1ced0bd8f926
- Tenant: erpact
- Service: erpact-shared
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-14T09:21:20.509929Z

### Summary
```
ArgoCD application erpact-shared OutOfSync for 1h
```

## Evidence
### Labels
```
none provided
```

### Log Snippet
```
mctl_get_service_logs: service not found: erpact-shared (workspace "erpact")
mctl_list_services for erpact: count 0 (argocd ok, complete true)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
