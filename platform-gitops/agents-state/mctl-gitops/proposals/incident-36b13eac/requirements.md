# Requirements: incident-36b13eac

## Incident
- ID: bd637526-9bff-4023-822e-490936b13eac
- Tenant: labs
- Service: mctl-rules
- Alert: generic (Deployment rollout is not progressing)
- Created: 2026-10-24T08:24:45.259724Z

### Summary
```
Deployment rollout is not progressing.
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
