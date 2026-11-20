# Requirements: incident-218c7f53

## Incident
- ID: 9e39f201-a2c4-4ae7-9e2a-b3a3218c7f53
- Tenant: mctl-api
- Service: admins-mctl-api
- Alert: ArgoCDApplicationDegraded (type argocd_app_degraded)
- Created: 2026-11-20T08:45:20.551085Z

### Summary
```
ArgoCD application admins-mctl-api has been Degraded for 30m
```

## Evidence
### Labels
```
(none provided by the incident record)
```

### Log Snippet
```
No logs available. mctl_get_service_logs for mctl-api/admins-mctl-api failed with "tenant not found: mctl-api";
for admins/mctl-api it failed with "service not found: mctl-api (workspace admins)".
mctl_get_service_status found no ArgoCD application named mctl-api-admins-mctl-api or admins-mctl-api.
mctl_list_services for team admins lists 8 services; none is mctl-api or admins-mctl-api.
Only observed anomaly: admins-mctl-agents-worker is OutOfSync (not Degraded).
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
