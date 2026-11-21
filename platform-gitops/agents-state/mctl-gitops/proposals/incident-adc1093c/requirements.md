# Requirements: incident-adc1093c

## Incident
- ID: c2152f53-4d9e-4111-9850-7973adc1093c
- Tenant: mctl-api
- Service: mctl-api
- Alert: KubeDeploymentRolloutStuck (type: generic)
- Created: 2026-11-20T08:29:45.38466Z

### Summary
```
Deployment rollout is not progressing.
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
tenant: mctl-api
service: mctl-api
```

### Log Snippet
```
No logs available. mctl_get_service_logs and mctl_get_service_pods returned
"tenant not found: mctl-api" for team=mctl-api, and "service not found" for
team=admins service=mctl-api. mctl-api is not in the admins catalogue listing.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
