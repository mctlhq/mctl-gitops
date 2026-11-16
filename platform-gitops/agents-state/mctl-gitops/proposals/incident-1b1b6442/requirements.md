# Requirements: incident-1b1b6442

## Incident
- ID: 47ef9c47-9cdc-4385-b291-ea161b1b6442
- Tenant: mctl-api
- Service: mctl-api
- Alert: KubeDeploymentRolloutStuck (type generic)
- Created: 2026-11-16T09:58:45.334709Z

### Summary
```
Deployment rollout is not progressing.
```

## Evidence
### Labels
```
(none returned by mctl_get_incident)
```

### Log Snippet
```
Logs unavailable: mctl_get_service_logs returned "tenant not found: mctl-api".
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
