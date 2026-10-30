# Requirements: incident-8f4af826

## Incident
- ID: c2c269da-ed6b-4b0b-a3fc-fcc18f4af826
- Tenant: labs
- Service: mctl-rules
- Alert: argocd_app_degraded (polling)
- Created: 2026-10-24T08:13:26.453752Z

### Summary
```
ArgoCD app labs-mctl-rules health: Degraded
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
