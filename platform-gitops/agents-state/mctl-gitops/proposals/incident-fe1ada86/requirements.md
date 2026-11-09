# Requirements: incident-fe1ada86

## Incident
- ID: 8893fe90-a3e8-4fd5-9cae-6c55fe1ada86
- Tenant: argocd
- Service: root-app
- Alert: ArgoCDApplicationDegraded (type argocd_app_degraded)
- Created: 2026-11-08T09:32:20.544743Z

### Summary
```
ArgoCD application root-app has been Degraded for 30m
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
status: escalated
```

### Log Snippet
```
No logs available. mctl_get_service_status for argocd/root-app returned "ArgoCD application not found: argocd-root-app" (naming convention mismatch).
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
