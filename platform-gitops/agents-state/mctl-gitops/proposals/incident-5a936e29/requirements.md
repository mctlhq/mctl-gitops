# Requirements: incident-5a936e29

## Incident
- ID: 967fa7e7-48f0-4544-9320-d2e45a936e29
- Tenant: labs
- Service: labs-mctl-rules
- Alert: ArgoCDApplicationDegraded (type argocd_app_degraded)
- Created: 2026-10-24T08:40:21.998654Z

### Summary
```
ArgoCD application labs-mctl-rules has been Degraded for 30m
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
mctl-agent analysis: no skill matched this ticket.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
