# Requirements: incident-b0a868fe

## Incident
- ID: 6ecfcbfc-39a3-4039-9fad-909bb0a868fe
- Tenant: argocd
- Service: root-app
- Alert: ArgoCDApplicationDegraded (type argocd_app_degraded)
- Created: 2026-11-19T21:43:20Z

### Summary
```
ArgoCD application root-app has been Degraded for 30m
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
status: escalated
analysis: no skill matched this ticket (alert=ArgoCDApplicationDegraded); needs a human or a new skill
```

### Log Snippet
```
No logs available: mctl_get_service_logs returned "tenant not found: argocd".
```

A related incident (ebc2bf65-6ac3-4d08-bd49-67b14f04ddab, ArgoCDApplicationOutOfSyncLong for root-app, created 2026-11-19T22:13Z) is the same application and likely the same cause. It was too recent to process in this run.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
