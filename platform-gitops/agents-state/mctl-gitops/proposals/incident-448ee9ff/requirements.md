# Requirements: incident-448ee9ff

## Incident
- ID: 853412bc-134b-428c-be15-0d44448ee9ff
- Tenant: labs
- Service: mctl-rules
- Alert: pod_crashloop (pod non-ready for more than 15 minutes)
- Created: 2026-10-24T08:14:45.244963Z

### Summary
```
Pod has been in a non-ready state for more than 15 minutes.
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
