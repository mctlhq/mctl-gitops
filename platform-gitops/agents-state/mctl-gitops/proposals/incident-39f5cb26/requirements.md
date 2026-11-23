# Requirements: incident-39f5cb26

## Incident
- ID: 98d5e542-c001-4a4a-bd28-1ca839f5cb26
- Tenant: mctl-api
- Service: admins-mctl-api
- Alert: ArgoCDApplicationDegraded (type argocd_app_degraded)
- Created: 2026-11-16T10:13:20.566022Z

### Summary
```
ArgoCD application admins-mctl-api has been Degraded for 30m
```

## Evidence
### Labels
```
(none returned by mctl_get_incident)
```

### Log Snippet
```
Logs unavailable: tenant "mctl-api" not found; workspace "admins" has no service mctl-api;
mctl_get_service_status for admins/mctl-api: ArgoCD application not found: admins-mctl-api.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
