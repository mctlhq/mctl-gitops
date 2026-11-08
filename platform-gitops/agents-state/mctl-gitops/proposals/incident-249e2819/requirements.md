# Requirements: incident-249e2819

## Incident
- ID: bf37f062-5b46-4057-9c3b-9f4e249e2819
- Tenant: forgejo
- Service: forgejo
- Alert: ArgoCDApplicationDegraded (type argocd_app_degraded)
- Created: 2026-11-08T09:32:20.563154Z

### Summary
```
ArgoCD application forgejo has been Degraded for 30m
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
No logs available: mctl_get_service_logs and mctl_get_service_pods both returned "tenant not found: forgejo". mctl_list_services for team forgejo returned zero services.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
