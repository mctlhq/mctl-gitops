# Requirements: incident-7a4031fa

## Incident
- ID: 0cc68805-b682-47a6-9645-9cf47a4031fa
- Tenant: erpact
- Service: erpact-deployer
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-14T09:21:20.410375Z

### Summary
```
ArgoCD application erpact-deployer OutOfSync for 1h
```

## Evidence
### Labels
```
none provided
```

### Log Snippet
```
mctl_get_service_logs: service not found: erpact-deployer (workspace "erpact")
mctl_list_services for erpact: count 0 (argocd ok, complete true)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
