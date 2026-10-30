# Requirements: incident-2a6e551f

## Incident
- ID: a7ba7606-59a0-4231-9c54-93e02a6e551f
- Tenant: labs
- Service: mctl-rules
- Alert: generic (Deployment has not matched the expected number of replicas)
- Created: 2026-10-24T08:24:45.263539Z

### Summary
```
Deployment has not matched the expected number of replicas.
```

## Evidence
### Labels
```
none provided by the incident record
```

### Log Snippet
```
mctl_get_service_logs for labs/mctl-rules returned zero lines (1h window).
mctl_get_service_status: ArgoCD health Degraded, sync Synced, imageTag 0.1.0, port 3000, componentType base-service, hasDatabase true.
mctl-agent analysis: skill argocd_sync_failed gave LOW confidence, fixable=false.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
