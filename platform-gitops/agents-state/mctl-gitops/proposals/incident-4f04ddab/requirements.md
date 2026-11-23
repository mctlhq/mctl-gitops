# Requirements: incident-4f04ddab

## Incident
- ID: ebc2bf65-6ac3-4d08-bd49-67b14f04ddab
- Tenant: argocd
- Service: root-app
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-19T22:13:20Z

### Summary
```
ArgoCD application root-app OutOfSync for 1h
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
type: argocd_app_degraded
tenant: argocd
service: root-app
```

### Log Snippet
```
No logs available: mctl_get_service_logs returned "tenant not found: argocd".
root-app is an ArgoCD Application, not a tenant workload.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
