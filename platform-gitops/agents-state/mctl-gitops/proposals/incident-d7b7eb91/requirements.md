# Requirements: incident-d7b7eb91

## Incident
- ID: 5133bdab-6334-424b-85f8-5667d7b7eb91
- Tenant: admins
- Service: admins-mctl-agents-worker
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-12T03:43:20.454793Z

### Summary
```
ArgoCD application admins-mctl-agents-worker OutOfSync for 1h
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
tenant: admins
service: admins-mctl-agents-worker
```

### Log Snippet
```
Service logs (last hour) show no errors: only routine httpx GETs, policy decisions (ALLOW, claim:execution-request) and GitHub proposal polling.
Service status from mctl: ArgoCD health=Healthy, syncStatus=OutOfSync, revision="" (empty), imageTag=1.117.0, componentType=base-service.
mctl-agent analysis: no skill matched (type=argocd_app_degraded, alert=ArgoCDApplicationOutOfSyncLong); confidence LOW.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
