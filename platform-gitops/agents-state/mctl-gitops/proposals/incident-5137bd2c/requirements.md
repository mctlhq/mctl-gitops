# Requirements: incident-5137bd2c

## Incident
- ID: 405f488e-2384-4187-8f73-1f1e5137bd2c
- Tenant: erpact
- Service: erpact-infra
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-14T10:01:20.584514Z

### Summary
```
ArgoCD application erpact-infra OutOfSync for 1h
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
tenant: erpact
service: erpact-infra
```

### Log Snippet
```
mctl_get_service_logs(erpact, erpact-infra): service not found: erpact-infra (workspace "erpact")
mctl_list_services(erpact): count 0, complete true, argocd ok
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
