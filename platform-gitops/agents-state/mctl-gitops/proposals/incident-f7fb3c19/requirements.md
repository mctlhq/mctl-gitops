# Requirements: incident-f7fb3c19

## Incident
- ID: 2e953497-f6aa-4d08-b519-3eb7f7fb3c19
- Tenant: argocd
- Service: root-app
- Alert: ArgoCDApplicationDegraded (type argocd_app_degraded)
- Created: 2026-11-20T12:50:20.42078Z

### Summary
```
ArgoCD application root-app has been Degraded for 30m
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
tenant: argocd
service: root-app
```

### Log Snippet
```
No logs available: mctl_get_service_logs returned "tenant not found: argocd".
root-app is an ArgoCD app-of-apps, not a tenant service, so Loki has no tenant logs for it.
mctl-agent analysis: no skill matched this signal; nothing was analysed.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN root-app is inspected THEN its health is Healthy and no child Application is Degraded.
