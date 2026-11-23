# Requirements: incident-10aeb4c1

## Incident
- ID: aef133f8-94eb-4b0f-8b34-7d5610aeb4c1
- Tenant: mctl-api
- Service: mctl-api
- Alert: KubeDeploymentRolloutStuck (type=generic)
- Created: 2026-11-14T13:43:45.339598Z

### Summary
```
Deployment rollout is not progressing.
```

## Evidence
### Labels
```
(none provided by incident record)
```

### Log Snippet
```
No logs available. mctl_get_service_logs and mctl_get_service_pods returned
"tenant not found: mctl-api" for team=mctl-api, and "service not found: mctl-api
(workspace admins)" for team=admins.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
