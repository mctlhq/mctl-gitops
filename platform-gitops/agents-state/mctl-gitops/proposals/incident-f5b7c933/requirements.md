# Requirements: incident-f5b7c933

## Incident
- ID: 47b1a988-f6ee-493d-b72c-12f5f5b7c933
- Tenant: admins
- Service: admins-mctl-agents-worker
- Alert: ArgoCDApplicationOutOfSyncLong (type argocd_app_degraded)
- Created: 2026-11-11T14:38:20Z

### Summary
```
ArgoCD application admins-mctl-agents-worker OutOfSync for 1h
```

## Evidence
### Labels
```
tenant: admins
service: admins-mctl-agents-worker
severity: warning
source: alertmanager
```

### Observed state (independently checked)
```
ArgoCD app admins-mctl-agents-worker: health=Healthy, syncStatus=OutOfSync, revision empty
Service config: imageTag 1.117.0, componentType base-service, no database
```

### Log Snippet
```
Service logs (last 50 lines) show no errors. Both pods
(admins-mctl-agents-worker and admins-mctl-agents-worker-exec) are running normally:
INFO:httpx:HTTP Request: GET https://api.mctl.ai/api/v1/workflows/mctl-agents-run-49683063 "HTTP/1.1 200 OK"
INFO:temporalio.activity:submitted mctl-agents-incidents -> mctl-agents-run-49683063
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN the ArgoCD app is refreshed THEN syncStatus is Synced.
